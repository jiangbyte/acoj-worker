from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config.enums import StorageProvider

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    name: str = "hei-fastapi"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = True
    workers: int = 1
    worker_max: int = 4
    timezone: str = "Asia/Shanghai"


class DatabaseSettings(BaseSettings):
    url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/hei_fastapi"
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout_seconds: float = 30.0
    pool_recycle_seconds: int = 1800
    pool_pre_ping: bool = True


class AuditSettings(BaseSettings):
    operation_queue_size: int = 1000
    operation_shutdown_timeout_seconds: float = 5.0


class RedisSettings(BaseSettings):
    """Redis 配置，支持通过标准 URL 传递账号、密码、库编号等连接信息。"""

    url: str = "redis://localhost:6379/0"


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    token_name: str = "Authorization"
    token_ttl_seconds: int = 60 * 60 * 24 * 30
    refresh_ttl_seconds: int = 60 * 60 * 24 * 30
    captcha_ttl_seconds: int = 5 * 60
    password_crypto_key_ttl_seconds: int = 10 * 60


class MailSettings(BaseSettings):
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""
    from_name: str = "hei-fastapi"
    use_tls: bool = True
    timeout_seconds: float = 10.0
    admin_password_reset_url: str = "http://localhost:5173/auth/forgot-password"
    portal_password_reset_url: str = "http://localhost:5174/auth/reset-password"


class CorsSettings(BaseSettings):
    allow_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    allow_credentials: bool = True
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]


class CelerySettings(BaseSettings):
    broker_url: str = "amqp://guest:guest@127.0.0.1:5672//"
    worker_log_level: str = "INFO"
    beat_log_level: str = "INFO"
    worker_pool: str = "solo"
    worker_concurrency: int = 1
    worker_without_mingle: bool = True
    worker_without_gossip: bool = True
    worker_remote_control_enabled: bool = False
    worker_cancel_long_running_tasks_on_connection_loss: bool = True
    shutdown_timeout_seconds: float = 10.0
    auto_start_enabled: bool = True
    auto_start_worker_enabled: bool = True
    auto_start_beat_enabled: bool = True
    beat_lock_key: str = "process:celery:beat:lock"
    beat_lock_ttl_seconds: int = 60
    beat_lock_renew_seconds: int = 20


class MQSettings(BaseSettings):
    enabled: bool = False
    url: str = ""
    reconnect_interval_seconds: float = 5.0
    publish_exchange: str = ""
    publish_exchange_type: str = "topic"


class StorageSettings(BaseSettings):
    provider: StorageProvider = StorageProvider.S3
    bucket: str = "hei-fastapi"
    endpoint: str = "http://127.0.0.1:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    region: str = "us-east-1"
    use_ssl: bool = False
    presign_expire_seconds: int = 3600
    base_url: str = ""
    public_path: str = "/api/v1/files"
    local_root: str = "storage"
    upload_max_bytes: int = 10 * 1024 * 1024
    upload_allowed_content_types: list[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
        "text/plain",
        "video/mp4",
        "video/webm",
        "video/quicktime",
    ]
    upload_allowed_extensions: list[str] = [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".pdf",
        ".txt",
        ".mp4",
        ".webm",
        ".mov",
    ]
    upload_denied_extensions: list[str] = [
        ".exe",
        ".bat",
        ".cmd",
        ".sh",
        ".js",
        ".html",
        ".php",
        ".py",
        ".jar",
    ]
    upload_category_max_length: int = 64
    public_upload_enabled: bool = False


class IdGeneratorSettings(BaseSettings):
    worker_id: int = 1
    datacenter_id: int = 1


class SwaggerSettings(BaseSettings):
    enabled: bool = True


class ObservabilitySettings(BaseSettings):
    enabled: bool = False
    service_name: str = "hei-fastapi"
    service_version: str = "0.1.0"
    environment: str = "dev"
    log_enabled: bool = True
    log_level: str = "INFO"
    log_json: bool = False
    metrics_enabled: bool = False
    metrics_path: str = "/metrics"
    tracing_enabled: bool = False
    otlp_enabled: bool = False
    otlp_endpoint: str = ""
    sample_ratio: float = 1.0
    celery_observability_enabled: bool = False
    db_observability_enabled: bool = False
    http_client_observability_enabled: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.local"),
        env_nested_delimiter="__",
        extra="ignore",
    )

    app: AppSettings = Field(default_factory=AppSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    mail: MailSettings = Field(default_factory=MailSettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    mq: MQSettings = Field(default_factory=MQSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    id_generator: IdGeneratorSettings = Field(default_factory=IdGeneratorSettings)
    swagger: SwaggerSettings = Field(default_factory=SwaggerSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
