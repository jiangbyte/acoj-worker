from __future__ import annotations

import importlib
import logging
import os
from functools import cache

from app.platform.module.spec import ModuleSpec

logger = logging.getLogger(__name__)


def _iter_module_manifest_names(package_name: str) -> list[str]:
    import pkgutil

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
    package_names = _resolve_package_names(package_name)
    return list(_load_module_specs_cached(tuple(package_names)))


@cache
def _load_module_specs_cached(package_names: tuple[str, ...]) -> tuple[ModuleSpec, ...]:
    specs: list[ModuleSpec] = []
    seen: set[str] = set()
    manifest_names: list[str] = []
    for package_name in package_names:
        manifest_names.extend(_iter_module_manifest_names(package_name))
    logger.info("Loading %d module specs from %s", len(manifest_names), package_names)
    for manifest_name in manifest_names:
        manifest = importlib.import_module(manifest_name)
        module_spec = getattr(manifest, "module", None)
        if not isinstance(module_spec, ModuleSpec):
            raise TypeError(f"{manifest_name}.module must be a ModuleSpec instance")
        if module_spec.name in seen:
            raise ValueError(f"Duplicate module name: {module_spec.name}")
        if not _is_module_enabled(module_spec):
            logger.info("Module %s disabled", module_spec.name)
            continue
        seen.add(module_spec.name)
        specs.append(module_spec)

    specs = _topological_sort(specs)

    route_count = sum(len(spec.routes) for spec in specs)
    logger.info(
        "Loaded %d modules with %d route specs total",
        len(specs),
        route_count,
    )
    return tuple(specs)


def _resolve_package_names(package_name: str) -> list[str]:
    package_names = [item.strip() for item in package_name.split(",") if item.strip()]
    env_packages = [
        item.strip()
        for item in os.environ.get("HEI_MODULE_PACKAGES", "").split(",")
        if item.strip()
    ]
    for item in env_packages:
        if item not in package_names:
            package_names.append(item)
    return package_names


def _is_module_enabled(spec: ModuleSpec) -> bool:
    disabled = _env_name_set("HEI_DISABLED_MODULES")
    enabled = _env_name_set("HEI_ENABLED_MODULES")
    if spec.name in disabled:
        return False
    if spec.name in enabled:
        return True
    return spec.enabled


def _env_name_set(name: str) -> set[str]:
    return {item.strip() for item in os.environ.get(name, "").split(",") if item.strip()}


def _topological_sort(specs: list[ModuleSpec]) -> list[ModuleSpec]:
    """按 depends_on 拓扑排序，保证依赖模块在前。"""
    by_name = {s.name: s for s in specs}
    visited: set[str] = set()
    result: list[ModuleSpec] = []

    def visit(name: str, path: set[str]) -> None:
        if name in visited:
            return
        if name in path:
            raise ValueError(f"Circular module dependency: {' -> '.join(path)} -> {name}")
        spec = by_name.get(name)
        if spec is None:
            logger.warning("Module '%s' not found (declared as dependency)", name)
            visited.add(name)
            return
        path.add(name)
        for dep in spec.depends_on:
            visit(dep, path)
        path.remove(name)
        visited.add(name)
        result.append(spec)

    for spec in specs:
        if spec.name not in visited:
            visit(spec.name, set())

    # 未声明 depends_on 的模块保持原 order 排序
    resolved_names = {s.name for s in result}
    remaining = [s for s in specs if s.name not in resolved_names]
    remaining.sort(key=lambda s: (s.order, s.name))
    result.extend(remaining)

    return result
