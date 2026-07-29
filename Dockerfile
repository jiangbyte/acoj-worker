#FROM python:3.11-slim
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim
#FROM docker.xuanyuan.run/library/python:3.11-slim

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security hardening.
RUN groupadd --system appgroup \
    && useradd --system --gid appgroup --home-dir /app --shell /usr/sbin/nologin appuser

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP__HOST=0.0.0.0 \
    APP__PORT=8000 \
    APP__DEBUG=false \
    APP__PROCESS_ROLE=all \
    APP__WORKERS=0 \
    APP__WORKER_MAX=4 \
    DB__POOL_SIZE=5 \
    DB__MAX_OVERFLOW=5 \
    DB__POOL_PRE_PING=true \
    DB__POOL_RECYCLE_SECONDS=1800 \
    AUDIT__OPERATION_QUEUE_SIZE=1000 \
    AUDIT__OPERATION_SHUTDOWN_TIMEOUT_SECONDS=5

ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./

RUN --mount=type=cache,target=/root/.cache/pip \
    python -c 'import os, subprocess, sys, tomllib; data = tomllib.load(open("pyproject.toml", "rb")); deps = data["project"]["dependencies"] + data["project"]["optional-dependencies"]["postgres"]; subprocess.check_call([sys.executable, "-m", "pip", "install", "--index-url", os.environ["PIP_INDEX_URL"], "--prefer-binary", *deps])'

COPY app ./app
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts/db ./scripts/db
COPY scripts/seed ./scripts/seed
COPY gunicorn.conf.py ./
COPY entrypoint.sh ./

RUN chmod +x entrypoint.sh && mkdir -p /app/storage /app/.runtime

RUN chown -R appuser:appgroup /app/storage /app/.runtime
USER appuser

VOLUME ["/app/storage"]
EXPOSE 8000

ENTRYPOINT ["tini", "-g", "--", "/app/entrypoint.sh"]
CMD ["all"]
