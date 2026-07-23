from app.core.schema.base import ApiSchema


class RootHealthResponse(ApiSchema):
    """根健康检查响应结构。"""

    status: str
    service: str


class LiveHealthResponse(ApiSchema):
    """存活探针响应结构。"""

    status: str


class HealthCheckItem(ApiSchema):
    """单个基础设施组件的就绪检查结果。"""

    enabled: bool
    ok: bool
    detail: str | None = None


class ReadyChecksResponse(ApiSchema):
    """聚合基础设施检查结果。"""

    database: HealthCheckItem
    redis: HealthCheckItem
    celery_broker: HealthCheckItem
    storage: HealthCheckItem


class ReadyHealthResponse(ApiSchema):
    """就绪探针响应结构。"""

    status: str
    checks: ReadyChecksResponse
