from __future__ import annotations

import inspect
import logging

from app.platform.module.spec import ModuleSpec, import_string

logger = logging.getLogger(__name__)


async def run_startup_hooks(module_specs: list[ModuleSpec]) -> None:
    for module_spec in module_specs:
        await _run_hooks(module_spec.startup_hooks)


async def run_shutdown_hooks(module_specs: list[ModuleSpec]) -> None:
    for module_spec in reversed(module_specs):
        await _run_hooks(module_spec.shutdown_hooks)


async def run_event_handlers(module_specs: list[ModuleSpec]) -> None:
    for module_spec in module_specs:
        await _run_hooks(module_spec.event_handlers)


async def _run_hooks(hooks: tuple[str, ...]) -> None:
    for hook_path in hooks:
        hook = import_string(hook_path)
        result = hook()
        if inspect.isawaitable(result):
            await result
