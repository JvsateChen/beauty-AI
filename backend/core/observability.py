"""可观测性：结构化日志 + 请求链路 ID。

线上排查故障的最低要求是「每个响应都能对上一条结构化日志」。
本模块提供 request_id 中间件：生成/透传 X-Request-Id，写入日志上下文，
并在响应头回传，前端报错时可携带该 ID 精准定位。
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
import uuid
from typing import Any, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def current_request_id() -> str:
    return _request_id_var.get()


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = current_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """生产用结构化日志（单行 JSON，便于采集）。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "msg": record.getMessage(),
        }
        for key in ("method", "path", "status", "duration_ms", "event"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: str = "INFO", as_json: bool = False) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    handler.setFormatter(
        JsonFormatter()
        if as_json
        else logging.Formatter(
            "%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level.upper())

    # 降噪：健康检查与框架自身的访问日志交给本中间件统一输出
    logging.getLogger("uvicorn.access").disabled = True


class RequestContextMiddleware(BaseHTTPMiddleware):
    """为每个请求生成 request_id，记录一条 access 日志，并回传响应头。"""

    def __init__(self, app, *, log_body_errors: bool = True):
        super().__init__(app)
        self.logger = logging.getLogger("caixuan.access")
        self.log_body_errors = log_body_errors

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = _request_id_var.set(rid)
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = rid
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            # 健康检查成功时不打日志，避免噪音
            if not (request.url.path == "/healthz" and status < 400):
                self.logger.log(
                    logging.WARNING if status >= 500 else
                    logging.INFO if status < 400 else logging.WARNING,
                    "%s %s -> %s",
                    request.method,
                    request.url.path,
                    status,
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status": status,
                        "duration_ms": duration_ms,
                    },
                )
            _request_id_var.reset(token)
