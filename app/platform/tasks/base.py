from contextlib import nullcontext

from celery import Task

from app.core.config.settings import settings
from app.platform.observability.metrics import track_celery_task


class BaseTask(Task):
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_kwargs = {"max_retries": 3}

    def __call__(self, *args, **kwargs):
        tracker = (
            track_celery_task(self.name)
            if settings.observability.enabled and settings.observability.celery_observability_enabled
            else nullcontext(lambda *_: None)
        )
        with tracker as finalize:
            try:
                result = super().__call__(*args, **kwargs)
            except Exception:
                finalize("failure")
                raise
            finalize("success")
            return result
