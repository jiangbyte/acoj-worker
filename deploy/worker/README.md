# 判题 Worker Demo

单机启动判题 worker：依赖本机 Redis（缓存 + Celery broker）；FILE 测例另需 MinIO。

## 准备

1. 构建或准备好 `acoj-worker` 镜像（见仓库根 README）。
2. 配置本目录 `.env`（端口、Redis、MinIO、`STORAGE__*`、concurrency 等）。
3. 可选：通过环境变量覆盖镜像标签：

```bash
export IMAGE=acoj-worker:local
export VERSION=local
```

## 端口（示例）

| 服务 | 端口 |
|------|------|
| Redis | `6380`（`/0` 缓存，`/1` Celery broker） |
| MinIO API | `9001` |

凭据见 `.env`。

## 启动

```bash
cd deploy/worker
chmod +x run.sh
IMAGE=acoj-worker:local ./run.sh
```

`run.sh` 会以 `--network host --privileged --cgroupns=host` 运行容器，并限制 memory / cpus（可用 `MEMORY` / `CPUS` 覆盖）。

## 运维

```bash
docker logs -f acoj-worker-demo
docker stats acoj-worker-demo
docker rm -f acoj-worker-demo
```

资源示例：`MEMORY=1g CPUS=1.5 IMAGE=acoj-worker:local ./run.sh`。concurrency 与 CPU 对齐。

## 配置要点

- `--network host` 便于访问本机 Redis / MinIO。
- 隔离：namespaces、cgroup、`/opt/acoj-rootfs`。
- `CELERY__WORKER_QUEUES=judge`（不要加入 `default` / `acoj_api`）。
- FILE：配置 `STORAGE__*` 与 bucket；仅 inline 测例时可只依赖 Redis。
