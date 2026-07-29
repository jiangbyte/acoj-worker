from app.deps.context import request_id_ctx


def get_request_id() -> str | None:
    return request_id_ctx.get()
