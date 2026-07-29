#!/usr/bin/env bash
# Print MinIO STORAGE__* lines from docker dev-minio for pasting into .env.
set -euo pipefail

CONTAINER="${MINIO_CONTAINER:-dev-minio}"
ENDPOINT="${ACOJ_MINIO_ENDPOINT:-http://127.0.0.1:9000}"
BUCKET="${ACOJ_MINIO_TEST_BUCKET:-acoj-worker-test}"

USER="$(docker exec "${CONTAINER}" printenv MINIO_ROOT_USER)"
PASS="$(docker exec "${CONTAINER}" printenv MINIO_ROOT_PASSWORD)"

cat <<EOF
# Paste into acoj-worker/.env for multi-node FILE testdata:
STORAGE__PROVIDER=minio
STORAGE__ENDPOINT=${ENDPOINT}
STORAGE__BUCKET=${BUCKET}
STORAGE__ACCESS_KEY=${USER}
STORAGE__SECRET_KEY=${PASS}
STORAGE__REGION=us-east-1
STORAGE__USE_SSL=false
EOF
