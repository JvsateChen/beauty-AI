"""统一错误体与异常处理器。

目标：
  1. 任何异常都返回**结构一致**的 JSON 错误体，前端只需处理一种形状。
  2. 5xx 绝不外泄堆栈/内部路径 —— 只回 request_id，细节进日志。
  3. 业务可预期错误（未收录商品、未授权、参数非法）用 DomainError 表达。
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.observability import current_request_id

logger = logging.getLogger("caixuan.error")


class DomainError(Exception):
    """可预期的业务错误。code 供前端分支处理，message 可直接展示给用户。"""

    def __init__(self, code: str, message: str, *, http_status: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class NotFoundError(DomainError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, http_status=status.HTTP_404_NOT_FOUND)


class UnauthorizedError(DomainError):
    def __init__(self, code: str = "UNAUTHORIZED", message: str = "请先登录后再操作。"):
        super().__init__(code, message, http_status=status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(DomainError):
    def __init__(self, code: str = "FORBIDDEN", message: str = "无权访问该资源。"):
        super().__init__(code, message, http_status=status.HTTP_403_FORBIDDEN)


class UpstreamError(DomainError):
    """外部数据源/推送通道故障。"""

    def __init__(self, code: str, message: str):
        super().__init__(code, message, http_status=status.HTTP_502_BAD_GATEWAY)


def _body(code: str, message: str) -> dict:
    return {
        "error": {"code": code, "message": message, "request_id": current_request_id()},
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError):
        return JSONResponse(status_code=exc.http_status, content=_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
        msg = first.get("msg", "参数不合法")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_body("INVALID_PARAM", f"参数「{loc}」不合法：{msg}"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(f"HTTP_{exc.status_code}", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # 细节只进日志；对外仅给 request_id 便于对账
        logger.exception(
            "未处理异常 %s %s", request.method, request.url.path,
            extra={"method": request.method, "path": request.url.path},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_body(
                "INTERNAL_ERROR",
                "服务暂时不可用，请稍后重试。"
                f"（如持续出现请提供追踪号 {current_request_id()}）",
            ),
        )
