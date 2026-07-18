from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RouteSpec:
    version: str
    router: str
    prefix: str = ""
    tags: tuple[str, ...] = ()
    order: int = 100


@dataclass(frozen=True, slots=True)
class BeatScheduleSpec:
    name: str
    task: str
    schedule: float


@dataclass(frozen=True, slots=True)
class ModuleSpec:
    name: str
    routes: tuple[RouteSpec, ...] = ()
    models: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    beat_schedules: tuple[BeatScheduleSpec, ...] = ()
    startup_hooks: tuple[str, ...] = ()
    shutdown_hooks: tuple[str, ...] = ()
    order: int = 100


def import_string(path: str) -> Any:
    module_path, separator, attr = path.partition(":")
    if not separator or not module_path or not attr:
        raise ValueError(f"Import path must use 'module:attribute' format: {path}")
    module = importlib.import_module(module_path)
    value: Any = module
    for part in attr.split("."):
        value = getattr(value, part)
    return value


def import_modules(module_paths: tuple[str, ...] | list[str]) -> None:
    for module_path in module_paths:
        importlib.import_module(module_path)


def _iter_module_manifest_names(package_name: str) -> list[str]:
    package = importlib.import_module(package_name)
    package_paths = getattr(package, "__path__", None)
    if package_paths is None:
        logger.warning(
            "Package %s has no __path__ (namespace package?) — no modules will be discovered",
            package_name,
        )
        return []

    logger.info(
        "Scanning for module manifests in %s at paths: %s",
        package_name,
        list(package_paths),
    )

    names: list[str] = []
    subpkg_count = 0
    for module_info in pkgutil.walk_packages(package_paths, prefix=f"{package_name}."):
        if not module_info.ispkg:
            continue
        subpkg_count += 1
        manifest_name = f"{module_info.name}.module"
        if importlib.util.find_spec(manifest_name) is not None:
            names.append(manifest_name)

    logger.info(
        "Found %d subpackages in %s, %d have module manifests",
        subpkg_count,
        package_name,
        len(names),
    )
    return sorted(set(names))


def load_module_specs(package_name: str = "app.modules") -> list[ModuleSpec]:
    specs: list[ModuleSpec] = []
    seen: set[str] = set()
    manifest_names = _iter_module_manifest_names(package_name)
    logger.info("Loading %d module specs from %s", len(manifest_names), package_name)
    for manifest_name in manifest_names:
        manifest = importlib.import_module(manifest_name)
        module_spec = getattr(manifest, "module", None)
        if not isinstance(module_spec, ModuleSpec):
            raise TypeError(f"{manifest_name}.module must be a ModuleSpec instance")
        if module_spec.name in seen:
            raise ValueError(f"Duplicate module name: {module_spec.name}")
        seen.add(module_spec.name)
        specs.append(module_spec)
    route_count = sum(len(spec.routes) for spec in specs)
    logger.info(
        "Loaded %d modules with %d route specs total",
        len(specs),
        route_count,
    )
    return sorted(specs, key=lambda item: (item.order, item.name))


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


def load_declared_models(module_specs: list[ModuleSpec]) -> None:
    for module_spec in module_specs:
        import_modules(module_spec.models)


def load_declared_tasks(module_specs: list[ModuleSpec]) -> None:
    for module_spec in module_specs:
        import_modules(module_spec.tasks)


def collect_beat_schedule(module_specs: list[ModuleSpec]) -> dict[str, dict[str, float | str]]:
    schedule: dict[str, dict[str, float | str]] = {}
    for module_spec in module_specs:
        for item in module_spec.beat_schedules:
            if item.name in schedule:
                raise ValueError(f"Duplicate Celery beat schedule name: {item.name}")
            schedule[item.name] = {"task": item.task, "schedule": item.schedule}
    return schedule


async def run_startup_hooks(module_specs: list[ModuleSpec]) -> None:
    for module_spec in module_specs:
        await _run_hooks(module_spec.startup_hooks)


async def run_shutdown_hooks(module_specs: list[ModuleSpec]) -> None:
    for module_spec in reversed(module_specs):
        await _run_hooks(module_spec.shutdown_hooks)


async def _run_hooks(hooks: tuple[str, ...]) -> None:
    for hook_path in hooks:
        hook = import_string(hook_path)
        result = hook()
        if inspect.isawaitable(result):
            await result


def _join_prefixes(*parts: str) -> str:
    normalized = [part.strip("/") for part in parts if part and part.strip("/")]
    return "/" + "/".join(normalized)
