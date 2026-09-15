"""M5 · CPS 一键跳转与点击溯源。

修复的问题：旧实现 ``href={offer.cps_url || '#'}``，而后端从不产出 cps_url，
于是所有「去购买」都是空链接 —— 核心变现路径完全断裂。

现在的两条路径：
  1. 前端直接用 ``offers[].cps_url``（已由 providers.cps 保证非空）
  2. 推荐做法：前端跳 ``GET /api/offer/go?q=..&offer_id=..&sid=..``，
     由服务端记一次点击后 302 到真实地址 —— 归因更可靠，且换链接时前端无需改动

安全说明（重要）：**跳转目标永远由服务端从自己的报价数据里推导**，
绝不接受请求参数里的任意 URL，因此不存在开放重定向（open redirect）漏洞。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import get_session
from core.domain import cheapest
from core.errors import NotFoundError
from core.models import OfferClick, UserSession
from core.security import optional_session
from providers.cps import build_sub_id, has_attribution, is_affiliate_url
from services import market as market_service

logger = logging.getLogger("caixuan.offer")

router = APIRouter()


def _clip(value: str | None, limit: int) -> str | None:
    if not value:
        return None
    return value[:limit]


def _record(
    db: Session,
    *,
    product_key: str | None,
    offer: dict,
    sub_id: str,
    session: UserSession | None,
    referer: str | None,
    user_agent: str | None,
) -> None:
    db.add(OfferClick(
        session_id=session.id if session else None,
        product_key=product_key,
        offer_id=str(offer.get("id") or ""),
        channel=str(offer.get("channel") or ""),
        shop_name=_clip(offer.get("shop_name"), 64),
        version=offer.get("version"),
        price_cents=int(offer.get("price_cents") or 0),
        sub_id=_clip(sub_id, 64),
        cps_url=_clip(offer.get("cps_url"), 2000),
        referer=_clip(referer, 255),
        user_agent=_clip(user_agent, 255),
    ))


@router.get("/go", include_in_schema=True)
def go(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100, description="商品查询词"),
    offer_id: str = Query(..., min_length=1, max_length=64, description="报价 ID"),
    sid: str | None = Query(None, description="会话 ID（用于归因；可省略）"),
    db: Session = Depends(get_session),
    session: UserSession | None = Depends(optional_session),
    user_agent: str | None = Header(default=None),
):
    """记录点击并 302 跳转到对应渠道。跳转目标不来自请求参数。"""
    market = market_service.get_offers(q, session_id=(session.id if session else sid))
    offer = next((o for o in market.offers if str(o.get("id")) == offer_id), None)
    if offer is None:
        raise NotFoundError(
            "OFFER_NOT_FOUND",
            f"未找到报价「{offer_id}」，可能该渠道报价已更新，请返回比价页重新选择。",
        )

    sub_id = str(offer.get("sub_id") or build_sub_id(
        session.id if session else sid, market.product.key, offer_id
    ))
    _record(
        db,
        product_key=market.product.key,
        offer=offer,
        sub_id=sub_id,
        session=session,
        referer=request.headers.get("referer"),
        user_agent=user_agent,
    )
    db.commit()

    target = str(offer.get("cps_url") or "")
    if not target or target == "#":
        # 理论上 providers.cps 绝不产出空链接；真出现也不静默跳首页，而是明说
        raise NotFoundError(
            "LINK_UNAVAILABLE",
            "该渠道跳转链接暂时不可用，请稍后重试或改用其他渠道。",
        )
    return RedirectResponse(url=target, status_code=302)


class ClickIn(BaseModel):
    """前端在 `cps_url` 直接跳转时的点击埋点（sendBeacon / fetch keepalive 调用）。"""

    product_key: str | None = Field(default=None, max_length=64)
    offer_id: str = Field(min_length=1, max_length=64)
    channel: str = Field(min_length=1, max_length=32)
    shop_name: str | None = Field(default=None, max_length=64)
    version: str | None = Field(default=None, max_length=16)
    price: float | None = Field(default=None, ge=0)
    sub_id: str | None = Field(default=None, max_length=64)
    cps_url: str | None = Field(default=None, max_length=2000)


@router.post("/click")
def click(
    body: ClickIn,
    db: Session = Depends(get_session),
    session: UserSession | None = Depends(optional_session),
    user_agent: str | None = Header(default=None),
):
    """点击埋点（可选）。不返回跳转地址，只记事件，避免被当作跳转代理滥用。"""
    db.add(OfferClick(
        session_id=session.id if session else None,
        product_key=body.product_key,
        offer_id=body.offer_id,
        channel=body.channel,
        shop_name=body.shop_name,
        version=body.version,
        price_cents=int(round((body.price or 0) * 100)),
        sub_id=body.sub_id,
        cps_url=body.cps_url,
        user_agent=_clip(user_agent, 255),
    ))
    db.commit()
    return {"ok": True}


@router.get("/clicks/summary")
def clicks_summary(
    db: Session = Depends(get_session),
    session: UserSession = Depends(optional_session),
):
    """当前会话的点击概览（「我的」页展示；也为将来佣金对账预留口径）。"""
    if session is None:
        return {
            "total": 0,
            "by_channel": [],
            "with_attribution": 0,
            "affiliate_tracked": 0,
            "latest": None,
            "note": "尚无会话，无法统计。",
        }
    rows = list(db.scalars(
        select(OfferClick)
        .where(OfferClick.session_id == session.id)
        .order_by(OfferClick.created_at.desc())
        .limit(200)
    ).all())
    by_channel: dict[str, int] = {}
    for r in rows:
        by_channel[r.channel] = by_channel.get(r.channel, 0) + 1

    # 两个口径要分开统计，不能混为一谈：
    #   with_attribution  —— 链接里带了归因标识（fallback 档用渠道各自的参数名，
    #                        如拼多多 refer_page_name / 天猫 utparam / 京东 utm_source）
    #   affiliate_tracked —— 真正走联盟推广链接（affiliate 档，带 sub_id，已启用佣金归因）
    # 旧实现只找字面 "sub_id="，导致 fallback 档一律算 0，指标长期被低估。
    with_attribution = sum(
        1 for r in rows if has_attribution(r.cps_url, r.channel)
    )
    affiliate_tracked = sum(1 for r in rows if is_affiliate_url(r.cps_url))

    return {
        "total": len(rows),
        "by_channel": [
            {"channel": k, "count": v}
            for k, v in sorted(by_channel.items(), key=lambda x: -x[1])
        ],
        "with_attribution": with_attribution,
        "affiliate_tracked": affiliate_tracked,
        "latest": (
            {
                "channel": rows[0].channel,
                "shop_name": rows[0].shop_name,
                "at": rows[0].created_at.isoformat() if rows[0].created_at else None,
            } if rows else None
        ),
        "note": (
            "点击已记录。带归因标识的链接可对账；"
            "佣金归因需各渠道联盟凭据接入后生效，未接入时跳转为官方搜索深链，不产生佣金。"
        ),
    }


@router.get("/best")
def best_offer(q: str = Query(..., min_length=1, max_length=100)):
    """轻量接口：直接返回该商品最低到手价的跳转信息（对话页一键跳转用）。"""
    market = market_service.get_offers(q)
    best = cheapest(market.offers)
    if best is None:
        raise NotFoundError("OFFER_NOT_FOUND", "暂无可用报价。")
    return {
        "product_key": market.product.key,
        "product_label": f"{market.product.brand} {market.product.name} {market.product.spec}",
        "offer_id": best.get("id"),
        "channel": best.get("channel"),
        "shop_name": best.get("shop_name"),
        "price": best.get("price"),
        "cps_url": best.get("cps_url"),
        "cps_tracked": best.get("cps_tracked", False),
        "sub_id": best.get("sub_id"),
        "data_basis": market.basis,
    }
