from __future__ import annotations

import ipaddress

from starlette.requests import Request

from app.core.config.settings import settings


def get_client_ip(request: Request) -> str | None:
    """Resolve the real client IP, trusting forwarding headers only from trusted proxies."""
    direct_ip = request.client.host if request.client else None
    if not direct_ip or not _is_trusted_proxy(direct_ip):
        return direct_ip

    real_ip = _first_header_ip(request.headers.get("x-real-ip"))
    if real_ip:
        return real_ip

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return _first_header_ip(forwarded_for) or direct_ip
    return direct_ip


def _first_header_ip(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.split(",", 1)[0].strip()
    return candidate or None


def _is_trusted_proxy(remote_ip: str) -> bool:
    trusted = settings.app.trusted_proxy_ips
    if not trusted:
        return False
    if "*" in trusted:
        return True
    try:
        remote = ipaddress.ip_address(remote_ip)
    except ValueError:
        return remote_ip in trusted

    for item in trusted:
        try:
            if remote in ipaddress.ip_network(item, strict=False):
                return True
        except ValueError:
            if item == remote_ip:
                return True
    return False
