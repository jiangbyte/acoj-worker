from redis.asyncio import Redis

from app.core.config.settings import settings

redis_client: Redis | None = None


async def init_redis() -> None:
    global redis_client
    if redis_client is not None:
        return
    redis_client = Redis.from_url(settings.redis.url, decode_responses=False)
    await redis_client.ping()


def get_redis() -> Redis | None:
    return redis_client


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None
