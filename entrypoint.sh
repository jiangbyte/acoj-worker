#!/bin/sh
set -eu

ROLE="${1:-${HEI_PROCESS_ROLE:-${APP__PROCESS_ROLE:-all}}}"
MINGLE_FLAG="--without-mingle"
GOSSIP_FLAG="--without-gossip"

if [ "${CELERY__WORKER_WITHOUT_MINGLE:-true}" = "false" ]; then
    MINGLE_FLAG=""
fi

if [ "${CELERY__WORKER_WITHOUT_GOSSIP:-true}" = "false" ]; then
    GOSSIP_FLAG=""
fi

start_worker() {
    exec celery -A app.worker.main:celery_app worker \
        $MINGLE_FLAG \
        $GOSSIP_FLAG \
        --pool "${CELERY__WORKER_POOL:-solo}" \
        --concurrency "${CELERY__WORKER_CONCURRENCY:-1}" \
        --loglevel "${CELERY__WORKER_LOG_LEVEL:-INFO}"
}

start_beat() {
    exec celery -A app.worker.main:celery_app beat \
        --loglevel "${CELERY__BEAT_LOG_LEVEL:-INFO}" \
        --scheduler redbeat.RedBeatScheduler
}

start_api() {
    exec gunicorn app.main:app -c gunicorn.conf.py
}

start_all() {
    exec python -m app.platform.runtime.process_group
}

run_migrate() {
    exec python scripts/db/migrate.py
}

run_seed() {
    exec python scripts/seed/seed_super_admin.py
}

case "$ROLE" in
    all)
        start_all
        ;;
    api)
        start_api
        ;;
    worker)
        start_worker
        ;;
    beat)
        start_beat
        ;;
    migrate)
        run_migrate
        ;;
    seed)
        run_seed
        ;;
    *)
        echo "Unknown entrypoint role: $ROLE" >&2
        echo "Expected: all, api, worker, beat, migrate, seed" >&2
        exit 64
        ;;
esac
