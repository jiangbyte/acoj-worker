# 数据库迁移

本项目使用 Alembic 管理数据库结构迁移。迁移只负责表、字段、索引、约束等结构变更，不负责初始化
业务数据。超管账号、初始角色等业务数据由独立 seed 脚本处理。

## 配置来源

迁移使用后端配置中的 `DB__URL`。配置优先级：

```text
真实环境变量 > .env / .env.local > settings.py 默认值
```

本地开发建议把个人数据库连接写在 `.env.local`，避免修改公共 `.env`。

当前项目按 PostgreSQL 生成和验证迁移，不使用 SQLite 生成迁移。

## 执行迁移

源码环境：

```bash
python scripts/migrate.py
```

等价命令：

```bash
alembic upgrade head
```

Docker 后端镜像没有复制 `scripts/`，镜像内应使用 Alembic 命令：

```bash
docker run --rm \
  --env-file .env \
  hei-fastapi-backend \
  python -m alembic upgrade head
```

后端容器不会自动执行迁移。首次部署或升级表结构前，应先执行迁移，再启动 API / worker / beat。

## 自动生成结构迁移

表结构变化后，先修改 SQLAlchemy model，再生成迁移：

```bash
python scripts/makemigration.py "describe schema change"
```

生成后必须人工检查 `migrations/versions/*.py`，确认只包含结构操作，例如：

- `op.create_table`
- `op.add_column`
- `op.alter_column`
- `op.create_index`
- `op.create_unique_constraint`
- `op.drop_table`
- `op.drop_column`
- `op.drop_index`

禁止在 migration 里写业务数据操作：

- `op.bulk_insert`
- `op.execute` 写入业务数据
- `insert/update/delete` seed 或修复业务数据
- 默认管理员、角色、字典、Banner 等初始化数据

检查无误后执行：

```bash
python scripts/migrate.py
python scripts/check_migration.py
```

`check_migration.py` 用于确认当前数据库结构和 SQLAlchemy model 没有未生成的结构差异。

## 重建初始迁移

如果项目早期还没有稳定发布，想清空 `migrations/versions` 并重新生成一份全新的初始迁移，不要直接拿
已有开发库生成。已有库里已经有业务表，Alembic 会把它当作“当前结构”，生成结果会不正确。

推荐使用脚本通过临时空库生成：

```bash
python scripts/rebuild_initial_migration.py --yes
```

脚本会：

1. 清空 `migrations/versions/*.py`。
2. 创建临时空库。
3. 生成 `initial schema`。
4. 执行迁移。
5. 执行结构差异检查。
6. 默认删除临时库。

默认临时库名是 `hei_fastapi_migration_shadow`，连接账号、密码、主机和端口来自当前 `DB__URL`。

常用参数：

```bash
python scripts/rebuild_initial_migration.py --yes -m "initial schema"
python scripts/rebuild_initial_migration.py --yes --shadow-db hei_fastapi_migration_tmp
python scripts/rebuild_initial_migration.py --yes --keep-db
```

重建初始迁移后，旧开发库里的 `alembic_version` 会指向已经删除的旧 revision。要迁移旧开发库，最干净的
方式是删除并重建数据库，再执行：

```bash
python scripts/migrate.py
```

如果旧库里有需要保留的数据，不要重建初始迁移；应走增量迁移流程。

## 新开发库初始化

空库初始化：

```bash
python scripts/migrate.py
python scripts/seed_super_admin.py
```

如果需要重建本地开发库，先删除并重新创建 PostgreSQL 数据库，再执行迁移和 seed：

```bash
dropdb hei_fastapi
createdb hei_fastapi
python scripts/migrate.py
python scripts/seed_super_admin.py
```

如果本地没有 `dropdb/createdb` 命令，也可以用数据库管理工具删除并重建 `DB__URL` 指向的数据库。

## Seed 数据

需要初始化超管时使用：

```bash
python scripts/seed_super_admin.py
```

默认账号、密码、昵称、邮箱和手机号可以通过脚本参数或环境变量覆盖：

```bash
python scripts/seed_super_admin.py --help
```

当前后端 Docker 镜像没有复制 `scripts/`。如果要在容器内 seed，需要自行扩展镜像或挂载源码脚本；否则在
源码环境执行 seed。

## 常见问题

`Target database is not up to date`：

当前数据库没有升级到最新 migration。先执行：

```bash
python scripts/migrate.py
```

然后再生成新的迁移。

生成的 migration 为空：

说明当前 model 和数据库结构没有检测到差异。可以运行：

```bash
python scripts/check_migration.py
```

确认是否已经一致。

Docker 容器内找不到 `scripts/migrate.py`：

这是预期行为。后端镜像只复制 `app/`、`migrations/`、`alembic.ini` 等运行必需文件。容器内迁移使用：

```bash
python -m alembic upgrade head
```

需要初始化数据：

不要写进 Alembic migration。当前超管初始化使用独立脚本：

```bash
python scripts/seed_super_admin.py
```
