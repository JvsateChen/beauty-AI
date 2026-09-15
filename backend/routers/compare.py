"""M2 · 全网结构化比价看板（并聚合 M3 行情，一次请求渲染整页）。

四个维度：
  价格 —— 到手价 / 优惠拆解 / 30·90 天最低 / 档位
  版本 —— 国行 / 保税免税 / 海外版 差异对比
  风险 —— 临期预警 / 无专柜联保 / 捆绑消费溢价 / 第三方店铺售后风险
  优惠 —— 优惠券 / 平台满减 / 赠品折算 / 平台补贴

诚实性设计（这是本接口的重点）：
  · ``data_basis`` 明确标注本次数据是 live / seed / mixed
  · ``unavailable_channels`` 列出本次没取到数据的渠道，不再静默隐藏
  · ``sponsored`` 标出付费推广位，且排序算法保证它不影响名次
  · 商品未收录 → 404 + 明确文案，**不回落**到默认商品
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from core.config import settings
from core.db import get_session
from core.domain import absolute_lowest, cents_to_yuan, cheapest
from core.models import UserSession
from core.security import optional_session
from services import market as market_service
from services import trend as trend_service
from services import versions as versions_service

router = APIRouter()


@router.get("/result")
def get_compare_result(
    q: str = Query(..., min_length=1, max_length=100, description="商品查询词，如「小棕瓶」"),
    session: UserSession | None = Depends(optional_session),
    db: Session = Depends(get_session),
):
    market = market_service.get_offers(q, session_id=session.id if session else None)
    best = cheapest(market.offers)
    fact_lowest = absolute_lowest(market.offers)
    current = cents_to_yuan(best["price_cents"]) if best else 0.0
    trend = trend_service.get_trend(market.product, current, db=db)

    # 把行情结论与「最低」标记回填到每条报价，前端一次渲染即可。
    # 关键：is_lowest 由后端按「非赞助位最低」判定，前端不再用 price === lowest
    # 这种浮点相等比较（那正是旧实现把徽章发给赞助位的原因）。
    offers = []
    for o in market.offers:
        row = dict(o)
        row["history_30d_low"] = trend["low_30d"]
        row["history_90d_low"] = trend["low_90d"]
        row["price_level"] = trend["level"]
        row["is_lowest"] = bool(best and o.get("id") == best.get("id"))
        row["is_fact_lowest"] = bool(
            fact_lowest and o.get("id") == fact_lowest.get("id")
        )
        offers.append(row)

    # 落一次快照，使行情曲线能逐步由真实数据接管
    try:
        trend_service.record_snapshot(db, market.product.key, market.offers)
    except Exception:      # pragma: no cover - 快照失败不影响比价
        pass

    return {
        "query": q,
        "product": market.product.to_public(),
        "offers": offers,
        "versions": versions_service.get_version_compare(market.product, market.offers),
        "trend": trend,
        # 用于展示与徽章的「最低到手价」= 非赞助位最低（中立排序的结论）
        "lowest_price": cents_to_yuan(best["price_cents"]) if best else None,
        "lowest_label": (
            f"{best.get('channel')}·{best.get('shop_name')}" if best else None
        ),
        # 含赞助位的绝对最低价：单独披露，避免「藏在列表里」的质疑
        "absolute_lowest": (
            cents_to_yuan(fact_lowest["price_cents"]) if fact_lowest else None
        ),
        "absolute_lowest_channel": fact_lowest.get("channel") if fact_lowest else None,
        "absolute_lowest_is_sponsored": bool(
            fact_lowest and fact_lowest.get("sponsored")
        ),
        "deal_count": len(offers),
        "data_basis": market.basis,
        "data_sources": market.sources,
        "unavailable_channels": market.unavailable_channels,
        "unconfigured_channels": market.unconfigured_channels,
        "note": market.note,
        "price_label": settings.price_label,
        "disclaimer": settings.disclaimer,
    }


@router.get("/products")
def list_products():
    """已收录商品清单（前端做搜索建议 / 空态引导）。"""
    from core.catalog import CATALOG

    return {
        "count": len(CATALOG),
        "products": [
            {**p.to_public(), "aliases": list(p.aliases)} for p in CATALOG.values()
        ],
    }


@router.get("/sources")
def source_status():
    """数据源接入现状 —— 让「哪些渠道是真实数据、哪些未接入」对外可见。"""
    from core.config import settings as s

    return {
        "data_mode": s.data_mode,
        "data_source_label": s.data_source_label,
        "channels": market_service.provider_status(),
        "configured_channels": s.configured_channels,
        "note": (
            "seed 模式使用内置演示数据集用于功能验证；"
            "接入各渠道联盟凭据后将 DATA_MODE 置为 hybrid / live 即切换为真实行情。"
        ),
    }
