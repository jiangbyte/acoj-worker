"""从 DB 配置表回写运行期 settings 的自动映射函数。"""
from app.core.config.settings import settings
from app.platform.config.coerce import coerce_config_value
from app.platform.config.reader import config_reader


def _apply_from_config(settings_obj: object, prefix: str) -> None:
    for field_name in vars(settings_obj.__class__).get("model_fields", {}):
        config_key = f"{prefix}.{field_name}"
        raw = config_reader.get(config_key)
        if raw is None:
            continue

        field_info = settings_obj.model_fields[field_name]
        annotation = field_info.annotation

        value = coerce_config_value(raw, annotation)
        if value is not None:
            setattr(settings_obj, field_name, value)


def apply_sys_config() -> None:
    """从 sys_config 表覆盖上传和邮件配置。"""
    _apply_from_config(settings.storage, "storage")
    _apply_from_config(settings.mail, "mail")


def apply_storage_config() -> None:
    """Validate that a DB-backed default storage config is available."""
    if not config_reader.get_default_storage():
        raise RuntimeError(
            "No active storage configuration found in sys_storage_config table. "
            "Set a default storage config via admin panel before starting the application."
        )


def apply_all_config() -> None:
    """顺序应用所有 DB 配置覆盖到 settings。"""
    apply_storage_config()
    apply_sys_config()
