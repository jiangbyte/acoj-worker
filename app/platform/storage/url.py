from urllib.parse import quote, urljoin, urlparse

from app.core.config.settings import settings


def quote_object_name(object_name: str) -> str:
    return "/".join(quote(part) for part in object_name.strip("/").split("/") if part)


def build_file_access_url(object_name: str) -> str:
    quoted_name = quote_object_name(object_name)
    if settings.storage.base_url:
        return urljoin(settings.storage.base_url.rstrip("/") + "/", quoted_name)
    return f"{settings.storage.public_path.rstrip('/')}/{quoted_name}"


def is_external_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https", "data", "blob"}


def normalize_object_name(value: str | None) -> str | None:
    if not value:
        return None
    raw_value = str(value).strip()
    if not raw_value:
        return None
    if is_external_url(raw_value):
        return raw_value

    public_prefix = settings.storage.public_path.rstrip("/") + "/"
    if raw_value.startswith(public_prefix):
        return raw_value[len(public_prefix) :].lstrip("/")

    return raw_value.replace("\\", "/").lstrip("/")


def resolve_file_url(value: str | None) -> str | None:
    object_name = normalize_object_name(value)
    if not object_name:
        return None
    if is_external_url(object_name):
        return object_name
    return build_file_access_url(object_name)
