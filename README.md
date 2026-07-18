# ACOJ Worker — 判题服务节点

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116%2B-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supported-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-6.2%2B-DC382D?logo=redis&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-Supported-FF6600?logo=rabbitmq&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

ACOJ Worker 是 ACOJ 在线判题系统的**判题服务节点**，负责接收判题任务、在沙箱中执行代码评测并返回结果。支持多节点部署，通过 RabbitMQ + Celery 进行任务调度。

沙箱执行基于 [acoj-sandbox](https://github.com/jiangbyte/acoj-sandbox) — 一个带 seccomp、cgroup、namespace 隔离的 C++ 原生沙箱。

技术底座基于 [hei-fastapi](https://github.com/jiangbyte/hei-fastapi) 全栈脚手架。

## 功能概览

- **判题执行**：在沙箱中编译运行用户代码，对时间、内存、输出进行限制和度量。
- **多语言支持**：通过 `acoj-sandbox` 的语言配置支持 C/C++、Python、Java 等。
- **多节点调度**：通过 RabbitMQ + Celery 分发判题任务到多个 Worker 节点。
- **异步任务**：Celery worker 消费判题任务，支持定时任务调度。
- **可观测性**：结构化日志、Prometheus metrics、OpenTelemetry tracing。

## 运行要求

- Python 3.11+
- PostgreSQL
- Redis
- RabbitMQ
- **acoj-sandbox**：沙箱执行引擎（需要 C++20 编译器、make、libseccomp-dev）

## 快速启动

```bash
# 安装 acoj-sandbox（需要在本地编译 C++ 二进制）
pip install /path/to/acoj-sandbox

# 安装 Worker
pip install -e ".[postgres]"
cp .env.example .env
vim .env
python scripts/dev.py
```

`.env.example` 是带注释的配置模板，复制后需要按本机环境取消注释并填写 `DB__URL`、`REDIS__URL`、`CELERY__BROKER_URL` 等关键项。

默认后端地址为 `http://127.0.0.1:8000`，接口文档为 `/docs`。

## 常用命令

```bash
python scripts/dev.py          # 启动开发服务器
python scripts/test.py         # 运行测试
python scripts/lint.py         # 代码检查
python scripts/migrate.py      # 执行数据库迁移
python scripts/makemigration.py "describe change"   # 生成迁移
```

## 配置

后端配置使用 `pydantic-settings`，支持嵌套环境变量，分隔符为 `__`。

常用配置项：

- `APP__HOST` / `APP__PORT`：监听地址和端口。
- `APP__DEBUG`：开发模式，开启时 Uvicorn reload 生效。
- `APP__WORKERS`：API worker 数，`0` 表示按 CPU 自动计算。
- `DB__URL`：数据库连接地址（PostgreSQL asyncpg）。
- `REDIS__URL`：Redis 地址，用于会话和缓存。
- `CELERY__BROKER_URL`：RabbitMQ broker 地址。
- `CELERY__AUTO_START_ENABLED`：是否由 API 进程内嵌自启动 Celery worker/beat。
- `MQ__ENABLED`：是否启用 RabbitMQ consumer。
- `STORAGE__PROVIDER`：文件存储方式，可选 `local`、`minio`、`s3`、`oss`。
- `OBSERVABILITY__ENABLED`：可观测性总开关。

本地开发示例：

```env
APP__DEBUG=true
APP__WORKERS=1
REDIS__URL=redis://127.0.0.1:6379/0
CELERY__AUTO_START_ENABLED=true
CELERY__BROKER_URL=amqp://admin:123456@127.0.0.1:5672//
STORAGE__PROVIDER=local
OBSERVABILITY__ENABLED=false
```

## Docker 部署

```bash
docker build -t acoj-worker .
```

Worker 节点按角色拆分：

- **API**：接收判题请求，可多副本部署。
- **Worker**：消费 RabbitMQ 队列中的判题任务，可多副本部署。
- **Beat**：定时任务调度，必须单副本。

API 容器：

```bash
docker run -d --name acoj-api --env-file .env \
  -e APP__DEBUG=false -e CELERY__AUTO_START_ENABLED=false \
  -p 8000:8000 acoj-worker
```

Worker 容器：

```bash
docker run -d --name acoj-worker-1 --env-file .env \
  -e CELERY__AUTO_START_ENABLED=false \
  acoj-worker \
  python -m celery -A app.platform.tasks.celery_app worker --without-mingle --without-gossip --loglevel INFO --pool solo --concurrency 1
```

Beat 容器：

```bash
docker run -d --name acoj-beat --env-file .env \
  -e CELERY__AUTO_START_ENABLED=false \
  acoj-worker \
  python -m celery -A app.platform.tasks.celery_app beat --loglevel INFO --schedule /app/.runtime/celerybeat-schedule
```

多副本注意事项：

- 所有节点必须使用同一组 `DB__URL`、`REDIS__URL`、`CELERY__BROKER_URL`。
- Beat 必须单副本，避免重复投递定时任务。
- 多实例部署时 `ID_GENERATOR__WORKER_ID` 应按实例规划，避免雪花 ID 冲突。

## 项目结构

```text
app/
  api/          API 路由聚合入口
  core/         配置、安全、日志、异常、统一响应
  deps/         FastAPI 依赖注入
  middleware/   中间件（日志、链路、CORS、上下文）
  modules/      业务模块（判题模块在此扩展）
  platform/     DB、Redis、HTTP、Celery、MQ、存储、可观测性等基础设施
migrations/     Alembic 数据库迁移
scripts/        开发、测试、迁移辅助脚本
tests/          测试
```

## 模块扩展

新增业务模块放在 `app/modules/<module_name>` 下：

```text
app/modules/example/
  __init__.py
  module.py     # ModuleSpec 声明
  model.py      # SQLAlchemy 模型
  schema.py     # Pydantic 请求/响应对象
  repository.py # 数据访问
  service.py    # 业务逻辑
  router.py     # FastAPI 路由
  tasks.py      # Celery 任务（可选）
```

`module.py` 示例：

```python
from app.platform.module import ModuleSpec, RouteSpec

module = ModuleSpec(
    name="example",
    routes=(
        RouteSpec(
            version="v1",
            prefix="/judge",
            tags=("judge",),
            router="app.modules.example.router:router",
        ),
    ),
    models=("app.modules.example.model",),
    startup_hooks=("app.modules.example.lifecycle:startup",),
    shutdown_hooks=("app.modules.example.lifecycle:shutdown",),
)
```

运行时路径规则：
- `GET /` — 健康检查
- `/api/v1/*` — 业务接口，按 `ModuleSpec` 自动装配

## 相关项目

- [acoj](https://github.com/jiangbyte/acoj) — ACOJ 完整系统（API 服务端、Web 管理端/门户端、uni-app 多端应用）
- [acoj-sandbox](https://github.com/jiangbyte/acoj-sandbox) — 沙箱执行引擎（本项目的判题核心依赖）
- [hei-fastapi](https://github.com/jiangbyte/hei-fastapi) — 全栈脚手架基础

## License

MIT License。详见 [LICENSE](LICENSE)。
