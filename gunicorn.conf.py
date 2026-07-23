import os

from app.core.config.settings import settings

bind = f"{settings.app.host}:{settings.app.port}"
worker_class = "uvicorn.workers.UvicornWorker"
workers = settings.app.workers if settings.app.workers > 0 else min(os.cpu_count() or 1, settings.app.worker_max)
max_requests = 10000
max_requests_jitter = 1000
timeout = 30
graceful_timeout = 30
keepalive = 5
accesslog = "-"
errorlog = "-"
loglevel = "info"
