"""Judge worker module spec — Celery task 无需启动消费者。"""

from app.platform.module import ModuleSpec

module = ModuleSpec(
    name="judge",
    tasks=("app.modules.judge.tasks",),
)
