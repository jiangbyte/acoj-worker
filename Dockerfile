# Build inside the acoj-worker repo (sandbox is a separate repo):
#   docker build \
#     --build-context sandbox=../acoj-sandbox \
#     -t acoj-worker:<tag> .
#
# CI: checkout both repos as siblings, then point --build-context at the sandbox path.
# Optional: publish an acoj-sandbox image later and switch COPY --from to that image.
# Requires BuildKit (DOCKER_BUILDKIT=1). Do not rely on docker.io/dockerfile frontend.

ARG PYTHON_BASE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim
ARG DEBIAN_BASE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/debian:bookworm-slim

# ── Stage 1: build acosandbox from external sandbox context ─────────────────
FROM ${DEBIAN_BASE} AS sandbox-build

# apt: Aliyun Debian mirror (CN)
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' \
        /etc/apt/sources.list.d/debian.sources; \
    else \
      printf '%s\n' \
        'deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware' \
        'deb https://mirrors.aliyun.com/debian-security bookworm-security main contrib non-free non-free-firmware' \
        'deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware' \
        > /etc/apt/sources.list; \
      rm -f /etc/apt/sources.list.d/*; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      pkg-config \
      libseccomp-dev \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
COPY --from=sandbox Makefile ./
COPY --from=sandbox include ./include
COPY --from=sandbox src ./src
COPY --from=sandbox third_party ./third_party
RUN make -j"$(nproc)"

# Full sandbox tree for pip install (python/ + lang/ + pyproject)
FROM ${DEBIAN_BASE} AS sandbox-src
COPY --from=sandbox / /sandbox

# ── Stage 2: runtime (unified api / worker / beat) ──────────────────────────
FROM ${PYTHON_BASE}

ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# apt + pip: Aliyun mirrors (CN). Base images: Huawei SWR docker.io mirror.
RUN set -eux; \
    if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' \
        /etc/apt/sources.list.d/debian.sources; \
    else \
      printf '%s\n' \
        'deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware' \
        'deb https://mirrors.aliyun.com/debian-security bookworm-security main contrib non-free non-free-firmware' \
        'deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware' \
        > /etc/apt/sources.list; \
      rm -f /etc/apt/sources.list.d/*; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
      tini \
      ca-certificates \
      libseccomp2 \
      g++ \
      gcc \
      openjdk-17-jdk-headless \
      golang-go \
      python3 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p \
      /opt/acoj-rootfs/tmp \
      /opt/acoj-rootfs/dev \
      /opt/acoj-rootfs/usr \
      /opt/acoj-rootfs/etc \
      /opt/acoj-rootfs/proc \
    && ln -s usr/bin /opt/acoj-rootfs/bin \
    && ln -s usr/lib /opt/acoj-rootfs/lib \
    && ln -s usr/lib64 /opt/acoj-rootfs/lib64 \
    && chmod 1777 /opt/acoj-rootfs/tmp \
    && mknod -m 666 /opt/acoj-rootfs/dev/null c 1 3 \
    && mknod -m 666 /opt/acoj-rootfs/dev/zero c 1 5 \
    && mknod -m 666 /opt/acoj-rootfs/dev/urandom c 1 9

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP__HOST=0.0.0.0 \
    APP__PORT=8000 \
    APP__DEBUG=false \
    APP__PROCESS_ROLE=all \
    APP__WORKERS=0 \
    APP__WORKER_MAX=4 \
    AUDIT__OPERATION_QUEUE_SIZE=1000 \
    AUDIT__OPERATION_SHUTDOWN_TIMEOUT_SECONDS=5 \
    ACOJ_SANDBOX_BINARY=/usr/local/bin/acosandbox \
    CELERY__WORKER_QUEUES=judge,default \
    CELERY__WORKER_POOL=threads \
    CELERY__WORKER_CONCURRENCY=8 \
    JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    GOPROXY=off \
    GO111MODULE=off \
    JUDGE__SANDBOX_ENABLE_NAMESPACES=true \
    JUDGE__SANDBOX_ENABLE_CGROUP=true \
    JUDGE__SANDBOX_ROOTFS_PATH=/opt/acoj-rootfs \
    JUDGE__SANDBOX_BIND_SYSTEM_PATHS=true

ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY --from=sandbox-build /src/build/acosandbox /usr/local/bin/acosandbox
RUN chmod 755 /usr/local/bin/acosandbox

COPY --from=sandbox-src /sandbox /tmp/acoj-sandbox
COPY --from=sandbox-build /src/build/acosandbox /tmp/acoj-sandbox/build/acosandbox
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --index-url "${PIP_INDEX_URL}" --prefer-binary \
      /tmp/acoj-sandbox/lang \
    && ACOJ_SANDBOX_SKIP_NATIVE_BUILD=1 \
       python -m pip install --index-url "${PIP_INDEX_URL}" --prefer-binary --no-deps \
      /tmp/acoj-sandbox \
    && rm -rf /tmp/acoj-sandbox

COPY pyproject.toml README.md ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -c 'import os, subprocess, sys, tomllib; data = tomllib.load(open("pyproject.toml", "rb")); deps = data["project"]["dependencies"]; subprocess.check_call([sys.executable, "-m", "pip", "install", "--index-url", os.environ["PIP_INDEX_URL"], "--prefer-binary", *deps])'

COPY app ./app
COPY gunicorn.conf.py ./
COPY entrypoint.sh ./

RUN chmod +x entrypoint.sh \
    && mkdir -p /app/storage /app/.runtime

VOLUME ["/app/storage"]
EXPOSE 8000

# Root required for sandbox namespaces/cgroup when running as worker.
ENTRYPOINT ["tini", "-g", "--", "/app/entrypoint.sh"]
CMD ["all"]
