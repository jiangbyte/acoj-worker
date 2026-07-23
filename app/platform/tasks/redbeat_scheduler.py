import logging

from redbeat.schedulers import RedBeatSchedulerEntry

from app.platform.module import collect_beat_schedule, load_module_specs

logger = logging.getLogger(__name__)


def sync_to_redbeat(celery_app) -> None:
    """将模块清单中声明的定时任务同步到 redbeat 的 Redis 存储。

    同步到 redbeat 是尝试性操作（Redis 连接失败时不阻塞应用启动）。
    """
    try:
        module_specs = load_module_specs()
        static_schedule = collect_beat_schedule(module_specs)
        for name, spec in static_schedule.items():
            try:
                entry = RedBeatSchedulerEntry(
                    name=name,
                    task=spec["task"],
                    schedule=spec["schedule"],
                    app=celery_app,
                )
                entry.save()
            except Exception:
                logger.exception("Failed to sync '%s' to redbeat", name)
    except Exception:
        logger.exception("Failed to sync static schedules to redbeat")
