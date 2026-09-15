"""领域常量与商业计算（全项目唯一口径来源）。

本模块是「口径」的单一权威：
  · 渠道 / 版本 / 风险标签 / 价格档位 的枚举与白名单
  · 到手价推导与自洽校验（消除手填常量与浮点比较问题）
  · 90 天价格档位判定
  · 行情形态识别（先涨后降 / 真实低点）—— 真实算法，非模板套用

设计原则：
  1. 金额一律以「分」为单位做整数运算，对外再转回元（2 位小数）。
     这样彻底消除 `0.1+0.2`、`o.price === lowest` 这类浮点相等失效问题。
  2. 任何派生结论都必须可复算：给定同样的输入，输出必须一致且可通过单测。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# 枚举与白名单
# ---------------------------------------------------------------------------

#: 比价看板聚合的 5 个渠道
CHANNELS: tuple[str, ...] = ("天猫", "京东", "拼多多", "唯品会", "保税仓")

#: AI 默认优先对比的 4 个核心渠道
CORE_CHANNELS: tuple[str, ...] = ("天猫自营", "京东自营", "保税仓", "拼多多品牌店")

#: 版本（3 类主版本；日版 / 韩免 / 欧版为「海外版」下的产地细分）
VERSIONS: tuple[str, ...] = ("国行", "保税免税", "海外版")
VERSION_ORDER: dict[str, int] = {v: i for i, v in enumerate(VERSIONS)}

#: 风险标签（全站只允许这四个）
RISK_TAGS: tuple[str, ...] = (
    "临期预警",
    "无专柜联保",
    "捆绑消费溢价",
    "第三方店铺售后风险",
)

#: 价格档位 -> 建议
LEVEL_ADVICE: dict[str, str] = {
    "低位": "低位囤货",
    "中位": "立即入手",
    "高位": "观望等待",
}

#: 档位阈值（可被 Settings.near_expiry_months 之外独立调整）
LOW_BAND = 1.03   # 现价 ≤ 90 天最低价 × 1.03 → 低位
HIGH_BAND = 0.97  # 现价 ≥ 90 天最高价 × 0.97 → 高位

#: 优惠四要素字段名（顺序即前端展示顺序）
BENEFIT_KEYS: tuple[str, ...] = (
    "coupon",          # 优惠券
    "platform_discount",  # 平台满减
    "gift_value",      # 赠品折算
    "subsidy",         # 平台补贴
)
BENEFIT_LABELS: dict[str, str] = {
    "coupon": "优惠券",
    "platform_discount": "平台满减",
    "gift_value": "赠品折算",
    "subsidy": "平台补贴",
}

#: 「行情参考价」统一标注
PRICE_LABEL = "行情参考价"


# ---------------------------------------------------------------------------
# 金额工具：分 <-> 元
# ---------------------------------------------------------------------------

def yuan_to_cents(v: Any) -> int:
    """元 → 分（四舍五入到分）。非法/空值按 0 处理。"""
    if v is None:
        return 0
    try:
        return int(round(float(v) * 100))
    except (TypeError, ValueError):
        return 0


def cents_to_yuan(c: int) -> float:
    """分 → 元（保留 2 位小数，避免 0.1+0.2 类误差外泄到 JSON）。"""
    return round(int(c) / 100.0, 2)


# ---------------------------------------------------------------------------
# 到手价推导与自洽校验
# ---------------------------------------------------------------------------

def derive_benefit_total_cents(raw: dict) -> int:
    b = raw.get("benefits") or {}
    return sum(yuan_to_cents(b.get(k, 0)) for k in BENEFIT_KEYS)


def normalize_offer(raw: dict, *, strict_derive: bool = True) -> dict:
    """归一化一条报价，并补齐全部派生字段。

    Parameters
    ----------
    raw
        原始报价。必需：channel / shop_name / version / list_price。
    strict_derive
        True（默认，内置种子数据集）—— 到手价由 ``官方价 - 优惠合计`` 推导，
        保证「价格」与「优惠拆解」数学自洽，杜绝手填常量。
        False（真实数据源）—— 以平台给出的到手价为准，同时校验与推导值的偏差，
        偏差超过容差时在响应里留下 ``price_consistent=False`` 供前端提示。

    派生字段：
        price_cents / price       到手价（元）
        benefit_total_cents / benefit_total  优惠合计（元）
        drop_pct                  相对官方价的降幅
        risk_tags                 过滤白名单后的标签 + 临期阈值自动打标
        price_consistent          价格与优惠拆解是否自洽
    """
    out = dict(raw)

    list_cents = yuan_to_cents(out.get("list_price"))
    benefit_cents = derive_benefit_total_cents(out)

    if strict_derive or out.get("price") is None:
        price_cents = list_cents - benefit_cents
        consistent = True
    else:
        price_cents = yuan_to_cents(out.get("price"))
        consistent = (list_cents - benefit_cents) == price_cents

    # 到手价不得为负（脏数据兜底：钳到 0 并标记不自洽）
    if price_cents < 0:
        price_cents = 0
        consistent = False

    out["list_price"] = cents_to_yuan(list_cents)
    out["price_cents"] = price_cents
    out["price"] = cents_to_yuan(price_cents)
    out["benefit_total_cents"] = benefit_cents
    out["benefit_total"] = cents_to_yuan(benefit_cents)
    out["price_consistent"] = consistent
    out["drop_pct"] = (
        round((1 - price_cents / list_cents) * 100, 1) if list_cents > 0 else 0.0
    )

    # 风险标签：只保留白名单内的，防脏数据绕过合规口径
    tags = [t for t in (out.get("risk_tags") or []) if t in RISK_TAGS]
    out["risk_tags"] = tags

    # 临期阈值：剩余保质期 ≤ N 个月自动打标（不依赖数据源是否手工标了）
    months = out.get("shelf_life_months")
    if months is not None:
        try:
            if float(months) <= _near_expiry_months():
                if "临期预警" not in tags:
                    out["risk_tags"].append("临期预警")
        except (TypeError, ValueError):
            pass

    return out


def _near_expiry_months() -> int:
    # 延迟导入避免 config <-> domain 循环依赖
    from core.config import settings

    return settings.near_expiry_months


def normalize_offers(offers: Iterable[dict], *, strict_derive: bool = True) -> list[dict]:
    return [normalize_offer(o, strict_derive=strict_derive) for o in offers]


def rank_offers(offers: list[dict]) -> list[dict]:
    """默认排序 —— **赞助位不参与默认排序，且永不置顶**。

    合规承诺的落地方式：
      · 排序键是 ``(是否赞助, 到手价)``：先排全部非赞助位（按到手价升序），
        再把赞助位按到手价升序排在后面；
      · 因此「付费买名次」这条路径在算法层被彻底关闭 —— 无论赞助位多便宜，
        它都不会占据列表首位，真正的低价位也不会被付费位挤下去；
      · 赞助位的**真实价格照常展示**（价格是客观事实，不因赞助而隐藏），
        但「最低到手价」徽章只授予非赞助位，见 ``cheapest()``；
      · 全场事实最低价（含赞助位）由 ``lowest_price()`` 单独给出，
        需要时可作为「绝对最低」另行披露，不用于排序。
    """
    return sorted(
        offers,
        key=lambda o: (bool(o.get("sponsored")), o.get("price_cents", 0)),
    )


def cheapest(offers: list[dict]) -> dict | None:
    """「最低到手价」对应的报价 —— 排除赞助位。"""
    pool = [o for o in offers if not o.get("sponsored")] or offers
    if not pool:
        return None
    return min(pool, key=lambda o: o.get("price_cents", 0))


def absolute_lowest(offers: list[dict]) -> dict | None:
    """全场事实最低（含赞助位）。价格是客观事实，不因赞助而隐瞒。

    与 ``cheapest()`` 的区别：本函数可能返回赞助位，仅供「绝对最低价」披露，
    **不得**用于给赞助位颁发「最低到手价」徽章。
    """
    if not offers:
        return None
    return min(offers, key=lambda o: o.get("price_cents", 0))


def lowest_price(offers: list[dict]) -> float:
    """全场最低到手价（事实值，含赞助位）。"""
    if not offers:
        return 0.0
    return cents_to_yuan(min(o.get("price_cents", 0) for o in offers))


# ---------------------------------------------------------------------------
# 价格档位判定
# ---------------------------------------------------------------------------

def classify_level(
    current: float,
    low_90d: float,
    high_90d: float,
    avg_90d: float,
) -> tuple[str, str, str]:
    """返回 (档位, 建议, 理由)。

    规则（与 PRD 一致）：
      现价 ≤ 90 天最低 × 1.03 → 低位
      现价 ≥ 90 天最高 × 0.97 → 高位
      其余 → 中位（低于均价给「立即入手」，高于均价给「观望等待」）
    """
    c = float(current)
    if low_90d > 0 and c <= low_90d * LOW_BAND:
        return (
            "低位",
            "低位囤货",
            f"当前价 ¥{c:g} 已贴近 90 天最低价 ¥{low_90d:g}，处于历史低位区间。",
        )
    if high_90d > 0 and c >= high_90d * HIGH_BAND:
        return (
            "高位",
            "观望等待",
            f"当前价 ¥{c:g} 处于 90 天高位（90 天最高 ¥{high_90d:g}），非急用建议等待大促。",
        )
    if c <= avg_90d:
        return (
            "中位",
            "立即入手",
            f"当前价 ¥{c:g} 低于 90 天均价 ¥{avg_90d:g}，属于中位偏下，可按需入手。",
        )
    return (
        "中位",
        "观望等待",
        f"当前价 ¥{c:g} 高于 90 天均价 ¥{avg_90d:g}，刚需可入、非急用可再观望。",
    )


# ---------------------------------------------------------------------------
# 行情形态识别（真实算法）
# ---------------------------------------------------------------------------

#: 真实的中国电商大促时间窗（用于给「真实价格低点」贴日历标签，非伪造）
_PROMO_WINDOWS: tuple[tuple[tuple[int, int], tuple[int, int], str], ...] = (
    ((5, 24), (6, 20), "618 大促期"),
    ((10, 24), (11, 13), "双 11 大促期"),
    ((12, 10), (12, 13), "双 12 大促期"),
    ((2, 1), (2, 18), "年货节"),
    ((3, 1), (3, 10), "38 大促期"),
)


def promo_label(d: date) -> str | None:
    """日期落在真实大促窗内则返回标签，否则 None。"""
    for (m1, d1), (m2, d2), label in _PROMO_WINDOWS:
        if m1 == m2:
            if d.month == m1 and d1 <= d.day <= d2:
                return label
        elif (d.month == m1 and d.day >= d1) or (d.month == m2 and d.day <= d2):
            return label
    return None


def detect_trend_shape(prices: list[float]) -> dict:
    """识别 90 天价格形态。

    返回：
        shape           先涨后降 / 先降后涨 / 持续下行 / 持续上行 / 区间震荡
        peak            {index, date_index, price}
        trough          {index, price}
        rise_then_fall  是否存在「前期高点 → 现价明显回落」
        fall_pct_from_peak  现价相对峰值回落百分比
        low_at           90 天最低价所在下标
        rebound_after_low 最低点之后的最大反弹幅度
        real_low_confirmed  最低点是否已被后续反弹确认（而非「最低点就是今天」）
    """
    n = len(prices)
    if n == 0:
        return {
            "shape": "无数据", "peak": None, "trough": None,
            "rise_then_fall": False, "fall_pct_from_peak": 0.0,
            "low_at": None, "rebound_after_low": 0.0, "real_low_confirmed": False,
        }

    peak_idx = max(range(n), key=lambda i: prices[i])
    low_idx = min(range(n), key=lambda i: prices[i])
    peak_px, low_px, last_px = prices[peak_idx], prices[low_idx], prices[-1]
    first_px = prices[0]

    fall_from_peak = round((peak_px - last_px) / peak_px * 100, 2) if peak_px else 0.0
    rebound = (
        round((max(prices[low_idx:]) - low_px) / low_px * 100, 2)
        if low_px and low_idx < n - 1
        else 0.0
    )
    # 最低点后至少留 3 天观察窗，且已反弹 ≥1%，才算「真实低点被确认」
    real_low = bool(low_idx <= n - 4 and rebound >= 1.0)

    # 形态：看前 1/3 与后 1/3 的中位数走向
    third = max(1, n // 3)
    head = sorted(prices[:third])[third // 2]
    tail = sorted(prices[-third:])[third // 2]
    overall_up = tail > head * 1.03
    overall_down = tail < head * 0.97

    # 判定顺序很关键（早期版本把单调上行误判成「先降后涨」，因为最低点必然在起点）：
    #   1/2 先排除「整体单边」的情形；「持续下行」要求峰值在起点、现价不高于起点、
    #       且低点之后没有像样反弹 —— 否则「跌下去又涨回来」会被误说成一路下行
    #   3/4 再看是否存在「真实前高回落」或「真实前低回升」——用「起点是否远离极值」
    #       来证明前段确实反向走过，避免把单调序列硬说成「先跌」或「先涨」
    #   5/6 兜底用整体走向
    if peak_idx == 0 and last_px <= first_px and rebound < 3.0:
        shape = "持续下行"
    elif low_idx == n - 1 and last_px >= first_px * 1.03:
        shape = "持续上行"
    elif peak_idx < n * 0.6 and last_px < peak_px * 0.97:
        shape = "先涨后降"
    elif low_idx < n * 0.6 and first_px > low_px * 1.01 and last_px > low_px * 1.03:
        shape = "先降后涨"
    elif overall_up:
        shape = "持续上行"
    elif overall_down:
        shape = "持续下行"
    else:
        shape = "区间震荡"

    return {
        "shape": shape,
        "peak": {"index": peak_idx, "price": round(peak_px, 2)},
        "trough": {"index": low_idx, "price": round(low_px, 2)},
        "rise_then_fall": shape == "先涨后降",
        "fall_pct_from_peak": fall_from_peak,
        "low_at": low_idx,
        "rebound_after_low": rebound,
        "real_low_confirmed": real_low,
        "first_price": round(first_px, 2),
        "last_price": round(last_px, 2),
    }


def detect_low_windows(points: list[dict], window: int = 2, drop: float = 0.97) -> list[dict]:
    """在真实序列上找「价格低点窗口」——局部极小且显著低于周边。

    与旧实现的区别：低点来自**实际数据**，不再是按商品 hash 伪造下探。
    同时用真实大促日历给窗口贴标签，无标签的只称「价格低点」。
    """
    prices = [p["price"] for p in points]
    n = len(prices)
    out: list[dict] = []
    for i in range(window, n - window):
        seg = prices[i - window: i + window + 1]
        if prices[i] != min(seg):
            continue
        neighbours = [p for j, p in enumerate(seg) if j != window]
        avg = sum(neighbours) / len(neighbours)
        if avg <= 0 or prices[i] > avg * drop:
            continue
        label = None
        try:
            label = promo_label(date.fromisoformat(points[i]["date"]))
        except (ValueError, KeyError, TypeError):
            label = None
        out.append({
            "index": i,
            "date": points[i]["date"],
            "price": round(prices[i], 2),
            "discount_pct": round((1 - prices[i] / avg) * 100, 1),
            "event": label or "价格低点",
        })
    # 按跌幅取前 6 个，日期升序
    out.sort(key=lambda x: -x["discount_pct"])
    out = sorted(out[:6], key=lambda x: x["date"])
    return out


# ---------------------------------------------------------------------------
# 渠道 / 文案工具
# ---------------------------------------------------------------------------

def describe_channels(offers: list[dict]) -> str:
    """由**实际报价**生成渠道串，避免文案写死「四渠道」与实际不符。"""
    seen: list[str] = []
    for o in offers:
        ch = str(o.get("channel", "")).strip()
        if ch and ch not in seen:
            seen.append(ch)
    return " / ".join(seen) if seen else "暂无渠道报价"


def sanitize_risk_tags(tags: Iterable[str]) -> list[str]:
    return [t for t in tags if t in RISK_TAGS]
