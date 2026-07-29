# Demo 部署（172.24.149.177，基础设施端口 = 常规 +1，机器 2C/2G）

运行时：Redis、RabbitMQ；FILE 测例：MinIO。

## 镜像

```text
registry.cn-beijing.aliyuncs.com/czbyte/acoj-worker:0.1.6
```

`VERSION=x.y.z ./run.sh`（默认 `0.1.6`）。

## 端口

| 服务 | 端口 |
|------|------|
| Redis | `6380` |
| RabbitMQ AMQP | `5673` |
| MinIO API | `9001` |

凭据见 `.env`。

## 启动

```bash
cd deploy/worker
chmod +x run.sh
./run.sh pull
./run.sh
```

```bash
docker pull registry.cn-beijing.aliyuncs.com/czbyte/acoj-worker:0.1.6
docker rm -f acoj-worker-demo 2>/dev/null || true
docker run -d \
  --name acoj-worker-demo \
  --restart unless-stopped \
  --network host \
  --privileged \
  --cgroupns=host \
  --memory=768m \
  --memory-swap=768m \
  --cpus=1.0 \
  --env-file .env \
  -e ACOJ_SANDBOX_BINARY=/usr/local/bin/acosandbox \
  -e ACOJ_CELERY_NODENAME=judge@acoj-worker-demo \
  -e ID_GENERATOR__WORKER_ID=1 \
  registry.cn-beijing.aliyuncs.com/czbyte/acoj-worker:0.1.6 \
  worker
```

## 运维

```bash
docker logs -f acoj-worker-demo
docker stats acoj-worker-demo
docker rm -f acoj-worker-demo
```

资源示例：`MEMORY=1g CPUS=1.5 ./run.sh`。concurrency 与 CPU 对齐。

## 配置要点

- `--network host` 访问本机 Redis / MQ / MinIO。
- 隔离：namespaces、cgroup、`/opt/acoj-rootfs`（usr-merge + `/usr` `/etc` `/proc`）。
- `STORAGE__*`、`CELERY__WORKER_CONCURRENCY=2`、sandbox 池 `4` 见 `.env`。
- FILE：MinIO bucket `acoj`；inline 测例可只用 Redis/MQ。
