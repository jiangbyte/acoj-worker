#!/usr/bin/env bash
# Bootstrap acoj-worker + acoj-sandbox inside acoj-worker-sec-test:patched
set -euo pipefail

SRC="${SRC:-/src}"
WORKER="${WORKER:-/worker}"
INSTALL_SBX="${INSTALL_SBX:-/tmp/acoj-sandbox-install}"
INSTALL_DEPS="${INSTALL_DEPS:-/tmp/acoj-worker-deps}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
PIP_TRUSTED_HOST="${PIP_TRUSTED_HOST:-pypi.tuna.tsinghua.edu.cn}"

# Clear obsolete CELERY__* from image ENV (sandbox/judge knobs moved to JUDGE__*)
for var in \
  CELERY__SANDBOX_WORKER_POOL_SIZE \
  CELERY__SANDBOX_STANDARD_PARALLELISM \
  CELERY__SANDBOX_BORROW_TIMEOUT_SECONDS \
  CELERY__SANDBOX_MAX_QUEUE_WAIT_SECONDS \
  CELERY__SANDBOX_COMPILATION_CACHE_ENABLED \
  CELERY__SANDBOX_COMPILATION_CACHE_DIR \
  CELERY__SANDBOX_ENABLE_NAMESPACES \
  CELERY__SANDBOX_ENABLE_CGROUP \
  CELERY__SANDBOX_CGROUP_VERSION \
  CELERY__SANDBOX_CGROUP_BASE_PATH \
  CELERY__WORKER_PREFETCH_MULTIPLIER \
  CELERY__RESULT_BACKEND \
  CELERY__AUTO_START_ENABLED
do
  unset "${var}" 2>/dev/null || true
done

echo "[bootstrap] rebuild sandbox from ${SRC}"
rm -rf /work/acoj-sandbox
cp -a "${SRC}" /work/acoj-sandbox
cd /work/acoj-sandbox
make clean >/dev/null
make all
install -m 755 build/acosandbox /usr/local/bin/acosandbox

echo "[bootstrap] install python packages (index=${PIP_INDEX_URL})"
rm -rf "${INSTALL_SBX}" "${INSTALL_DEPS}"
python3 -m pip install . \
  --index-url "${PIP_INDEX_URL}" \
  --trusted-host "${PIP_TRUSTED_HOST}" \
  --target "${INSTALL_SBX}" \
  --no-deps \
  --no-build-isolation \
  --break-system-packages \
  >/tmp/pip-sandbox.log

# Minimal deps for celery worker + judge + settings load
python3 -m pip install \
  --index-url "${PIP_INDEX_URL}" \
  --trusted-host "${PIP_TRUSTED_HOST}" \
  --target "${INSTALL_DEPS}" \
  --break-system-packages \
  "celery>=5.5.0" \
  "celery-redbeat>=2.2.0" \
  "pydantic>=2.11.0" \
  "pydantic-settings>=2.10.0" \
  "prometheus-client>=0.22.0" \
  "fastapi>=0.116.0" \
  "redis>=6.2.0" \
  "sqlalchemy>=2.0.41" \
  "asyncpg>=0.30.0" \
  "greenlet>=3.2.0" \
  "httpx>=0.28.0" \
  "orjson>=3.10.0" \
  "bcrypt>=5.0.0" \
  "cryptography>=45.0.0" \
  "python-multipart>=0.0.20" \
  "snowflake-id>=1.0.2" \
  "jinja2>=3.1.0" \
  "boto3>=1.39.0" \
  "oss2>=2.19.0" \
  "opentelemetry-api>=1.36.0" \
  "opentelemetry-sdk>=1.36.0" \
  "opentelemetry-exporter-otlp>=1.36.0" \
  "opentelemetry-instrumentation-fastapi>=0.57b0" \
  "opentelemetry-instrumentation-httpx>=0.57b0" \
  "opentelemetry-instrumentation-sqlalchemy>=0.57b0" \
  "alembic>=1.16.0" \
  "uvicorn[standard]>=0.35.0" \
  "gunicorn>=23.0.0" \
  "pika>=1.3.2" \
  >/tmp/pip-worker.log

export PYTHONPATH="${INSTALL_DEPS}:${INSTALL_SBX}:${WORKER}${PYTHONPATH:+:${PYTHONPATH}}"
export PATH="/usr/local/bin:${PATH}"

python3 - <<'PY'
import socket
from acoj_sandbox import default_binary_path
print("sandbox_binary", default_binary_path(), flush=True)
s = socket.create_connection(("127.0.0.1", 5672), timeout=3)
s.close()
print("rabbitmq_connect_ok", flush=True)
s = socket.create_connection(("127.0.0.1", 6379), timeout=3)
s.close()
print("redis_connect_ok", flush=True)
s = socket.create_connection(("127.0.0.1", 5432), timeout=3)
s.close()
print("postgres_connect_ok", flush=True)
PY

echo "[bootstrap] ready"
echo "PYTHONPATH=${PYTHONPATH}"
