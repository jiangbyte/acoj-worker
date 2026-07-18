from typing import Any

import httpx

from app.core.config.settings import settings
from app.platform.observability.metrics import track_http_client_request

http_client: httpx.AsyncClient | None = None


class InstrumentedAsyncClient(httpx.AsyncClient):
    async def request(self, method: str, url: httpx._types.URLTypes, *args: Any, **kwargs: Any) -> httpx.Response:
        """在启用观测性时采集出站 HTTP 指标，关闭观测性时保持纯净调用链。"""
        if not (settings.observability.enabled and settings.observability.http_client_observability_enabled):
            return await super().request(method, url, *args, **kwargs)
        request = self.build_request(method, url, *args, **kwargs)
        host = request.url.host or "unknown"
        with track_http_client_request(method.upper(), host) as finalize:
            response = await self.send(request)
            finalize(response.status_code)
            return response


async def init_http_client() -> None:
    """初始化全局 HTTP 客户端，供应用生命周期内复用连接池。"""
    global http_client
    if http_client is None:
        http_client = InstrumentedAsyncClient(timeout=10.0)


def get_http_client() -> httpx.AsyncClient:
    """获取全局 HTTP 客户端实例，若未初始化则明确抛错。"""
    if http_client is None:
        raise RuntimeError("HTTP client is not initialized")
    return http_client


async def close_http_client() -> None:
    """关闭全局 HTTP 客户端并释放底层连接资源。"""
    global http_client
    if http_client is not None:
        await http_client.aclose()
        http_client = None
