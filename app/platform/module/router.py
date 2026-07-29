from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import APIRouter

from app.platform.module.discovery import load_module_specs
from app.platform.module.spec import ModuleSpec, RouteSpec, import_string

logger = logging.getLogger(__name__)


@lru_cache(maxsize=None)
def get_api_router(package_name: str = "app.modules") -> APIRouter:
    return build_api_router(load_module_specs(package_name))


def build_api_router(module_specs: list[ModuleSpec]) -> APIRouter:
    api_router = APIRouter()
    route_specs: list[tuple[ModuleSpec, RouteSpec]] = [
        (module_spec, route_spec)
        for module_spec in module_specs
        for route_spec in module_spec.routes
    ]
    route_specs.sort(key=lambda item: (item[1].version, item[1].order, item[0].order, item[0].name))

    logger.info("Building API router with %d route specs", len(route_specs))
    for module_spec, route_spec in route_specs:
        route_router = import_string(route_spec.router)
        if not isinstance(route_router, APIRouter):
            raise TypeError(f"{module_spec.name} route {route_spec.router} is not an APIRouter")
        prefix = _join_prefixes("/api", route_spec.version, route_spec.prefix)
        logger.debug(
            "Including router %s -> prefix=%s, tags=%s",
            route_spec.router,
            prefix,
            route_spec.tags,
        )
        api_router.include_router(route_router, prefix=prefix, tags=list(route_spec.tags))
    logger.info("API router built with %d total routes", len(api_router.routes))
    return api_router


def _join_prefixes(*parts: str) -> str:
    normalized = [part.strip("/") for part in parts if part and part.strip("/")]
    return "/" + "/".join(normalized)
