"""M3 · 价格行情曲线。

返回 90 天序列 + 区间统计 + 档位建议 + **真实形态识别**结果。

诚实性设计：
  · ``data_basis`` 标注曲线来自真实快照（snapshot）还是内置序列（seed）
  · 低点窗口只在真实大促日历窗内贴「618 / 双 11」标签，否则只叫「价格低点」
  · 序列以**绝对日期**为锚，同一天同一商品的价格恒定，不会随「今天」整体漂移
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.db import get_session
from core.domain import cents_to_yuan, cheapest
from core.errors import DomainError
from core.models import UserSession
from core.security import optional_session
from services import market as market_service
from services import trend as trend_service

router = APIRouter()

_ALLOWED_DAYS = (30, 90, 180)


@router.get("/series")
def get_series(
    q: str = Query(..., min_length=1, max_length=100, description="商品查询词"),
    days: int = Query(90, description="窗口天数：30 / 90 / 180"),
    session: UserSession | None = Depends(optional_session),
    db: Session = Depends(get_session),
):
    if days not in _ALLOWED_DAYS:
        raise DomainError(
            "INVALID_PARAM", f"窗口仅支持 {'、'.join(str(d) for d in _ALLOWED_DAYS)} 天。"
        )

    market = market_service.get_offers(q, session_id=session.id if session else None)
    best = cheapest(market.offers)
    current = cents_to_yuan(best["price_cents"]) if best else 0.0

    trend = trend_service.get_trend(market.product, current, db=db, days=days)
    return {
        "query": q,
        "product": market.product.to_public(),
        "current_lowest": current,
        "current_label": f"{best.get('channel')}·{best.get('shop_name')}" if best else None,
        **trend,
    }


@router.get("/lowest")
def get_lowest(
    q: str = Query(..., min_length=1, max_length=100),
    db: Session = Depends(get_session),
):
    """轻量接口：只回最低价与档位判断，供列表页 / 提醒卡片快速取值。"""
    market = market_service.get_offers(q)
    best = cheapest(market.offers)
    current = cents_to_yuan(best["price_cents"]) if best else 0.0
    trend = trend_service.get_trend(market.product, current, db=db)
    return {
        "product_key": market.product.key,
        "product_label": f"{market.product.brand} {market.product.name} {market.product.spec}",
        "lowest": current,
        "lowest_channel": best.get("channel") if best else None,
        "level": trend["level"],
        "advice": trend["advice"],
        "low_90d": trend["low_90d"],
        "high_90d": trend["high_90d"],
        "avg_90d": trend["avg_90d"],
        "shape": trend["shape"],
        "data_basis": trend["data_basis"],
    }
