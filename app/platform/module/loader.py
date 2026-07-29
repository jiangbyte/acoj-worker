from __future__ import annotations

import importlib
import logging

from app.platform.module.spec import ModuleSpec

logger = logging.getLogger(__name__)


def import_modules(module_paths: tuple[str, ...] | list[str]) -> None:
    for module_path in module_paths:
        importlib.import_module(module_path)


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
