from cryptography.fernet import Fernet

from app.core.config.settings import settings

_sensitive_keys = {
    "auth.default_password",
    "audit_alert.webhook_secret",
    "mail.password",
}

_storage_sensitive_columns = {
    "access_key",
    "secret_key",
}


def _get_fernet() -> Fernet | None:
    key = (settings.app.config_crypto_key or "").strip()
    return Fernet(key.encode()) if key else None


def is_sensitive(config_key: str) -> bool:
    return config_key in _sensitive_keys


def encrypt_config_value(config_key: str, value: str | None) -> str | None:
    if not value or not is_sensitive(config_key):
        return value
    f = _get_fernet()
    if f is None:
        raise RuntimeError("config_crypto_key is not configured")
    return f.encrypt(value.encode()).decode()


def decrypt_config_value(config_key: str, value: str | None) -> str | None:
    if not value:
        return value
    f = _get_fernet()
    if f:
        try:
            return f.decrypt(value.encode()).decode()
        except Exception:
            pass
    return value


def is_storage_sensitive(column_name: str) -> bool:
    return column_name in _storage_sensitive_columns


def encrypt_storage_value(column_name: str, value: str | None) -> str | None:
    if not value or not is_storage_sensitive(column_name):
        return value
    return encrypt_config_value(column_name, value)


def decrypt_storage_value(column_name: str, value: str | None) -> str | None:
    if not value:
        return value
    return decrypt_config_value(column_name, value)
