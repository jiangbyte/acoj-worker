"""Rate-limiting middleware — sliding-window per IP and per user using Redis.

等保 requirement: restrict login attempts and sensitive API abuse.
"""
import logging
import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.deps.context import account_id_ctx, client_ip_ctx
from app.platform.cache.redis import get_redis

logger = logging.getLogger(__name__)

# (path_pattern, requests_per_window, window_seconds, scope)
# scope: "ip" = per-IP, "user" = per-authenticated-user, "mix" = user if auth else IP
RATE_LIMIT_RULES: list[tuple[re.Pattern, int, int, str]] = [
    (re.compile(r"^/api/v\d+/(admin|portal)/login"), 10, 60, "ip"),
    (re.compile(r"^/api/v\d+/portal/register"), 5, 60, "ip"),
    (re.compile(r"^/api/v\d+/(admin|portal)/(forgot-password|reset-password)"), 5, 60, "ip"),
    (re.compile(r"^/api/v\d+/(admin|portal)/captcha"), 30, 60, "ip"),
    (re.compile(r"^/api/v\d+/"), 120, 60, "mix"),
]


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter backed by Redis."""

    async def dispatch(self, request: Request, call_next):
        redis = get_redis()
        if redis is None:
            return await call_next(request)

        path = request.url.path
        for pattern, limit, window_sec, scope in RATE_LIMIT_RULES:
            if not pattern.search(path):
                continue

            if scope == "ip":
                key = f"rl:ip:{client_ip_ctx.get() or 'unknown'}:{pattern.pattern}"
            elif scope == "user":
                uid = account_id_ctx.get()
                if not uid:
                    continue
                key = f"rl:user:{uid}:{pattern.pattern}"
            else:
                uid = account_id_ctx.get()
                key = f"rl:user:{uid}:{pattern.pattern}" if uid else f"rl:ip:{client_ip_ctx.get() or 'unknown'}:{pattern.pattern}"

            try:
                count = await self._increment_and_check(redis, key, limit, window_sec)
                if count > limit:
                    logger.warning("Rate limit exceeded: %s (count=%d, limit=%d)", key, count, limit)
                    return JSONResponse(
                        status_code=429,
                        content={"code": 429, "message": "请求过于频繁，请稍后再试", "data": None},
                        headers={"Retry-After": str(window_sec)},
                    )
            except Exception:
                logger.debug("Rate limit check failed for %s", key, exc_info=True)
            break

        return await call_next(request)

    async def _increment_and_check(
        self, redis, key: str, limit: int, window_sec: int
    ) -> int:
        """Sliding-window counter using Redis sorted set."""
        now = time.time()
        window_start = now - window_sec
        pipe = redis.pipeline()
        pipe.zadd(key, {str(now): now})
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.expire(key, window_sec)
        results = await pipe.execute()
        return int(results[2])


