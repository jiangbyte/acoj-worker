from contextvars import ContextVar

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
account_id_ctx: ContextVar[str | None] = ContextVar("account_id", default=None)
account_type_ctx: ContextVar[str | None] = ContextVar("account_type", default=None)
trace_id_ctx: ContextVar[str | None] = ContextVar("trace_id", default=None)
span_id_ctx: ContextVar[str | None] = ContextVar("span_id", default=None)
request_path_ctx: ContextVar[str | None] = ContextVar("request_path", default=None)
request_method_ctx: ContextVar[str | None] = ContextVar("request_method", default=None)
status_code_ctx: ContextVar[int | None] = ContextVar("status_code", default=None)
duration_ms_ctx: ContextVar[float | None] = ContextVar("duration_ms", default=None)
client_ip_ctx: ContextVar[str | None] = ContextVar("client_ip", default=None)
user_agent_ctx: ContextVar[str | None] = ContextVar("user_agent", default=None)
