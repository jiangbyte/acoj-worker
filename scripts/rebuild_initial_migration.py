"""重建完整初始 Alembic 迁移。

该脚本会使用临时空 PostgreSQL 数据库生成一份新的 initial migration，
避免基于已有开发库 autogenerate 时误生成空迁移或增量迁移。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shlex
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import URL, make_url

DEFAULT_DB_URL = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/hei_fastapi"
DEFAULT_SHADOW_DB = "hei_fastapi_migration_shadow"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-m",
        "--message",
        default="initial schema",
        help='Alembic revision message, defaults to "initial schema".',
    )
    parser.add_argument(
        "--db-url",
        help="Source database URL used as a template for connection credentials.",
    )
    parser.add_argument(
        "--shadow-db",
        default=DEFAULT_SHADOW_DB,
        help=f"Temporary database name, defaults to {DEFAULT_SHADOW_DB}.",
    )
    parser.add_argument(
        "--admin-db",
        default="postgres",
        help='Database used to create/drop the temporary database, defaults to "postgres".',
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the temporary database after the script finishes.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm deletion of existing migrations/versions/*.py files.",
    )
    return parser.parse_args()


def read_dotenv_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != key:
            continue
        return shlex.split(value.strip(), comments=False)[0] if value.strip() else ""

    return None


def get_source_db_url(project_root: Path, override: str | None) -> str:
    if override:
        return override
    if env_url := os.environ.get("DB__URL"):
        return env_url

    db_url: str | None = None
    for env_file in (project_root / ".env", project_root / ".env.local"):
        if value := read_dotenv_value(env_file, "DB__URL"):
            db_url = value

    return db_url or DEFAULT_DB_URL


def ensure_postgresql_url(url: URL) -> None:
    if not url.drivername.startswith("postgresql"):
        raise SystemExit("Only PostgreSQL URLs are supported for rebuilding initial migrations.")


def quote_identifier(value: str) -> str:
    if "\x00" in value:
        raise ValueError("PostgreSQL identifiers cannot contain NUL bytes.")
    return '"' + value.replace('"', '""') + '"'


def asyncpg_dsn(url: URL, database: str) -> str:
    return url.set(drivername="postgresql", database=database).render_as_string(
        hide_password=False
    )


async def recreate_database(source_url: URL, admin_db: str, shadow_db: str) -> None:
    import asyncpg

    admin_dsn = asyncpg_dsn(source_url, admin_db)
    conn = await asyncpg.connect(dsn=admin_dsn)
    try:
        await conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1
              AND pid <> pg_backend_pid()
            """,
            shadow_db,
        )
        quoted_db = quote_identifier(shadow_db)
        await conn.execute(f"DROP DATABASE IF EXISTS {quoted_db}")
        await conn.execute(f"CREATE DATABASE {quoted_db}")
    finally:
        await conn.close()


async def drop_database(source_url: URL, admin_db: str, shadow_db: str) -> None:
    import asyncpg

    admin_dsn = asyncpg_dsn(source_url, admin_db)
    conn = await asyncpg.connect(dsn=admin_dsn)
    try:
        await conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1
              AND pid <> pg_backend_pid()
            """,
            shadow_db,
        )
        await conn.execute(f"DROP DATABASE IF EXISTS {quote_identifier(shadow_db)}")
    finally:
        await conn.close()


def confirm_destructive_action(args: argparse.Namespace, version_files: list[Path]) -> None:
    if args.yes:
        return
    if not sys.stdin.isatty():
        raise SystemExit(
            "Refusing to delete migration files without --yes in non-interactive mode."
        )

    print("This will delete existing migration files:")
    for path in version_files:
        print(f"  - {path}")
    answer = input("Continue? Type 'rebuild' to confirm: ").strip()
    if answer != "rebuild":
        raise SystemExit("Aborted.")


def clear_versions(versions_dir: Path) -> list[Path]:
    deleted: list[Path] = []
    for path in sorted(versions_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        path.unlink()
        deleted.append(path)
    return deleted


def run_script(project_root: Path, script_name: str, env: dict[str, str], *args: str) -> None:
    command = [sys.executable, str(project_root / "scripts" / script_name), *args]
    subprocess.run(command, cwd=project_root, env=env, check=True)


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    versions_dir = project_root / "migrations" / "versions"
    if not versions_dir.is_dir():
        raise SystemExit(f"Migration versions directory does not exist: {versions_dir}")

    source_url = make_url(get_source_db_url(project_root, args.db_url))
    ensure_postgresql_url(source_url)
    if args.shadow_db in {source_url.database, args.admin_db}:
        raise SystemExit("--shadow-db must differ from the source database and --admin-db.")

    version_files = [
        path for path in sorted(versions_dir.glob("*.py")) if path.name != "__init__.py"
    ]
    confirm_destructive_action(args, version_files)

    try:
        import asyncpg  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "asyncpg is required. Install the postgres/dev dependencies first."
        ) from exc

    shadow_url = source_url.set(database=args.shadow_db)
    shadow_env = os.environ.copy()
    shadow_env["DB__URL"] = shadow_url.render_as_string(hide_password=False)

    print(f"Recreating temporary database: {args.shadow_db}")
    asyncio.run(recreate_database(source_url, args.admin_db, args.shadow_db))

    try:
        print("Deleting existing migration version files")
        deleted = clear_versions(versions_dir)
        if deleted:
            print(f"Deleted {len(deleted)} migration file(s).")
        else:
            print("No existing migration files found.")

        print("Generating initial migration")
        run_script(project_root, "makemigration.py", shadow_env, args.message)

        print("Validating generated migration")
        run_script(project_root, "migrate.py", shadow_env)
        run_script(project_root, "check_migration.py", shadow_env)
    finally:
        if args.keep_db:
            print(f"Keeping temporary database: {args.shadow_db}")
        else:
            print(f"Dropping temporary database: {args.shadow_db}")
            asyncio.run(drop_database(source_url, args.admin_db, args.shadow_db))

    generated = sorted(versions_dir.glob("*.py"))
    print("Done. Generated migration files:")
    for path in generated:
        if path.name != "__init__.py":
            print(f"  - {path.relative_to(project_root)}")


if __name__ == "__main__":
    main()
