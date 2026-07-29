"""ServiceRegistry — 通用服务注册中心。

注册:  register("interface_name", impl_instance)
消费:  resolve("interface_name") → object（调用方 import Protocol 后 cast）

新增 interface 只需要:
  1. 在 interfaces/ 下定义 Protocol 类
  2. 在模块的 module.py 中声明 ServiceRegistration
"""

from typing import cast

from app.platform.interfaces.account_lookup import AccountLookupProtocol
from app.platform.interfaces.audit_queue import AuditQueueProtocol
from app.platform.interfaces.config_reader import ConfigReaderProtocol
from app.platform.interfaces.data_scope_resolver import DataScopeResolverProtocol

_registry: dict[str, object] = {}


def register(interface: str, impl: object) -> None:
    _registry[interface] = impl


def resolve(interface: str) -> object:
    impl = _registry.get(interface)
    if impl is None:
        raise RuntimeError(f"'{interface}' not registered")
    return impl


# 类型安全的便捷注册函数（薄封装）

def register_audit_queue(impl: AuditQueueProtocol) -> None:
    register("audit_queue", impl)


def register_config_reader(impl: ConfigReaderProtocol) -> None:
    register("config_reader", impl)


def register_data_scope_resolver(impl: DataScopeResolverProtocol) -> None:
    register("data_scope_resolver", impl)


def register_account_lookup(impl: AccountLookupProtocol) -> None:
    register("account_lookup", impl)
