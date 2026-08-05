# acoj-worker

ACOJ 判题 Worker：Celery 消费 `judge.execute`，调用 `acoj-sandbox` / `acosandbox` 执行，经 Redis result backend 返回 `JudgeResultOut`。

兄弟仓库：
- [acoj](https://github.com/jiangbyte/acoj) — 主站 API
- [acoj-sandbox](https://github.com/jiangbyte/acoj-sandbox) — 判题沙箱

- 协议：[docs/judge-protocol.md](docs/judge-protocol.md)
- 单机 demo 启动脚本：[deploy/worker/](deploy/worker/)

运行时依赖 Redis（缓存与 Celery broker）。FILE 测例另需 MinIO（或 S3 兼容存储）。配置来自环境变量。

## 流程

```text
业务 API
  → send_task("judge.execute", queue="judge", link=apply@acoj_api)
  → Redis broker
  → Celery worker（仅 -Q judge）
       → JudgePayload 校验
       → STANDARD / SPECIAL_JUDGE / INTERACTIVE
       → SandboxClient + acosandbox
       → return JudgeResultOut
  → Celery link → API 侧 celery（acoj_api）落库 + SSE
```

要点：

- Broker 为 Redis；落库由 API 侧 Celery `link` 完成。判题 worker 不要消费 `default` / `acoj_api`。
- 用户源码字段：`source`。
- FILE：`input_file` / `output_file` + sha256，经 `STORAGE__*` 下载与本地缓存；失败时 `status=FAILED`。
- 语言命令来自 payload；Java / Go 在 `language_config.py` 中配置 `memory_limit_check_only` 等。
- `time_ms` / `memory_kb` 为测例汇总；`compile_*` 为编译阶段；内存为 `getrusage` RSS。

## 本地开发

Python ≥ 3.11，以及 Redis（FILE 时再加对象存储）。

```bash
cp .env.example .env
pip install -e ".[dev]"
# 同级克隆 https://github.com/jiangbyte/acoj-sandbox 后：
pip install -e ../acoj-sandbox/lang
ACOJ_SANDBOX_SKIP_NATIVE_BUILD=1 pip install -e ../acoj-sandbox
# 或 export ACOJ_SANDBOX_BINARY=/path/to/build/acosandbox

python -m celery -A app.worker.main:celery_app worker \
  --without-mingle --without-gossip \
  -Q judge --pool threads --concurrency 8 -n judge@dev
```

本机 `.env` 默认可关闭 namespaces / cgroup。容器生产环境使用 `--privileged --cgroupns=host`。

`entrypoint.sh` 角色：`worker`（判题）、`beat`、`api`。

## Docker

```bash
DOCKER_BUILDKIT=1 docker build \
  --build-context sandbox=../acoj-sandbox \
  -t acoj-worker:local .
```

镜像内含 `acosandbox`、`acoj-sandbox`、常用语言工具链与 `/opt/acoj-rootfs`。默认开启 namespaces + cgroup，并 bind `/usr` `/etc` `/proc`。

```bash
cd deploy/worker
# 编辑 .env，设置 IMAGE=acoj-worker:local 或你的构建标签
./run.sh
```

或直接：

```bash
docker run -d --name acoj-j1 --network host \
  --privileged --cgroupns=host \
  --memory=768m --cpus=1.0 \
  --env-file .env.production \
  -e ACOJ_SANDBOX_BINARY=/usr/local/bin/acosandbox \
  -e ACOJ_CELERY_NODENAME=judge@j1 \
  -e ID_GENERATOR__WORKER_ID=1 \
  acoj-worker:local worker
```

| 角色 | 命令 | 说明 |
|------|------|------|
| Worker | `worker` | 需 `--privileged --cgroupns=host`；可多副本 |
| Beat | `beat` | 定时任务时单副本即可 |

### 环境变量

| 变量 | 说明 |
|------|------|
| `CELERY__BROKER_URL` | Redis broker（建议独立 DB，如 `/1`）；密码中的 `@` 写成 `%40` |
| `CELERY__BROKER_VISIBILITY_TIMEOUT` | 须大于最长判题时间（默认 3600） |
| `REDIS__URL` | 缓存与默认 result backend（建议 `/0`） |
| `CELERY__WORKER_CONCURRENCY` | 与容器 `--cpus` 对齐 |
| `JUDGE__WORKER_PREFETCH_MULTIPLIER` | 公平性用 `1`；吞吐可加大 |
| `JUDGE__SANDBOX_WORKER_POOL_SIZE` | ≥ concurrency × parallelism |
| `JUDGE__SANDBOX_ENABLE_NAMESPACES` 等 | 隔离开关与 rootfs |
| `ACOJ_CELERY_NODENAME` | 每实例唯一 |
| `ID_GENERATOR__WORKER_ID` | 每实例唯一 |
| `ACOJ_SANDBOX_BINARY` | 如 `/usr/local/bin/acosandbox` |
| `STORAGE__*` | FILE 对象存储 |

模板：`.env.production.example`。

## FILE 测例

| 项 | 约定 |
|----|------|
| 对象 | 每测例 `.in` / `.out`（或 `.ans`） |
| key | `oj/problem/{problem_id}/testdata/{stem}.in` |
| payload | `input_file` / `output_file` + sha256 |
| 桶 | 与 API 共用 `STORAGE__BUCKET` |

下载失败返回 `status=FAILED` 与 `error`。

## 脚本与测试

| 路径 | 用途 |
|------|------|
| `entrypoint.sh` | 容器入口 |
| `deploy/worker/run.sh` | demo 启动 |
| `scripts/ops/bench_judge_burst.py` | 压测 |
| `scripts/ops/docker_sandbox_smoke.py` | 四语言冒烟 |
| `scripts/ops/print_minio_storage_env.sh` | 打印 MinIO 相关 env |

`pytest`、`tests/test_all_judge_modes.py`、`tests/judge_helper.py`、`tests/integration/test_minio_download_cache.py`。

## 目录

```text
app/modules/judge/
app/platform/tasks/
app/platform/storage/
deploy/worker/
Dockerfile
docs/judge-protocol.md
```
