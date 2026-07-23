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
    model_config = SettingsConfigDict(extra="ignore")
    broker_url: str = "amqp://guest:guest@127.0.0.1:5672//"
    result_backend: str = "rpc://"
    worker_log_level: str = "INFO"
    beat_log_level: str = "INFO"
    worker_pool: str = "threads"
    worker_concurrency: int = 4
    worker_prefetch_multiplier: int = 4
    worker_without_mingle: bool = True
    worker_without_gossip: bool = True
    worker_remote_control_enabled: bool = False
    worker_cancel_long_running_tasks_on_connection_loss: bool = True
    sandbox_worker_pool_size: int = 16
    sandbox_borrow_timeout_seconds: float = 0.25
    sandbox_max_queue_wait_seconds: float = 0.0
    sandbox_request_timeout_seconds: float = 120.0
    sandbox_queue_wait_warn_seconds: float = 0.5
    sandbox_health_check_timeout_seconds: float = 1.0
    sandbox_standard_parallelism: int = 4
    sandbox_allow_emergency_worker: bool = False
    sandbox_compilation_cache_enabled: bool = True
    sandbox_compilation_cache_dir: str = "/tmp/acoj-ccache"
    sandbox_compilation_cache_max_mb: int = 512
    sandbox_compilation_cache_ttl_seconds: int = 3600
    sandbox_enable_namespaces: bool = False
    sandbox_rootfs_path: str = ""
    sandbox_isolate_network: bool = True
    sandbox_isolate_ipc: bool = True
    sandbox_isolate_uts: bool = True
    sandbox_private_mounts: bool = True
    sandbox_use_pivot_root: bool = True
    sandbox_bind_workspace: bool = True
    sandbox_enable_cgroup: bool = False
    sandbox_cgroup_version: str = "auto"
    sandbox_cgroup_base_path: str = "/sys/fs/cgroup/acoj-sandbox"
    sandbox_cgroup_v1_memory_base_path: str = ""
    sandbox_cgroup_v1_pids_base_path: str = ""


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
    # 文件缓存（worker judge 使用，避免重复从远端下载测试数据）
    cache_enabled: bool = True
    cache_dir: str = "storage/judge-cache"
    cache_max_mb: int = 512
    cache_ttl_seconds: int = 86400 * 7


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
    storage: StorageSettings = Field(default_factory=StorageSettings)
    id_generator: IdGeneratorSettings = Field(default_factory=IdGeneratorSettings)
    swagger: SwaggerSettings = Field(default_factory=SwaggerSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
