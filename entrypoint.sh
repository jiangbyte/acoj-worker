#!/bin/sh
set -e

celery -A app.platform.tasks.celery_app:celery_app worker \
    -Q judge \
    --pool threads \
    --concurrency "${CELERY__WORKER_CONCURRENCY:-8}" \
    --without-mingle --without-gossip \
    --loglevel "${CELERY__WORKER_LOG_LEVEL:-INFO}" &

celery -A app.platform.tasks.celery_app:celery_app beat \
    --loglevel "${CELERY__BEAT_LOG_LEVEL:-INFO}" \
    --scheduler redbeat.RedBeatScheduler &

exec gunicorn app.main:app -c gunicorn.conf.py
