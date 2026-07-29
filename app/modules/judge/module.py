"""Judge worker module — Celery tasks for judge.execute."""

from app.platform.module import ModuleSpec

module = ModuleSpec(
    name="judge",
    enabled=True,
    tasks=("app.modules.judge.tasks",),
    config_model="app.modules.judge.config:JudgeSettings",
    startup_hooks=("app.modules.judge.pool_metrics:init",),
)
