"""注册模块提供的框架服务实现到 ServiceRegistry。"""
import logging

from app.platform.interfaces import register
from app.platform.module.spec import ModuleSpec, import_string

logger = logging.getLogger(__name__)


def register_services(module_specs: list[ModuleSpec]) -> None:
    for spec in module_specs:
        if not spec.services:
            continue
        for svc in spec.services:
            impl = import_string(svc.implementation)
            register(svc.interface, impl)
            logger.info("Registered service '%s' from %s", svc.interface, svc.implementation)
