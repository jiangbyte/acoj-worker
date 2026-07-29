import logging
from collections.abc import Iterable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse

from app.core.exceptions.base import AppError
from app.core.config.settings import settings
from app.core.response.schema import ApiErrorResponse
from app.platform.observability.metrics import record_app_exception, record_validation_error

logger = logging.getLogger(__name__)


def _build_cors_headers(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    if not origin or origin not in settings.cors.allow_origins:
        return {}

    headers = {
        "Access-Control-Allow-Origin": origin,
        "Vary": "Origin",
    }
    if settings.cors.allow_credentials:
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers


def _build_error_response(request: Request, status_code: int, code: int, message: str) -> JSONResponse:
    """构造统一错误响应，避免各类异常处理器重复拼装响应结构。"""
    return JSONResponse(
        status_code=status_code,
        content=ApiErrorResponse(code=code, message=message, data=None).model_dump(mode="json"),
        headers=_build_cors_headers(request),
    )


def _format_validation_path(loc: Iterable[object]) -> str:
    """将 Pydantic/FastAPI 的错误路径压缩为更适合接口调用方阅读的字段路径。"""
    parts: list[str] = []
    for item in list(loc)[1:]:
        if isinstance(item, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{item}]"
            else:
                parts.append(f"[{item}]")
            continue
        parts.append(str(item))
    return ".".join(part for part in parts if part) or ""


def _build_validation_message(exc: RequestValidationError) -> str:
    """从校验异常中提取首条错误摘要，避免直接暴露框架默认 detail 数组。"""
    errors = exc.errors()
    if not errors:
        return "Validation failed"
    first_error = errors[0]
    path = _format_validation_path(first_error.get("loc", ()))
    detail = first_error.get("msg", "Validation failed")
    return f"{path}: {detail}" if path else str(detail)


def _extract_http_exception_message(exc: StarletteHTTPException) -> str:
    """读取 HTTP 异常的可读文案，屏蔽非字符串 detail 的默认透传。"""
    return exc.detail if isinstance(exc.detail, str) and exc.detail else "HTTP request error"


def customize_openapi_error_responses(app: FastAPI) -> None:
    """将文档中的通用错误响应统一替换为平台错误响应模型。"""

    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components["ApiErrorResponse"] = ApiErrorResponse.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )

        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            path_item = schema.get("paths", {}).get(route.path_format)
            if not path_item:
                continue
            for method in route.methods or []:
                operation = path_item.get(method.lower())
                if not operation:
                    continue
                responses = operation.setdefault("responses", {})
                if "422" in responses:
                    responses["422"] = {
                        "description": "Validation Error",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
                            }
                        },
                    }
                responses.setdefault(
                    "500",
                    {
                        "description": "Internal Server Error",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
                            }
                        },
                    },
                )
                if any(parameter.get("name") == "Authorization" for parameter in operation.get("parameters", [])):
                    responses.setdefault(
                        "401",
                        {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
                                }
                            },
                        },
                    )
                    responses.setdefault(
                        "403",
                        {
                            "description": "Forbidden",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ApiErrorResponse"}
                                }
                            },
                        },
                    )
        app.openapi_schema = schema
        return app.openapi_schema

    setattr(app, "openapi", custom_openapi)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        record_app_exception(exc.__class__.__name__)
        logger.warning("Handled application error on %s %s: %s", request.method, request.url.path, exc.message)
        return _build_error_response(request, exc.status_code, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        record_validation_error()
        logger.warning("Validation error on %s %s", request.method, request.url.path)
        return _build_error_response(request, 422, 422, _build_validation_message(exc))

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        record_app_exception(exc.__class__.__name__)
        logger.warning("Handled HTTP exception on %s %s: %s", request.method, request.url.path, exc.detail)
        return _build_error_response(
            request,
            exc.status_code,
            exc.status_code,
            _extract_http_exception_message(exc),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        record_app_exception(exc.__class__.__name__)
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
        return _build_error_response(request, 500, 500, "Internal server error")
