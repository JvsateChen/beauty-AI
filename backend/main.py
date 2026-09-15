"""采选美妆 AI · FastAPI 后端入口

定位：垂直于国际大牌美妆的「AI 对话选型 + 多平台比价 + 货源风险筛查」工具平台。
端形态：Web（H5）为主，小程序二期复用同一套 REST。

5 大核心模块（一期全部实现）：
  M1 AI 智能对话选型      —— POST   /api/dialogue/chat
  M2 全网结构化比价看板   —— GET    /api/compare/result
  M3 价格行情曲线         —— GET    /api/trend/series
  M4 降价订阅提醒         —— GET|POST|DELETE /api/alert/*
  M5 一键跳转与点击溯源   —— GET    /api/offer/go  ·  POST /api/offer/click

架构分层（依赖方向单向，不允许反向）：
  routers/    HTTP 契约：参数校验、鉴权依赖、响应剪裁
  services/   业务编排：比价、行情、订阅、推送、调度
  providers/  数据源：联盟接口 / 种子数据集，统一 PriceProvider 协议
  core/       口径与基座：config / domain / catalog / db / models / errors / security / observability

诚信原则（本项目最重要的工程约束）：
  · 数据来源必须可区分 —— 每个响应带 data_basis（live / seed / mixed / snapshot）
  · 未接入的能力必须如实说明 —— 不假装有数据、不假装已推送、不假装已登录
  · 商品未收录就说不收录 —— 绝不回落到默认商品编造答案
  · 排序中立 —— 佣金与赞助位不参与名次，赞助位强制标注

合规红线：
  1. 不提供真伪鉴定服务、不承诺正品；
  2. 所有价格为「行情参考价」，非锁定成交价，不构成交易要约；
  3. 只做版本差异科普、临期风险筛查、渠道优劣提示。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.domain import CHANNELS, RISK_TAGS, VERSIONS
from core.errors import register_exception_handlers
from core.observability import RequestContextMiddleware, setup_logging
from routers import alert, auth, compare, dialogue, offer, trend

setup_logging(settings.log_level, as_json=settings.log_json)
logger = logging.getLogger("caixuan.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动：跑迁移 + 起定时任务；关闭：停任务。"""
    from core.db import run_migrations
    from services import scheduler

    try:
        run_migrations()
    except Exception:                      # pragma: no cover - 启动期防御
        logger.exception("数据库初始化失败，请检查 DATABASE_URL / 目录权限")
        raise

    scheduler.start()
    logger.info(
        "%s v%s 启动完成（env=%s, data_mode=%s, 已接入渠道=%s）",
        settings.app_name, settings.app_version, settings.env,
        settings.data_mode, settings.configured_channels or "无（演示数据集）",
    )
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(
    title=f"{settings.app_name} · API",
    version=settings.app_version,
    description=(
        "AI 对话选型 · 全网结构化比价 · 价格行情曲线 · 降价订阅提醒 · CPS 一键跳转。\n\n"
        "不提供真伪鉴定服务，不承诺正品；所有价格均为行情参考价。"
    ),
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_prod else None,
    redoc_url=None,
)

# 请求链路 ID + 访问日志（必须在 CORS 之外先包一层，保证 4xx/5xx 也有 request_id）
app.add_middleware(RequestContextMiddleware)

# CORS 白名单来自配置。生产禁止 "*"（带凭据的通配来源浏览器会直接拒绝，
# 且会把接口暴露给任意站点）。
_origins = settings.cors_origin_list
if settings.is_prod and "*" in _origins:
    raise RuntimeError("生产环境禁止 CORS 通配符，请在 CORS_ORIGINS 中显式列出来源域名")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Session-Id", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
    max_age=600,
)

register_exception_handlers(app)

app.include_router(auth.router, prefix="/api/auth", tags=["鉴权 · 会话"])
app.include_router(dialogue.router, prefix="/api/dialogue", tags=["M1 AI 对话选型"])
app.include_router(compare.router, prefix="/api/compare", tags=["M2 比价看板"])
app.include_router(trend.router, prefix="/api/trend", tags=["M3 价格行情"])
app.include_router(alert.router, prefix="/api/alert", tags=["M4 降价订阅"])
app.include_router(offer.router, prefix="/api/offer", tags=["M5 跳转与溯源"])


@app.get("/", tags=["元信息"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "env": settings.env,
        "positioning": "国际大牌护肤美妆 · AI 对话选型 + 多平台比价 + 货源风险筛查",
        "modules": [
            "M1 AI 对话选型",
            "M2 全网结构化比价看板",
            "M3 价格行情曲线",
            "M4 降价订阅提醒",
            "M5 一键跳转与点击溯源",
        ],
        "channels": list(CHANNELS),
        "versions": list(VERSIONS),
        "risk_tags": list(RISK_TAGS),
        "data_mode": settings.data_mode,
        "configured_channels": settings.configured_channels,
        "endpoints": {
            "auth": ["POST /api/auth/session", "GET /api/auth/me"],
            "M1": ["POST /api/dialogue/chat", "GET /api/dialogue/suggestions"],
            "M2": ["GET /api/compare/result?q=小棕瓶", "GET /api/compare/products",
                   "GET /api/compare/sources"],
            "M3": ["GET /api/trend/series?q=小棕瓶&days=90", "GET /api/trend/lowest?q=小棕瓶"],
            "M4": ["GET /api/alert/capability", "GET /api/alert/list",
                   "POST /api/alert/add", "DELETE /api/alert/{id}"],
            "M5": ["GET /api/offer/go?q=..&offer_id=..", "POST /api/offer/click",
                   "GET /api/offer/best?q=小棕瓶", "GET /api/offer/clicks/summary"],
        },
        "docs": "/docs" if not settings.is_prod else None,
        "disclaimer": settings.disclaimer,
    }


@app.get("/healthz", tags=["元信息"])
def healthz():
    """存活探针（容器 / K8s 用）。不查库，避免数据库抖动导致实例被反复重启。"""
    return {"ok": True, "version": settings.app_version}


@app.get("/readyz", tags=["元信息"])
def readyz():
    """就绪探针：真正探一次数据库与数据源装配，失败返回 503。"""
    from sqlalchemy import text

    from core.db import get_engine
    from services import market as market_service
    from services import scheduler

    checks: dict[str, object] = {}
    ok = True

    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:                      # pragma: no cover - 探针
        checks["database"] = f"failed: {exc.__class__.__name__}"
        ok = False

    try:
        checks["providers"] = [
            {"channel": s["channel"], "configured": s["configured"]}
            for s in market_service.provider_status()
        ]
    except Exception as exc:                      # pragma: no cover - 探针
        checks["providers"] = f"failed: {exc.__class__.__name__}"
        ok = False

    checks["scheduler"] = scheduler.status()["running"]
    checks["data_mode"] = settings.data_mode

    payload = {"ok": ok, "checks": checks}
    return JSONResponse(status_code=200 if ok else 503, content=payload)
