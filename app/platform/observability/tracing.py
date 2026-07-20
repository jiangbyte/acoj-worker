import logging

from app.core.config.settings import settings
from app.deps.context import span_id_ctx, trace_id_ctx

logger = logging.getLogger(__name__)
_tracing_initialized = False


def tracing_enabled() -> bool:
    return settings.observability.enabled and settings.observability.tracing_enabled


def init_tracing(app=None, engine=None) -> None:
    global _tracing_initialized
    if _tracing_initialized or not tracing_enabled():
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    except ModuleNotFoundError:
        logger.warning("Tracing is enabled but OpenTelemetry dependencies are not installed")
        return
    resource = Resource.create(
        {
            "service.name": settings.observability.service_name,
            "service.version": settings.observability.service_version,
            "deployment.environment": settings.observability.environment,
        }
    )
    provider = TracerProvider(
        resource=resource,
        sampler=TraceIdRatioBased(settings.observability.sample_ratio),
    )
    if settings.observability.otlp_enabled and settings.observability.otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=f"{settings.observability.otlp_endpoint.rstrip('/')}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
    elif settings.observability.otlp_enabled:
        logger.warning("OTLP exporter enabled but endpoint is empty; skipping exporter registration")
    trace.set_tracer_provider(provider)
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)
    if engine is not None and settings.observability.db_observability_enabled:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    if settings.observability.http_client_observability_enabled:
        HTTPXClientInstrumentor().instrument()
    _tracing_initialized = True


def shutdown_tracing() -> None:
    try:
        from opentelemetry import trace
    except ModuleNotFoundError:
        return
    provider = trace.get_tracer_provider()
    shutdown = getattr(provider, "shutdown", None)
    if callable(shutdown):
        shutdown()


def sync_trace_context() -> None:
    try:
        from opentelemetry import trace
    except ModuleNotFoundError:
        trace_id_ctx.set(None)
        span_id_ctx.set(None)
        return
    span = trace.get_current_span()
    span_context = span.get_span_context()
    if not span_context.is_valid:
        trace_id_ctx.set(None)
        span_id_ctx.set(None)
        return
    trace_id_ctx.set(format(span_context.trace_id, "032x"))
    span_id_ctx.set(format(span_context.span_id, "016x"))
