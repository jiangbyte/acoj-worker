from app.deps.context import (
    account_id_ctx,
    account_type_ctx,
    duration_ms_ctx,
    request_id_ctx,
    request_method_ctx,
    request_path_ctx,
    span_id_ctx,
    status_code_ctx,
    trace_id_ctx,
)


def get_log_context() -> dict[str, object | None]:
    return {
        "request_id": request_id_ctx.get(),
        "trace_id": trace_id_ctx.get(),
        "span_id": span_id_ctx.get(),
        "account_id": account_id_ctx.get(),
        "account_type": account_type_ctx.get(),
        "method": request_method_ctx.get(),
        "path": request_path_ctx.get(),
        "status_code": status_code_ctx.get(),
        "duration_ms": duration_ms_ctx.get(),
    }
