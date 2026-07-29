"""Apply optional in-memory config overrides onto settings."""
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
    _apply_from_config(settings.storage, "storage")
    _apply_from_config(settings.mail, "mail")


def apply_all_config() -> None:
    apply_sys_config()
