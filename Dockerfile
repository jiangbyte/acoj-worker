#FROM python:3.11-slim
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim
#FROM docker.xuanyuan.run/library/python:3.11-slim

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP__HOST=0.0.0.0 \
    APP__PORT=8000 \
    APP__DEBUG=false \
    APP__WORKERS=0 \
    APP__WORKER_MAX=4 \
    CELERY__AUTO_START_ENABLED=false \
    DB__POOL_SIZE=5 \
    DB__MAX_OVERFLOW=5 \
    DB__POOL_PRE_PING=true \
    DB__POOL_RECYCLE_SECONDS=1800 \
    AUDIT__OPERATION_QUEUE_SIZE=1000 \
    AUDIT__OPERATION_SHUTDOWN_TIMEOUT_SECONDS=5 \
    STORAGE__PROVIDER=local \
    STORAGE__LOCAL_ROOT=/app/storage \
    STORAGE__PUBLIC_PATH=/api/v1/files

ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md .env ./

RUN --mount=type=cache,target=/root/.cache/pip \
    python -c 'import os, subprocess, sys, tomllib; data = tomllib.load(open("pyproject.toml", "rb")); deps = data["project"]["dependencies"] + data["project"]["optional-dependencies"]["postgres"]; subprocess.check_call([sys.executable, "-m", "pip", "install", "--index-url", os.environ["PIP_INDEX_URL"], "--prefer-binary", *deps])'

RUN apt-get update && apt-get install -y --no-install-recommends tini && rm -rf /var/lib/apt/lists/*

COPY app ./app
COPY gunicorn.conf.py entrypoint.sh ./

RUN chmod +x entrypoint.sh

RUN mkdir -p /app/storage /app/.runtime

VOLUME ["/app/storage"]

EXPOSE 8000

ENTRYPOINT ["tini", "--"]
CMD ["/app/entrypoint.sh"]
