# Worker / Sandbox 生产开发与部署指南

本文档面向 `acoj-worker` 与 `acoj-sandbox` 的联调、部署、压测和运维，是当前代码结构下的长期开发手册。

适用范围：

- `acoj-worker` 通过 Celery/RabbitMQ 消费判题任务。
- `acoj-worker` 通过 `acoj-sandbox` Python 包和 `acosandbox` C++ binary 执行代码。
- 生产环境在 Linux/Docker 中开启 seccomp、namespaces、cgroup 和可选 rootfs。

## 架构

```text
API / producer / test client
  -> RabbitMQ judge queue
  -> Celery task judge.execute
  -> app.modules.judge.orchestrator.judge()
  -> mode: STANDARD / SPECIAL_JUDGE / INTERACTIVE
  -> SandboxClient
  -> process-wide SandboxWorkerPool
  -> acosandbox worker JSONL protocol
  -> user program / checker / interactor
```

职责边界：

- 判题结果通过 Celery task result 返回。
- `acoj-sandbox` 不负责 OJ 业务计分、答案比对和任务队列；这些在 worker judge mode 中完成。
- `acoj-sandbox` 负责执行、隔离、资源限制、计量、状态映射和 Python 底层封装。

## 代码地图

### worker

| 文件 | 职责 |
|---|---|
| `app/modules/judge/tasks.py` | Celery task `judge.execute` |
| `app/modules/judge/orchestrator.py` | 判题模式分发，统一兜底失败结果 |
| `app/modules/judge/modes/standard.py` | STANDARD: ACM/OI/IOI |
| `app/modules/judge/modes/spj.py` | SPECIAL_JUDGE: 用户程序 + checker |
| `app/modules/judge/modes/interactive.py` | INTERACTIVE: 用户程序 + interactor + FIFO |
| `app/modules/judge/case_builder.py` | 构造 JudgeCase，提取期望输出 |
| `app/modules/judge/checker.py` | 输出比对（忽略行尾空白） |
| `app/modules/judge/data_loader.py` | 从本地/远端存储加载测试数据 |
| `app/modules/judge/file_cache.py` | 判题测试数据文件缓存 |
| `app/modules/judge/language_config.py` | 从 payload language dict 构建 `LanguagesConfig` |
| `app/modules/judge/pool_metrics.py` | sandbox worker pool 指标采集 |
| `app/modules/judge/result_mapper.py` | 映射 sandbox 结果到 OJ 状态码 |
| `app/modules/judge/sandbox_config.py` | isolation/cgroup/client/pool/cache 配置 |
| `app/modules/judge/schemas.py` | 判题输入/输出 Pydantic 模型 |
| `app/modules/judge/scoring.py` | IOI 子任务计分、依赖解析 |
| `app/modules/judge/module.py` | ModuleSpec 声明 |
| `app/platform/tasks/celery_app.py` | Celery app、队列、prefetch、result backend |
| `app/platform/tasks/autostart.py` | API 进程内自启动 Celery worker/beat |
| `app/platform/tasks/base.py` | 基类 task |
| `app/platform/tasks/scheduler.py` | beat schedule 管理 |

### sandbox

| 文件 | 职责 |
|---|---|
| `python/acoj_sandbox/client.py` | `SandboxClient`、worker pool、批量运行、SPJ helper |
| `python/acoj_sandbox/compilation_cache.py` | 编译缓存、TTL/LRU、跨线程/进程锁 |
| `python/acoj_sandbox/languages.py` | 语言配置 API |
| `python/acoj_sandbox/result.py` | `Status`、`Stage`、`ProcessResult`、`JudgeResult` |
| `src/main.cpp` | CLI 入口：judge/batch/run/languages/self-test/worker |
| `src/judge.cpp` | C++ 判题执行流程、workspace、编译/运行阶段 |
| `src/runner.cpp` | fork/exec、rlimit、seccomp、namespace、cgroup |
| `src/json_io.cpp` | JSON 序列化/反序列化 |
| `src/language.cpp` | 命令展开、变量替换、可执行文件解析 |
| `src/seccomp_profiles.cpp` | 内置 seccomp BPF profile |
| `tests/run_root_integration.py` | root/namespaces/cgroup/rootfs 生产路径验证 |

## 部署基线

### RabbitMQ / Celery

生产 worker 必须显式使用 Celery worker 进程，不建议依赖 API 进程内 autostart：

```bash
CELERY__AUTO_START_ENABLED=false \
python -m celery -A app.platform.tasks.celery_app:celery_app worker \
  -Q judge \
  --pool threads \
  --concurrency 8 \
  --without-mingle \
  --without-gossip \
  --loglevel INFO
```

推荐起步配置：

```env
CELERY__BROKER_URL=amqp://user:password@rabbitmq:5672//
CELERY__RESULT_BACKEND=rpc://
CELERY__WORKER_POOL=threads
CELERY__WORKER_CONCURRENCY=8
CELERY__WORKER_PREFETCH_MULTIPLIER=1
CELERY__WORKER_REMOTE_CONTROL_ENABLED=false
CELERY__WORKER_CANCEL_LONG_RUNNING_TASKS_ON_CONNECTION_LOSS=true
```

prefetch 选择：

- `1`：生产默认推荐，长任务/TLE 多时更公平，避免单 worker 预取太多长任务。
- `2-4`：短任务多、吞吐优先时可提高，需要监控队列等待和 worker 间公平性。

### sandbox pool

推荐起步配置：

```env
CELERY__SANDBOX_WORKER_POOL_SIZE=32
CELERY__SANDBOX_STANDARD_PARALLELISM=4
CELERY__SANDBOX_BORROW_TIMEOUT_SECONDS=0.25
CELERY__SANDBOX_MAX_QUEUE_WAIT_SECONDS=0.0
CELERY__SANDBOX_ALLOW_EMERGENCY_WORKER=false
CELERY__SANDBOX_REQUEST_TIMEOUT_SECONDS=120
CELERY__SANDBOX_QUEUE_WAIT_WARN_SECONDS=0.5
CELERY__SANDBOX_HEALTH_CHECK_TIMEOUT_SECONDS=1
```

容量公式：

```text
sandbox_worker_pool_size >= worker_concurrency * sandbox_standard_parallelism
```

示例：

```text
8 * 4 = 32
```

`sandbox_max_queue_wait_seconds` 语义：

- `0.0`：不设置总排队上限，满池时持续按 `borrow_timeout` 分片等待。
- `>0`：设置借用 sandbox worker 的总等待预算，超过后抛 `SandboxQueueTimeout`。

生产默认建议保持 `0.0`，让超出能力的请求在 RabbitMQ/Celery/sandbox pool 中排队。如果业务需要 SLA，可以设置为 `30-60` 秒，并在上层把 timeout 映射为可重试或系统繁忙。

### 编译缓存

推荐开启：

```env
CELERY__SANDBOX_COMPILATION_CACHE_ENABLED=true
CELERY__SANDBOX_COMPILATION_CACHE_DIR=/tmp/acoj-ccache
CELERY__SANDBOX_COMPILATION_CACHE_MAX_MB=512
CELERY__SANDBOX_COMPILATION_CACHE_TTL_SECONDS=3600
```

实现要点：

- cache key 包含 source、language fingerprint、source filename、extra files、variables。
- cache 写入使用临时目录和 `os.replace()`。
- same-key 编译由线程锁 + 文件锁串行化。
- 编译缓存只缓存/恢复目标可执行产物，避免恢复整个 workspace。

生产建议：

- cache 目录放本机磁盘，不放高延迟网络盘。
- 容器重启可以丢 cache，cache 只影响性能，不应影响正确性。
- 监控 cache restore failed 和 cache size。

### isolation / cgroup

生产建议：

```env
CELERY__SANDBOX_ENABLE_NAMESPACES=true
CELERY__SANDBOX_ISOLATE_NETWORK=true
CELERY__SANDBOX_ISOLATE_IPC=true
CELERY__SANDBOX_ISOLATE_UTS=true
CELERY__SANDBOX_PRIVATE_MOUNTS=true
CELERY__SANDBOX_USE_PIVOT_ROOT=true
CELERY__SANDBOX_BIND_WORKSPACE=true
CELERY__SANDBOX_ENABLE_CGROUP=true
CELERY__SANDBOX_CGROUP_VERSION=auto
CELERY__SANDBOX_CGROUP_BASE_PATH=/sys/fs/cgroup/acoj-sandbox
```

rootfs：

```env
CELERY__SANDBOX_ROOTFS_PATH=/var/lib/acoj-sandbox/rootfs/cpp
```

如果 `ENABLE_NAMESPACES=true` 但 `ROOTFS_PATH` 为空，worker 会记录生产硬化 warning。可以用于灰度，但正式生产应明确 rootfs 策略。

## Docker 部署

### Worker 容器

示例：

```bash
docker run -d --name acoj-worker-1 \
  --env-file .env \
  --privileged \
  --cgroupns=host \
  -e APP__DEBUG=false \
  -e CELERY__AUTO_START_ENABLED=false \
  -e CELERY__WORKER_POOL=threads \
  -e CELERY__WORKER_CONCURRENCY=8 \
  -e CELERY__WORKER_PREFETCH_MULTIPLIER=1 \
  -e CELERY__SANDBOX_WORKER_POOL_SIZE=32 \
  -e CELERY__SANDBOX_ENABLE_NAMESPACES=true \
  -e CELERY__SANDBOX_ENABLE_CGROUP=true \
  acoj-worker \
  python -m celery -A app.platform.tasks.celery_app:celery_app worker \
    -Q judge \
    --pool threads \
    --concurrency 8 \
    --without-mingle \
    --without-gossip \
    --loglevel INFO
```

说明：

- `--privileged --cgroupns=host` 是最容易验证通过的 Docker 配置。
- 如果生产要收敛权限，需要逐项验证 capability、mount、cgroup 写权限和 namespace 创建能力。
- worker 容器应与 API/DB 分离部署。

### 重新编译安装 sandbox

每次更新 `acoj-sandbox` 后，生产镜像必须重新构建或在镜像内重新安装。验证环境使用全新的 `--target` 安装目录。

验证安装示例：

```bash
install_dir=/tmp/acoj-sandbox-install-$(date +%s)
python3 -m pip install /src/acoj-sandbox \
  --target "$install_dir" \
  --no-deps \
  --no-build-isolation
```

启动前确认加载的新版本支持 selected-path cache：

```bash
PYTHONPATH="$install_dir" python3 - <<'PY'
import inspect
import acoj_sandbox.compilation_cache as cc
print(inspect.signature(cc.restore))
PY
```

期望包含：

```text
paths: list[str] | tuple[str, ...] | None = None
```

## 判题模式开发指南

### STANDARD

入口：`app/modules/judge/modes/standard.py`

流程：

1. 从 payload 构建 `LanguagesConfig`。
2. 从 test cases 构建 sandbox `JudgeCase`。
3. 调用 `client.run_cases()`。
4. 基于 sandbox status 和 output compare 映射 OJ result。
5. 根据 ACM/OI/IOI 规则聚合分数。

注意：

- `run_cases(stop_on_first_failure=False)` 会执行所有 submitted cases；ACM 的首错跳过由 worker 层生成 `SKIPPED`。
- `sandbox_standard_parallelism` 控制单任务内部 case 并行度。
- 输出比对在 worker 层，不在 sandbox 层。

### SPECIAL_JUDGE

入口：`app/modules/judge/modes/spj.py`

流程：

1. 编译用户程序。
2. 编译 checker。
3. per-case 运行用户程序。
4. 复用 `prepared_checker` 调用 `run_testlib_checker()`。
5. worker 层解释 checker exit code 和 accepted。

注意：

- checker 编译一次，多 case 复用。
- 用户 RE/TLE 当前映射为非 AC case；如需区分为 RE/TLE，可在 SPJ mode 中扩展结果优先级。

### INTERACTIVE

入口：`app/modules/judge/modes/interactive.py`

流程：

1. 用户程序和 interactor 在同一 workspace 编译。
2. 创建两条 FIFO：
   - user stdout -> interactor stdin
   - interactor stdout -> user stdin
3. 主进程先以 `O_RDWR` 打开 FIFO holder，避免子进程 open 阻塞。
4. 用户程序和 interactor 并行运行。
5. 任一侧先异常结束时关闭 FIFO holder，让另一侧快速 EOF/退出。

注意：

- 交互模式使用 `FIRST_COMPLETED`，异常路径不会等待完整 real-time timeout。
- interactor exit code `0` 表示 AC，`1` 表示 WA。
- `exit_codes_ok=[0, 1]` 让 sandbox 不把 interactor 的 WA exit code 当作 RE。

## 资源清理

### workspace

worker mode 必须保证：

- `PreparedProgram.close()` 在 `finally` 中执行。
- `SandboxClient.close()` 在 `finally` 中执行。
- 手动创建的临时 workspace 使用 `shutil.rmtree(..., ignore_errors=True)` 清理。
- FIFO fd 在所有路径关闭。

如果进程被 `SIGKILL`，Python `finally` 不执行，生产容器启动时应清理残留的 `/tmp/acoj-*` workspace。

### sandbox worker pool

`SandboxWorkerPool` 行为：

- worker 借出后不在 queue 中。
- 请求结束后归还。
- dead worker / request count 接近阈值时 recycle。
- request timeout 会 close 当前 worker。
- emergency worker 生产默认关闭。

### cgroup

生产必须验证：

- cgroup base path 可创建。
- memory/pids limit 可写入。
- `cgroup.procs` 可写入。
- 任务结束后 cgroup 子目录可清理。

## 安全基线

必须做：

- 生产运行阶段禁用网络。
- 开启 seccomp。
- 开启 cgroup。
- 对每个任务使用独立 workspace。
- workspace path 必须在 sandbox 校验范围内。
- 不把宿主敏感目录挂进 rootfs。
- 编译器、解释器、运行时库通过 rootfs/bind mount 白名单提供。

建议做：

- 判题 worker 与业务 API、DB、对象存储访问权限隔离。
- 使用专用 runner 节点。
- cgroup base path 按 worker 容器隔离。
- rootfs 按语言拆分。
- 定期清理 `/tmp/acoj-*` 和 cache。

## 监控与告警

必须监控：

- RabbitMQ `judge` queue messages。
- RabbitMQ `judge` consumers。
- Celery task runtime、failure rate、retry/lost。
- sandbox pool active/available/waiting。
- sandbox borrow avg/max wait。
- sandbox queue timeout count。
- sandbox worker replaced count。
- verdict 分布：AC/WA/CE/RE/TLE/MLE/OLE/SE/IE。
- compile cache hit/miss、restore failed、cache size。
- Docker CPU/memory/pids。
- `/tmp` 与 cache 磁盘空间。

建议告警：

- `judge` 队列持续增长超过 5 分钟。
- sandbox borrow max wait 持续超过 1 秒。
- `SE` 或 `IE` 比例突增。
- cgroup 创建/清理错误。
- worker replaced count 突增。
- cache restore failed 持续出现。

## 测试与验收

### 单元测试

```bash
PYTHONPATH=/path/to/acoj-sandbox/python:/path/to/acoj-worker \
python -m pytest tests/unit -q
```

### worker 基础 sandbox 集成

```bash
PYTHONPATH=/path/to/acoj-sandbox/python:/path/to/acoj-worker \
python -m pytest tests/test_sandbox.py -q
```

### sandbox 编译缓存

```bash
PYTHONPATH=/path/to/acoj-sandbox/python:/path/to/acoj-sandbox/tests \
python -m pytest \
  /path/to/acoj-sandbox/tests/test_compilation_cache.py \
  /path/to/acoj-sandbox/tests/test_compilation_cache_integration.py \
  -q
```

### Docker root integration

必须在目标 Docker/宿主环境执行：

```bash
cd /path/to/acoj-sandbox
make clean all
sudo python3 tests/run_root_integration.py \
  --binary build/acosandbox \
  --enable-namespaces \
  --enable-cgroup \
  --cgroup-version auto
```

Docker 中常用：

```bash
docker run --rm --privileged --cgroupns=host \
  -v /path/to/acoj-sandbox:/src:ro \
  acoj-test \
  bash -lc 'cp -a /src /work/acoj-sandbox && cd /work/acoj-sandbox && make clean all && python3 tests/run_root_integration.py --binary build/acosandbox --enable-namespaces --enable-cgroup --cgroup-version auto'
```

### 真实 Celery/RabbitMQ 集成

启动 worker 后运行：

```bash
export CELERY__BROKER_URL=amqp://admin:123456@127.0.0.1:5672//
export CELERY__RESULT_BACKEND=rpc://
export CELERY__AUTO_START_ENABLED=false
export PYTHONPATH=/path/to/acoj-sandbox/python:/path/to/acoj-worker

python tests/test_all_judge_modes.py
python tests/test_interactive.py
python tests/test_celery_pool.py
python tests/test_concurrent.py
python tests/test_concurrent_extended.py
python tests/test_boundary.py
python tests/test_boundary_extended.py
python tests/test_stability.py
python tests/test_stress_extended.py
```

测试完成后确认：

```bash
docker exec rabbitmq rabbitmqctl list_queues name messages consumers
```

期望：

```text
judge 0 0
```

如果测试 worker 仍在运行，则 consumers 为 `1` 是正常的；验收结束应关闭测试 worker。

### 参考验收矩阵

| 测试 | 期望 |
|---|---|
| sandbox root integration | passed |
| `tests/test_all_judge_modes.py` | 24/24 |
| `tests/test_interactive.py` | AC/WA/RE all passed |
| `tests/test_celery_pool.py` | 51/51 |
| `tests/test_concurrent.py` | 22/22 |
| `tests/test_concurrent_extended.py` | 180/180 |
| `tests/test_boundary.py` | 7/7 |
| `tests/test_boundary_extended.py` | 11/11 |
| `tests/test_stability.py` | 4/4 |
| `tests/test_stress_extended.py` | 5/5 |
| sandbox compilation cache tests | 9 passed |
| worker pipeline/config unit tests | 12 passed |

## 常见问题

### worker 超出并行能力为什么不直接报错？

正确行为是排队。

排队发生在三层：

1. RabbitMQ 中等待 Celery worker 消费。
2. Celery worker 已预取但等待执行槽。
3. task 内部等待 sandbox worker pool。

`sandbox_max_queue_wait_seconds=0.0` 表示 sandbox pool 不设置总等待上限，满池时持续按等待 slice 排队。

### 为什么 interactive RE/WA 不应等待十几秒？

交互模式中，如果一侧已经异常结束，另一侧通常阻塞在 FIFO 读写。worker 会关闭 FIFO holder fd，让另一侧尽快收到 EOF 或 broken pipe，只保留 1 秒收尾时间。

### 为什么生产建议 prefetch=1？

判题任务耗时差异很大。prefetch 过高时，一个 worker 可能预取多个 TLE/长任务，导致其他 worker 空闲但队列任务已被占住。`1` 更公平，`2-4` 适合短任务吞吐优化。

### 为什么 Docker 中 Celery 会提示 root 运行风险？

sandbox 的 namespace/cgroup/rootfs 操作通常需要 root 或等价 capability。短期可在专用 runner 容器中接受该模式；长期建议拆分最小权限 helper 或专用 runner 节点。

### 为什么更新 sandbox 后必须重新安装？

Python 包和 C++ binary 都可能变化。生产镜像应重新构建，验证环境应使用全新安装目录。
