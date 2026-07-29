#!/bin/sh
set -eu

ROLE="${1:-${HEI_PROCESS_ROLE:-${APP__PROCESS_ROLE:-all}}}"
MINGLE_FLAG="--without-mingle"
GOSSIP_FLAG="--without-gossip"
WORKER_QUEUES="${CELERY__WORKER_QUEUES:-judge,default}"

if [ "${CELERY__WORKER_WITHOUT_MINGLE:-true}" = "false" ]; then
    MINGLE_FLAG=""
fi

if [ "${CELERY__WORKER_WITHOUT_GOSSIP:-true}" = "false" ]; then
    GOSSIP_FLAG=""
fi

start_worker() {
    NODENAME="${ACOJ_CELERY_NODENAME:-${CELERY_NODENAME:-judge@${HOSTNAME:-$(hostname)}}}"
    exec celery -A app.worker.main:celery_app worker \
        $MINGLE_FLAG \
        $GOSSIP_FLAG \
        -n "${NODENAME}" \
        --pool "${CELERY__WORKER_POOL:-threads}" \
        --concurrency "${CELERY__WORKER_CONCURRENCY:-8}" \
        -Q "${WORKER_QUEUES}" \
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
    *)
        echo "Unknown entrypoint role: $ROLE" >&2
        echo "Expected: all, api, worker, beat" >&2
        exit 64
        ;;
esac
