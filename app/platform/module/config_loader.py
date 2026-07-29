"""模块级配置加载 — 从 ModuleSpec.config_model 声明实例化 BaseSettings 并注入 settings。"""
import importlib
import logging

from pydantic_settings import BaseSettings

from app.core.config.settings import settings
from app.platform.config.coerce import coerce_config_value
from app.platform.config.reader import config_reader
from app.platform.module.spec import ModuleSpec

logger = logging.getLogger(__name__)


def load_module_configs(module_specs: list[ModuleSpec]) -> None:
    for spec in module_specs:
        if not spec.config_model:
            continue
        cls = _import_config_class(spec.config_model)
        instance = cls()
        if spec.config_from_db:
            _apply_db_overrides(instance, spec.name)
        settings.module_configs[spec.name] = instance
        logger.info("Loaded module config for %s from %s", spec.name, spec.config_model)


def get_module_config(module_name: str) -> BaseSettings | None:
    return settings.module_configs.get(module_name)


def _import_config_class(import_path: str) -> type[BaseSettings]:
    module_path, _, attr = import_path.partition(":")
    if not attr:
        raise ValueError(f"config_model must use 'module:Class' format: {import_path}")
    mod = importlib.import_module(module_path)
    cls = getattr(mod, attr)
    if not isinstance(cls, type) or not issubclass(cls, BaseSettings):
        raise TypeError(f"{import_path} is not a BaseSettings subclass")
    return cls


def _apply_db_overrides(instance: BaseSettings, module_name: str) -> None:
    prefix = module_name + "."
    for key, value in config_reader.raw_items().items():
        if not key.startswith(prefix):
            continue
        attr_name = key[len(prefix):]
        field_info = instance.__class__.model_fields.get(attr_name)
        if field_info is None:
            continue
        coerced = coerce_config_value(value, field_info.annotation)
        if coerced is not None:
            setattr(instance, attr_name, coerced)
