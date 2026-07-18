from app.core.schema.base import ApiSchema


class IdNameResponse(ApiSchema):
    """通用 ID/名称回显项。"""

    id: str
    name: str
