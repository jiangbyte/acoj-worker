# 数据库迁移说明

本目录保存 Alembic 迁移文件。迁移只管理数据库结构，不写入业务种子数据。

## 执行迁移

源码环境：

```bash
python scripts/migrate.py
```

等价命令：

```bash
alembic upgrade head
```

Docker 后端镜像没有复制 `scripts/`，镜像内执行迁移应使用：

```bash
docker run --rm \
  --env-file .env \
  hei-fastapi-backend \
  python -m alembic upgrade head
```

迁移使用后端配置中的 `DB__URL`。配置优先级：

```text
真实环境变量 > .env / .env.local > settings.py 默认值
```

当前项目按 PostgreSQL 生成和验证迁移，不使用 SQLite 生成迁移。

## 自动生成结构迁移

修改 SQLAlchemy model 后生成迁移：

```bash
python scripts/makemigration.py "describe schema change"
```

生成后必须检查 `migrations/versions/*.py`，确认只包含结构操作，例如：

- `op.create_table`
- `op.add_column`
- `op.alter_column`
- `op.create_index`
- `op.create_unique_constraint`
- `op.drop_table`
- `op.drop_column`
- `op.drop_index`

禁止在 migration 中写业务数据操作，例如 seed 默认管理员、角色、字典、Banner 等。

检查无误后执行：

```bash
python scripts/migrate.py
python scripts/check_migration.py
```

## 重建初始迁移

项目早期如果要清空 `migrations/versions` 并重新生成完整初始迁移，使用临时空库脚本：

```bash
python scripts/rebuild_initial_migration.py --yes
```

脚本会清空 `migrations/versions/*.py`，创建临时空库，生成 `initial schema`，再执行迁移和结构差异检查。
默认临时库名是 `hei_fastapi_migration_shadow`，连接账号、密码、主机和端口来自当前 `DB__URL`。

常用参数：

```bash
python scripts/rebuild_initial_migration.py --yes -m "initial schema"
python scripts/rebuild_initial_migration.py --yes --shadow-db hei_fastapi_migration_tmp
python scripts/rebuild_initial_migration.py --yes --keep-db
```

重建初始迁移后，旧开发库里的 `alembic_version` 会指向已经删除的旧 revision。最干净的处理方式是删除并
重建开发库，再执行：

```bash
python scripts/migrate.py
```

如果旧库里有需要保留的数据，不要重建初始迁移，应走增量迁移流程。

## 初始化数据

初始化超管使用独立 seed 脚本：

```bash
python scripts/seed_super_admin.py
```

默认账号、密码、昵称、邮箱和手机号可以通过脚本参数或环境变量覆盖：

```bash
python scripts/seed_super_admin.py --help
```

不要把 seed 数据写进 Alembic migration。

当前后端 Docker 镜像没有复制 `scripts/`。如果要在容器内 seed，需要自行扩展镜像或挂载源码脚本；否则在
源码环境执行 seed。

## 更多说明

完整流程见 [docs/migration.md](../docs/migration.md)。




```bash
# 完整的一键迁移脚本（包含强制断开连接）
docker exec -e PGPASSWORD=123456 -it postgres psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'hei_fastapi_test' AND pid <> pg_backend_pid();" && \
docker exec -e PGPASSWORD=123456 -it postgres psql -U postgres -c "DROP DATABASE IF EXISTS hei_fastapi_test;" && \
docker exec -e PGPASSWORD=123456 -it postgres psql -U postgres -c "CREATE DATABASE hei_fastapi_test;" && \
docker exec -e PGPASSWORD=123456 postgres pg_dump -U postgres -d hei_fastapi --inserts --column-inserts --no-owner --no-privileges | docker exec -e PGPASSWORD=123456 -i postgres psql -U postgres -d hei_fastapi_test && \
echo "✅ 迁移完成！"
```