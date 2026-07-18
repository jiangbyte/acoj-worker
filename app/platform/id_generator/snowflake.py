from app.core.config.settings import settings

try:
    from snowflake import SnowflakeGenerator
except ModuleNotFoundError as exc:  # pragma: no cover
    raise RuntimeError("snowflake-id package is required for ID generation") from exc


def _build_instance_id() -> int:
    datacenter = settings.id_generator.datacenter_id & 0x1F
    worker = settings.id_generator.worker_id & 0x1F
    return (datacenter << 5) | worker


_generator = SnowflakeGenerator(
    _build_instance_id(),
)


def generate_snowflake_id() -> str:
    return str(next(_generator))
