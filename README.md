# ACOJ Worker

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116%2B-009688?logo=fastapi&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.x-37814A)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-Supported-FF6600?logo=rabbitmq&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

`acoj-worker` 是 ACOJ 的判题 worker 服务。它通过 RabbitMQ/Celery 消费 `judge` 队列中的判题任务，调用 `acoj-sandbox` 完成编译、运行、资源限制和计量，并通过 Celery task result 返回判题结果。判题入口是 Celery task `judge.execute`。

## 架构

```text
API / test client
  -> RabbitMQ judge queue
  -> Celery task judge.execute
  -> app.modules.judge.orchestrator.judge()
  -> judge mode: STANDARD / SPECIAL_JUDGE / INTERACTIVE
  -> SandboxClient
  -> acoj-sandbox worker pool
  -> acosandbox C++ binary
```

核心模块：

- `app/modules/judge/tasks.py`：Celery task `judge.execute`。
- `app/modules/judge/orchestrator.py`：按 `judge_mode` 分发到不同判题模式。
- `app/modules/judge/modes/__init__.py`：`MODE_REGISTRY` 注册 STANDARD/SPECIAL_JUDGE/INTERACTIVE。
- `app/modules/judge/modes/base.py`：`BaseJudgeMode` 抽象基类。
- `app/modules/judge/modes/standard.py`：STANDARD，支持 ACM/OI/IOI 计分。
- `app/modules/judge/modes/spj.py`：SPECIAL_JUDGE，checker 编译一次、多 case 复用。
- `app/modules/judge/modes/interactive.py`：INTERACTIVE，用户程序和 interactor 通过 FIFO 通信。
- `app/modules/judge/case_builder.py`：构造 JudgeCase，提取期望输出文本。
- `app/modules/judge/checker.py`：输出比对（忽略行尾空白）。
- `app/modules/judge/data_loader.py`：从本地/远端存储加载测试数据。
- `app/modules/judge/file_cache.py`：判题测试数据文件缓存（避免重复远端下载）。
- `app/modules/judge/language_config.py`：从 payload 生成 `acoj_sandbox.LanguagesConfig`。
- `app/modules/judge/pool_metrics.py`：sandbox worker pool 指标采集。
- `app/modules/judge/result_mapper.py`：映射 sandbox 结果到 OJ 状态码，聚合总结果。
- `app/modules/judge/sandbox_config.py`：从配置生成 sandbox isolation/cgroup/client。
- `app/modules/judge/schemas.py`：判题输入/输出 Pydantic 模型。
- `app/modules/judge/scoring.py`：IOI 子任务计分、依赖关系解析、错误评语。
- `app/modules/judge/module.py`：ModuleSpec 声明（config_model / startup_hooks / 纯任务）。
- `app/modules/judge/config.py`：JudgeSettings（`JUDGE__*`），sandbox / 缓存 / 判题队列。
- `app/modules/judge/celery_setup.py`：在任务加载时把队列、prefetch、超时应用到上游 celery_app。
- `app/platform/tasks/celery_app.py`：上游 Celery app（broker / RedBeat / result backend），无判题业务配置。
- `app/platform/tasks/redbeat_scheduler.py`：RedBeat 定时任务同步。
- `app/platform/tasks/base.py`：基类 task。

## 功能

- STANDARD 判题：ACM 首错跳过、OI 按点计分、IOI batch/subtask 聚合。
- SPECIAL_JUDGE：用户程序和 checker 分别编译，checker per-case 复用。
- INTERACTIVE：用户程序与 interactor 双向 FIFO 通信，异常路径快速释放 FIFO，避免等待十几秒。
- 多语言：从任务 payload 的 `language` 字段生成 `acoj_sandbox.LanguagesConfig`。
- 真实队列：RabbitMQ + Celery；`judge.celery_setup` 将默认队列设为 `judge`（不改框架 celery_app）。
- sandbox worker pool：进程级复用 `acosandbox worker`，降低 subprocess 启动成本。
- 编译缓存：由 `acoj-sandbox` 提供 content-addressed cache，worker 默认开启。
- 隔离能力：可配置 namespaces、network/ipc/uts/mount isolation、cgroup v1/v2、rootfs。
- 可观测性：Celery 进程状态、sandbox pool metrics、日志、Prometheus/OpenTelemetry 基础设施。

## 运行要求

- Python 3.11+
- RabbitMQ
- Redis（Celery beat lock、缓存等基础设施使用）
- PostgreSQL（API/业务模块需要）
- `acoj-sandbox` Python 包与 C++ binary
- 判题语言工具链，例如 `g++`、`gcc`、`python3`、`openjdk-17-jdk`
- 生产隔离建议 Linux + Docker/root 权限 + cgroup v2 + seccomp

Debian/Ubuntu 基础依赖示例：

```bash
sudo apt-get update
sudo apt-get install -y build-essential pkg-config libseccomp-dev python3 python3-pip
```

## 快速启动

安装 sandbox：

```bash
cd /path/to/acoj-sandbox
make clean all
python -m pip install .
```

安装 worker：

```bash
cd /path/to/acoj-worker
python -m pip install -e ".[postgres]"
cp .env.example .env
```

编辑 `.env`，至少配置：

```env
APP__DEBUG=true
DB__URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/hei_fastapi
REDIS__URL=redis://127.0.0.1:6379/0
CELERY__BROKER_URL=amqp://admin:123456@127.0.0.1:5672//
```

开发模式下可以直接启动 API（使用 `entrypoint.sh` 同时启动 API + Worker + Beat）：

```bash
./entrypoint.sh
```

也可以单独启动各部分：

```bash
gunicorn app.main:app -c gunicorn.conf.py           # 仅 API
celery -A app.worker.main:celery_app worker \
  --pool threads \
  --concurrency 8 \
  --without-mingle \
  --without-gossip \
  --loglevel INFO
```

> 判题队列由 `JUDGE__TASK_DEFAULT_QUEUE`（默认 `judge`）在模块加载时配置；无需在框架层写死 `-Q judge`。若显式传 `-Q`，需与该配置一致。

RedBeat 定时任务调度器：

```bash
celery -A app.worker.main:celery_app beat \
  --loglevel INFO \
  --scheduler redbeat.RedBeatScheduler
```

## 配置

配置使用 `pydantic-settings`，环境变量嵌套分隔符为 `__`。

### Celery

| 配置 | 默认值 | 说明 |
|---|---:|---|
| `CELERY__BROKER_URL` | `amqp://guest:guest@127.0.0.1:5672//` | RabbitMQ broker |
| `CELERY__WORKER_LOG_LEVEL` | `INFO` | Celery worker 日志级别 |
| `CELERY__BEAT_LOG_LEVEL` | `INFO` | Celery beat 日志级别 |
| `CELERY__WORKER_POOL` | `threads` | worker pool 类型 |
| `CELERY__WORKER_CONCURRENCY` | `1` | 单 worker 并行 task 数 |
| `CELERY__WORKER_REMOTE_CONTROL_ENABLED` | `false` | 是否启用 Celery remote control |
| `CELERY__WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS` | `true` | 连接丢失时是否取消长时间运行的任务 |

### Judge Celery（模块配置）

| 配置 | 默认值 | 说明 |
|---|---:|---|
| `JUDGE__TASK_DEFAULT_QUEUE` | `judge` | 默认消费队列 |
| `JUDGE__TASK_DEFAULT_ROUTING_KEY` | `judge.default` | 默认 routing key |
| `JUDGE__WORKER_PREFETCH_MULTIPLIER` | `4` | 每个执行槽预取任务数 |
| `JUDGE__TASK_SOFT_TIME_LIMIT` | `300` | 软超时（秒） |
| `JUDGE__TASK_TIME_LIMIT` | `600` | 硬超时（秒） |

生产建议：

- `JUDGE__WORKER_PREFETCH_MULTIPLIER` 默认 `4`，prefetch = concurrency × 4，适合大多数场景。
- 长任务/TLE 占比极高、多 worker 水平扩展时对公平性敏感，可降到 `1`。
- 多 worker 容器水平扩展通常比单容器无限提高 concurrency 更稳。

Celery result backend 使用 Redis（由 `REDIS__URL` 提供），通过 RedBeat 管理定时任务。

### sandbox pool

| 配置 | 默认值 | 说明 |
|---|---:|---|
| `JUDGE__SANDBOX_WORKER_POOL_SIZE` | `16` | 进程级 sandbox worker 池大小 |
| `JUDGE__SANDBOX_STANDARD_PARALLELISM` | `4` | STANDARD 单任务内多 case 并行度 |
| `JUDGE__SANDBOX_BORROW_TIMEOUT_SECONDS` | `0.25` | 满池时每次等待 slice |
| `JUDGE__SANDBOX_MAX_QUEUE_WAIT_SECONDS` | `0.0` | sandbox 借用总等待预算，`0` 表示不设总上限 |
| `JUDGE__SANDBOX_ALLOW_EMERGENCY_WORKER` | `false` | 满池时是否创建临时 worker |
| `JUDGE__SANDBOX_REQUEST_TIMEOUT_SECONDS` | `120.0` | 单次 sandbox worker 请求超时 |
| `JUDGE__SANDBOX_QUEUE_WAIT_WARN_SECONDS` | `0.5` | 借用等待超过该值时记录 warning |
| `JUDGE__SANDBOX_HEALTH_CHECK_TIMEOUT_SECONDS` | `1.0` | 健康检查超时 |

容量建议：

```text
SANDBOX_WORKER_POOL_SIZE >= WORKER_CONCURRENCY * SANDBOX_STANDARD_PARALLELISM
```

例如 `concurrency=8`、`standard_parallelism=4` 时，pool size 建议至少 `32`。

### 编译缓存

| 配置 | 默认值 | 说明 |
|---|---:|---|
| `JUDGE__SANDBOX_COMPILATION_CACHE_ENABLED` | `true` | 是否启用 sandbox 编译缓存 |
| `JUDGE__SANDBOX_COMPILATION_CACHE_DIR` | `/tmp/acoj-ccache` | 缓存目录 |
| `JUDGE__SANDBOX_COMPILATION_CACHE_MAX_MB` | `512` | LRU 容量上限 |
| `JUDGE__SANDBOX_COMPILATION_CACHE_TTL_SECONDS` | `3600` | TTL |

缓存由 `acoj-sandbox` 管理。编译缓存只恢复目标编译产物，SPJ/INTERACTIVE 的共享 workspace 不会被缓存中的其他文件覆盖。

结果缓存：使用 Redis RPC result backend（通过 `REDIS__URL`），默认 polling 间隔 100ms 降低 `AsyncResult.get()` 延迟。

### isolation / cgroup

| 配置 | 默认值 | 说明 |
|---|---:|---|
| `JUDGE__SANDBOX_ENABLE_NAMESPACES` | `false` | 是否启用 namespaces |
| `JUDGE__SANDBOX_ROOTFS_PATH` | 空 | rootfs 路径 |
| `JUDGE__SANDBOX_ISOLATE_NETWORK` | `true` | 网络 namespace |
| `JUDGE__SANDBOX_ISOLATE_IPC` | `true` | IPC namespace |
| `JUDGE__SANDBOX_ISOLATE_UTS` | `true` | UTS namespace |
| `JUDGE__SANDBOX_PRIVATE_MOUNTS` | `true` | private mount propagation |
| `JUDGE__SANDBOX_USE_PIVOT_ROOT` | `true` | 使用 pivot_root |
| `JUDGE__SANDBOX_BIND_WORKSPACE` | `true` | rootfs 模式下绑定 workspace |
| `JUDGE__SANDBOX_ENABLE_CGROUP` | `false` | 是否启用 cgroup |
| `JUDGE__SANDBOX_CGROUP_VERSION` | `auto` | `auto` / `v1` / `v2` |
| `JUDGE__SANDBOX_CGROUP_BASE_PATH` | `/sys/fs/cgroup/acoj-sandbox` | cgroup base path |
| `JUDGE__SANDBOX_CGROUP_V1_MEMORY_BASE_PATH` | 空 | v1 显式 memory controller 路径 |
| `JUDGE__SANDBOX_CGROUP_V1_PIDS_BASE_PATH` | 空 | v1 显式 pids controller 路径 |

生产建议开启 namespaces 和 cgroup。Docker 中通常需要 `--privileged --cgroupns=host` 或经验证的最小 capability 集合。
如果生产要收敛权限，需要逐项验证 capability、mount、cgroup 写权限和 namespace 创建能力。

### judge file cache

| 配置 | 默认值 | 说明 |
|---|---:|---|
| `JUDGE__CACHE_ENABLED` | `true` | 是否启用判题测试数据文件缓存 |
| `JUDGE__CACHE_DIR` | `storage/judge-cache` | 缓存目录 |
| `JUDGE__CACHE_MAX_MB` | `512` | LRU 容量上限 |
| `JUDGE__CACHE_TTL_SECONDS` | `604800`（7天） | TTL |

## 判题任务 payload

最小 STANDARD payload：

```json
{
  "submission_id": "sub-1",
  "judge_mode": "STANDARD",
  "problem": {
    "code": "demo",
    "time_limit_ms": 2000,
    "memory_limit_kb": 262144,
    "points": 100,
    "partial": false
  },
  "language": {
    "key": "cpp17",
    "name": "C++17",
    "extension": ".cpp",
    "compile_command": "/usr/bin/g++ -std=c++17 -O2 -o {exe} {source}",
    "run_command": "{exe}"
  },
  "source": "#include <iostream>\nint main(){std::cout<<\"ok\\n\";}",
  "test_cases": [
    {
      "case_no": 1,
      "points": 100,
      "time_limit_ms": 2000,
      "memory_limit_kb": 262144,
      "input_inline": "",
      "output_inline": "ok\n"
    }
  ]
}
```

发送任务：

```python
from app.platform.tasks.celery_app import celery_app

async_result = celery_app.send_task("judge.execute", args=[payload], queue="judge")
result = async_result.get(timeout=30)
```

返回结果形态：

```json
{
  "submission_id": "sub-1",
  "status": "COMPLETED",
  "result": "AC",
  "score": 100.0,
  "time_ms": 5,
  "memory_kb": 3456,
  "compile_output": "",
  "compile_error": false,
  "cases": [],
  "error": null,
  "wall_time_ms": 120
}
```

## 测试

基础单元测试：

```bash
PYTHONPATH=/path/to/acoj-sandbox/python:/path/to/acoj-worker \
python -m pytest tests/unit -q
```

sandbox 基础集成：

```bash
PYTHONPATH=/path/to/acoj-sandbox/python:/path/to/acoj-worker \
python -m pytest tests/test_sandbox.py -q
```

真实 Celery/RabbitMQ 集成测试需要先启动 RabbitMQ 和 Celery worker，然后运行：

```bash
PYTHONPATH=/path/to/acoj-sandbox/python:/path/to/acoj-worker \
python tests/test_all_judge_modes.py
```

测试矩阵：

| 文件 | 覆盖内容 | 依赖 |
|---|---|---|
| `tests/test_all_judge_modes.py` | STANDARD/SPJ/INTERACTIVE 全模式、全状态 | Worker + RabbitMQ |
| `tests/test_interactive.py` | INTERACTIVE AC/WA/RE 专项 | Worker + RabbitMQ |
| `tests/test_celery_pool.py` | pool 复用、并发、混合模式、Python | Worker + RabbitMQ |
| `tests/test_concurrent.py` | 基础并发和 TLE 隔离 | Worker + RabbitMQ |
| `tests/test_concurrent_extended.py` | burst 与混合并发扩展 | Worker + RabbitMQ |
| `tests/test_boundary.py` | 重复 ID、无效 payload、大源码 | Worker + RabbitMQ |
| `tests/test_boundary_extended.py` | Unicode、空源码、200 case、极端 limit | Worker + RabbitMQ |
| `tests/test_stability.py` | 多轮 AC/TLE 稳定性 | Worker + RabbitMQ |
| `tests/test_stress_extended.py` | 3 分钟脉冲、存活验证、混合 100 | Worker + RabbitMQ |
| `tests/unit/*` | case builder、checker、file cache、language config、pipeline、result mapper、sandbox config、schemas、scoring | pytest |

生产路径必须额外在目标 Docker/宿主环境执行 `acoj-sandbox` root integration，详见 [worker/sandbox 生产开发与部署指南](docs/worker-sandbox-production-validation.md)。

## 性能基准

`tests/run_benchmark.py` 是性能基准测试脚本，在真实 Celery + RabbitMQ + sandbox 环境下测量判题吞吐和延迟。

支持 C++（编译型）和 Python（解释型）两种语言对比，每种语言跑三种负载模式，
外加 C++ 三种判题模式（STANDARD / SPJ / INTERACTIVE）性能对比：

| 模式 | 说明 |
|------|------|
| Burst AC | 64 个 AC 任务并发发送，统计吞吐和延迟分布 |
| Sustained | 4 线程持续 60 秒发送 AC 任务，统计稳定吞吐 |
| Mixed | 20 AC + 3 TLE + 5 WA 混合负载，验证 TLE 不阻塞正常判题 |
| 判题模式对比 | 测试三种判题模式（STANDARD / SPJ / INTERACTIVE）在 C++ 和 Python 语言下的性能 |

运行完成后生成结果图表和 Markdown 表格：

```bash
# 先启动 Celery worker
celery -A app.worker.main:celery_app worker --pool threads --concurrency 4

# 另开终端运行基准测试
PYTHONPATH=/path/to/acoj-sandbox/python:/path/to/acoj-worker \
python tests/run_benchmark.py

# 生成图表和 Markdown 表格
python scripts/generate_benchmark_chart.py
```

结果写入 `docs/benchmark.png` 和 `docs/benchmark_result.json`。

### 基准测试结果

> **测试环境**：WSL2 (Debian), 16 核 CPU, 7.6GB 内存, Docker 容器 (`--privileged --cgroupns=host --network host`)，基础镜像 `acoj-worker-sec-test:patched` (Ubuntu 24.04, acoj-sandbox 本地编译), RabbitMQ 4.1.5, Redis 8.6.2  
> **Worker 配置**：`concurrency=4, prefetch_multiplier=4, pool_size=16, pool=threads`  
> **负载**：Burst AC=64 并发（同语言同时发送）, Sustained=4 线程持续 60s, Mixed=20AC+3TLE+5WA

![性能基准图表](docs/benchmark.png)

| 语言 | 测试 | 请求 | 成功 | 耗时(s) | 吞吐(req/s) | P50/P95/P99(ms) | 平均延迟(ms) |
|------|------|------|------|---------|-------------|-----------------|-------------|
| C++ | Burst AC | 64 | 64/0 | 5.99 | 10.69 | 4.9/72.3/1811.2 | 93.5 |
| C++ | Sustained | 6169 | 6169/0 | 60.03 | 102.77 | - | - |
| C++ | Mixed | 28 | AC=20 TLE=3 WA=5 | 7.4 | - | - | - |
| Python | Burst AC | 64 | 64/0 | 4.54 | 14.1 | 1.8/77.3/1865.0 | 70.9 |
| Python | Sustained | 5348 | 5348/0 | 60.01 | 89.12 | - | - |
| Python | Mixed | 28 | AC=20 TLE=3 WA=5 | 5.49 | - | - | - |
|判题模式对比|---|---|---|---|---|---|---|
| C++ | STANDARD(C++) | 16 | 16/0 | 0.16 | 97.11 | 4.2/35.7/60.5 | 10.3 |
| Python | STANDARD(Python) | 16 | 16/0 | 0.43 | 37.31 | 3.5/107.5/141.7 | 26.8 |
| C++ | SPJ(C++) | 16 | 16/0 | 1.94 | 8.24 | 4.1/476.5/1564.8 | 121.3 |
| Python | SPJ(Python) | 16 | 16/0 | 2.01 | 7.95 | 3.6/496.3/1612.3 | 125.7 |
| C++ | INTERACTIVE(C++) | 16 | 16/0 | 7.37 | 2.17 | 333.5/1139.0/2286.6 | 460.9 |
| Python | INTERACTIVE(Python) | 16 | 16/0 | 0.21 | 77.6 | 8.1/41.8/59.0 | 12.9 |

## Docker 部署

构建：

```bash
docker build -t acoj-worker .
```

镜像特点：

- 使用 `tini` 作为 init 进程，确保信号转发和僵尸进程回收。
- 入口为 `entrypoint.sh`（gunicorn + Celery worker + Celery beat 单容器模式）。
- Celery worker 默认消费 `judge` 队列。
- Gunicorn 使用 `UvicornWorker` 运行 ASGI 应用。
- 默认 `APP__DEBUG=false`、`APP__WORKERS=0`（按 CPU 自动计算）。
- Celery result backend 通过 Redis 提供。

API 容器（仅启动 API，不运行 Celery worker/beat）：

```bash
docker run -d --name acoj-api --env-file .env \
  -e APP__DEBUG=false \
  -p 8000:8000 \
  acoj-worker
```

Worker 容器示例（仅启动 Celery worker，不运行 API）：

```bash
docker run -d --name acoj-worker-1 --env-file .env \
  --privileged --cgroupns=host \
  -e APP__DEBUG=false \
  -e APP__PROCESS_ROLE=worker \
  acoj-worker
```

Beat 容器（仅启动 RedBeat 调度器）：

```bash
docker run -d --name acoj-beat --env-file .env \
  -e APP__PROCESS_ROLE=beat \
  acoj-worker
```

单容器全量启动（API + Worker + Beat）：

```bash
docker run -d --name acoj-all --env-file .env \
  --privileged --cgroupns=host \
  -p 8000:8000 \
  acoj-worker
```

部署注意：

- 所有 worker 使用同一个 `CELERY__BROKER_URL`。
- Beat 必须单副本，RedBeat 通过 Redis 锁保证只有一个实例持有锁。
- 多实例部署时 `ID_GENERATOR__WORKER_ID` 应按实例规划。
- 判题 worker 建议和 API/DB 隔离部署。
- root 权限、cgroup、rootfs、挂载白名单必须在目标镜像里真实验证。
- `--privileged --cgroupns=host` 是最容易验证通过的 Docker 配置。如果生产要收敛权限，需要逐项验证 capability、mount、cgroup 写权限和 namespace 创建能力。

## 项目结构

```text
app/
  api/                 API 版本装配入口
  core/                配置、安全、日志、异常、统一响应
  deps/                FastAPI 依赖注入
  middleware/          中间件
  modules/judge/       判题 pipeline、mode、语言配置、数据加载、计分
  platform/
    cache/             Redis 缓存客户端
    db/                SQLAlchemy 异步会话、基模型、审计、事务
    email/             邮件发送
    http/              共享 httpx 异步客户端
    id_generator/      雪花 ID 生成器
    module/            模块自动发现系统
    observability/     metrics/tracing/logging
    storage/           本地/S3/MinIO/OSS 存储与 judge file cache
    tasks/             Celery app、RedBeat、async runner
scripts/               开发、测试、迁移和 seed 辅助脚本
migrations/            Alembic 数据库迁移
docs/
  migration.md
  worker-sandbox-production-validation.md
tests/
  unit/                单元测试
  test_*.py            真实 Celery/RabbitMQ 集成测试
```

## 相关文档

- [MQ 数据协议说明](docs/mq-protocol.md)
- [worker/sandbox 生产开发与部署指南](docs/worker-sandbox-production-validation.md)
- `acoj-sandbox/docs/production.md`
- `acoj-sandbox/docs/testing.md`
- `acoj-sandbox/docs/usage.md`

## License

MIT License。详见 [LICENSE](LICENSE)。
