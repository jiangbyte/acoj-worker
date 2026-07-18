from app.platform.module import collect_beat_schedule, load_module_specs
from app.platform.tasks.celery_app import celery_app

celery_app.conf.beat_schedule = collect_beat_schedule(load_module_specs())
