#!/usr/bin/env bash
# Demo: pull from Aliyun registry + run memory-capped judge worker (2C/2G).
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

VERSION="${VERSION:-0.1.6}"
IMAGE="${IMAGE:-registry.cn-beijing.aliyuncs.com/czbyte/acoj-worker:${VERSION}}"
NAME="${NAME:-acoj-worker-demo}"
MEMORY="${MEMORY:-768m}"
CPUS="${CPUS:-1.0}"
ENV_FILE="${ENV_FILE:-$DIR/.env}"

if [[ "${1:-}" == "pull" ]]; then
  docker pull "$IMAGE"
  exit 0
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing env file: $ENV_FILE" >&2
  exit 1
fi

docker pull "$IMAGE"

docker rm -f "$NAME" >/dev/null 2>&1 || true

docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --network host \
  --privileged \
  --cgroupns=host \
  --memory="$MEMORY" \
  --memory-swap="$MEMORY" \
  --cpus="$CPUS" \
  --env-file "$ENV_FILE" \
  -e ACOJ_SANDBOX_BINARY=/usr/local/bin/acosandbox \
  -e ACOJ_CELERY_NODENAME="judge@${NAME}" \
  -e ID_GENERATOR__WORKER_ID="${ID_GENERATOR__WORKER_ID:-1}" \
  "$IMAGE" \
  worker

echo "started $NAME  image=$IMAGE  memory=$MEMORY  cpus=$CPUS"
echo "logs: docker logs -f $NAME"
