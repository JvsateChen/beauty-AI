"""M3 · 90 天价格行情服务。

修复三个问题：
  1. 旧实现所有商品套同一个「下行模板」→ 等价于默认每款都「先涨后降」，
     PRD 的「识别先涨后降与真实低点」从未实现。现在用 core.domain 的真实
     形态识别（峰值/谷值位置 + 反弹确认）得出结论。
  2. 旧实现用 `date.today()` 生成相对序列，导致历史值随「今天」整体漂移，
     「90 天最低价」不稳定、会被用户质疑。现在以**绝对日期**为输入的函数
     生成序列：同一天同一商品的价格恒定，滚动窗口的滑动是真实语义。
  3. 旧实现按商品 hash 伪造「618 大促 / 暑期大促」标注。现在下探只发生在
     **真实大促日历窗**内，标注即事实。

数据来源优先级：
  1. price_snapshot 表里的真实轮询快照（≥20 个点才用）→ data_basis="snapshot"
  2. 内置种子序列 → data_basis="seed"（响应里如实标注）
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta

from core.catalog import Product
from core.domain import (
    classify_level,
    detect_low_windows,
    detect_trend_shape,
    promo_label,
)
from core.models import PriceSnapshot

#: 序列锚点：所有合成价格都是「商品 + 绝对日期」的纯函数，保证可复现、不漂移
_ANCHOR = date(2026, 1, 1)

#: 真实大促窗内的下探系数（按日历给，不按商品给）
_PROMO_DIP: dict[str, float] = {
    "618 大促期": 0.93,
    "双 11 大促期": 0.90,
    "双 12 大促期": 0.945,
    "年货节": 0.95,
    "38 大促期": 0.96,
}


def _synthetic_factor(key: str, d: date) -> float:
    """同一天同一商品恒定的价格系数（含轻微长期衰减 + 大促真实下探 + 日常噪声）。"""
    raw = hashlib.md5(f"{key}:{d.isoformat()}".encode("utf-8")).hexdigest()
    noise = 1 + ((int(raw[:6], 16) % 1000) / 1000.0 - 0.5) * 0.05   # ±2.5% 日常波动
    # 越接近锚点越贵（长期缓慢下行），用指数衰减表达自然掉价
    days = (d - _ANCHOR).days
    decay = 1.0 + 0.07 * math.exp(-max(days, 0) / 300.0)
    dip = _PROMO_DIP.get(promo_label(d) or "", 1.0)
    return noise * decay * dip


def build_seed_series(product_key: str, current_price: float, days: int = 90,
                      today: date | None = None) -> list[dict]:
    """构造与「当前到手价」自洽的 90 天序列（最后一个点 == 当前到手价）。"""
    today = today or date.today()
    dates = [today - timedelta(days=days - 1 - i) for i in range(days)]
    factors = [_synthetic_factor(product_key, d) for d in dates]

    last_factor = factors[-1] or 1.0
    scale = (current_price / last_factor) if last_factor else current_price

    points: list[dict] = []
    for d, f in zip(dates, factors):
        points.append({
            "date": d.isoformat(),
            "price": round(f * scale, 2),
            "event": promo_label(d),
        })
    points[-1]["price"] = round(current_price, 2)
    points[-1]["event"] = None
    return points


def build_snapshot_series(
    rows: list[PriceSnapshot], current_price: float, days: int = 90,
    today: date | None = None,
) -> list[dict]:
    """把真实快照按日聚合成曲线（同一日多条取最低，作为「全网最低到手价」历史）。"""
    today = today or date.today()
    per_day: dict[str, float] = {}
    for r in rows:
        d = r.captured_at.date().isoformat()
        price = r.lowest_price_cents if r.lowest_price_cents else r.price_cents
        val = price / 100.0
        if d not in per_day or val < per_day[d]:
            per_day[d] = val

    start = today - timedelta(days=days - 1)
    points: list[dict] = []
    for i in range(days):
        d = start + timedelta(days=i)
        iso = d.isoformat()
        if iso in per_day:
            points.append({"date": iso, "price": round(per_day[iso], 2),
                           "event": promo_label(d)})
    if points:
        points[-1]["price"] = round(current_price, 2)
        points[-1]["event"] = None
    return points


def get_trend(
    product: Product,
    current_price: float,
    *,
    db=None,
    days: int = 90,
) -> dict:
    """返回 90 天行情：曲线点、区间统计、档位与建议、形态识别结果。"""
    points: list[dict] = []
    basis = "seed"

    # 1) 真实快照优先
    if db is not None:
        try:
            since = date.today() - timedelta(days=days)
            rows = (
                db.query(PriceSnapshot)
                .filter(
                    PriceSnapshot.product_key == product.key,
                    PriceSnapshot.captured_at >= _as_dt(since),
                )
                .order_by(PriceSnapshot.captured_at.asc())
                .all()
            )
            if len({r.captured_at.date() for r in rows}) >= 20:
                points = build_snapshot_series(rows, current_price, days)
                basis = "snapshot"
        except Exception:  # pragma: no cover - 快照不可用时静默降级
            points = []

    # 2) 种子序列兜底
    if not points:
        points = build_seed_series(product.key, current_price, days)

    prices = [p["price"] for p in points]
    low_90 = round(min(prices), 2)
    high_90 = round(max(prices), 2)
    low_30 = round(min(prices[-30:]), 2) if len(prices) >= 30 else low_90
    avg_90 = round(sum(prices) / len(prices), 2)
    now = round(float(current_price), 2)

    level, advice, reason = classify_level(now, low_90, high_90, avg_90)
    shape_info = detect_trend_shape(prices)
    low_windows = detect_low_windows(points)

    return {
        "days": days,
        "points": points,
        "low_90d": low_90,
        "high_90d": high_90,
        "low_30d": low_30,
        "avg_90d": avg_90,
        "current": now,
        "level": level,
        "advice": advice,
        "advice_reason": reason,
        # 形态识别（真实算法结论，不是模板）
        "shape": shape_info["shape"],
        "rise_then_fall": shape_info["rise_then_fall"],
        "fall_pct_from_peak": shape_info["fall_pct_from_peak"],
        "rebound_after_low": shape_info["rebound_after_low"],
        "real_low_confirmed": shape_info["real_low_confirmed"],
        "peak": shape_info["peak"],
        "trough": shape_info["trough"],
        "promo_points": low_windows,
        "data_basis": basis,
        # 兼容旧字段名
        "disclaimer": "以上为行情参考价，非锁定成交价；实际以下单页实际结算为准。",
    }


def _as_dt(d: date):
    from datetime import datetime, timezone

    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def record_snapshot(db, product_key: str, offers: list[dict]) -> int:
    """把一次比价结果写入快照表（供行情曲线用真实数据）。返回写入条数。"""
    from core.domain import cheapest  # 局部导入避免循环

    best = cheapest(offers)
    lowest_cents = best["price_cents"] if best else None
    n = 0
    for o in offers:
        db.add(PriceSnapshot(
            product_key=product_key,
            offer_id=str(o.get("id")),
            channel=str(o.get("channel")),
            version=o.get("version"),
            price_cents=int(o.get("price_cents", 0)),
            list_price_cents=int(round(float(o.get("list_price", 0)) * 100)),
            lowest_price_cents=lowest_cents,
        ))
        n += 1
    return n
