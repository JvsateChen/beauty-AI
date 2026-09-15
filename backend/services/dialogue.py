"""M1 · AI 对话选型的意图解析与五段式结论生成。

修复的三个硬伤：
  1. **预算误取规格** —— 旧实现用 ``(\\d{2,6})`` 抓预算，「小黑瓶 50ml」里的 50
     被当成预算，把规格读成价格是误导性错误。现在先把容量表达（50ml/3.5g）
     从待解析文本里剔除，再按「预算 / 元 / 块 / k / 千 / 万」等线索取数。
  2. **无匹配即回落小棕瓶** —— 用户问「娇韵诗双萃」却得到小棕瓶的答案，等于
     编造回答。现在走 core.catalog 的显式对齐，未收录就如实说未收录。
  3. **渠道串写死「四渠道」** —— 实际是 5 个渠道，文案与数据不一致。现在由
     实际报价动态生成（core.domain.describe_channels）。

输出两层：
  · ``sections`` —— 结构化五段（key/title/text），前端直接渲染，无需正则切块
  · ``reply``    —— 同一内容的纯文本拼接（保留给非结构化消费方 / 复制粘贴）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.catalog import CATALOG, Product, match_product, spec_matches
from core.config import settings
from core.domain import (
    cheapest,
    cents_to_yuan,
    describe_channels,
    RISK_TAGS,
    VERSIONS,
)
from services.market import MarketResult, get_offers
from services.versions import get_version_compare

# ---------------------------------------------------------------------------
# 词表
# ---------------------------------------------------------------------------

SKIN_TYPES: tuple[str, ...] = ("混油", "油皮", "干皮", "混干", "敏感肌", "痘肌", "中性")
NEEDS: tuple[str, ...] = (
    "抗初老", "抗老", "保湿", "美白", "修护", "紧致", "淡纹",
    "控油", "舒缓", "提亮", "祛痘", "彩妆", "显白",
)
CHANNEL_WORDS: tuple[tuple[str, str], ...] = (
    ("天猫", "天猫"), ("京东", "京东"), ("拼多多", "拼多多"),
    ("唯品会", "唯品会"), ("保税", "保税仓"), ("跨境", "保税仓"),
)
VERSION_WORDS = ("版本", "国行", "免税", "海外", "日版", "韩免", "欧版", "行货")
PRICE_WORDS = ("比价", "降价", "价格", "划算", "最低", "行情", "便宜", "贵")

#: 容量 / 重量表达 —— 解析预算前必须先剔除，否则 50ml 会被读成预算 50
_CAPACITY_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:ml|ML|mL|毫升|g|G|克|oz|OZ)")
_BUDGET_PATTERNS: tuple[tuple[re.Pattern[str], float], ...] = (
    (re.compile(r"(?:预算|最高|最多|不超过|控制在|大概|大约|价位)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*(万|w|k|千|元|块|rmb|RMB)?"), 1.0),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:元|块|rmb|RMB)\s*(?:以内|以下|左右|上下|内)?"), 1.0),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(万|w|W|k|K|千)\b"), 1.0),
)
_UNIT_MULT = {"万": 10000, "w": 10000, "W": 10000, "k": 1000, "K": 1000, "千": 1000}
BUDGET_MIN, BUDGET_MAX = 30, 100000


@dataclass
class Intent:
    raw: str
    budget: float | None = None
    skin_type: str | None = None
    needs: list[str] = field(default_factory=list)
    product_key: str | None = None
    matched_alias: str | None = None
    requested_spec: str | None = None
    channels_pref: list[str] = field(default_factory=list)
    asks_version: bool = False
    asks_price: bool = False
    #: 未收录时的原因；命中则为 None
    unmatched_reason: str | None = None

    def to_public(self) -> dict:
        return {
            "budget": self.budget,
            "skin_type": self.skin_type,
            "needs": self.needs,
            "product": self.product_key,
            "product_alias": self.matched_alias,
            "requested_spec": self.requested_spec,
            "channels_pref": self.channels_pref,
            "asks_version": self.asks_version,
            "asks_price": self.asks_price,
            "unmatched_reason": self.unmatched_reason,
        }


def parse_intent(text: str) -> Intent:
    raw = text or ""
    intent = Intent(raw=raw)

    # --- 预算（先剔除容量表达） ---
    masked = _CAPACITY_RE.sub(" ", raw)
    for pattern, _ in _BUDGET_PATTERNS:
        m = pattern.search(masked)
        if not m:
            continue
        try:
            num = float(m.group(1))
        except (TypeError, ValueError):
            continue
        unit = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        if unit in _UNIT_MULT:
            num *= _UNIT_MULT[unit]
        if BUDGET_MIN <= num <= BUDGET_MAX:
            intent.budget = num
            break

    # --- 肤质 / 诉求 ---
    intent.skin_type = next((s for s in SKIN_TYPES if s in raw), None)
    intent.needs = [n for n in NEEDS if n in raw]

    # --- 商品对齐（显式，绝不回落） ---
    res = match_product(raw)
    if res.ok and res.product is not None:
        intent.product_key = res.product.key
        intent.matched_alias = res.matched_alias
        intent.requested_spec = res.requested_spec
    else:
        intent.unmatched_reason = res.unmatched_reason
        intent.requested_spec = res.requested_spec

    # --- 渠道偏好 / 追问意图 ---
    intent.channels_pref = [std for w, std in CHANNEL_WORDS if w in raw]
    intent.channels_pref = list(dict.fromkeys(intent.channels_pref))
    intent.asks_version = any(w in raw for w in VERSION_WORDS)
    intent.asks_price = any(w in raw for w in PRICE_WORDS)
    return intent


# ---------------------------------------------------------------------------
# 无明确商品时的适配推荐（用主数据的肤质 / 诉求标签打分）
# ---------------------------------------------------------------------------

def recommend(intent: Intent, limit: int = 3) -> list[dict]:
    scored: list[tuple[float, Product, list[str]]] = []
    for p in CATALOG.values():
        score = 0.0
        why: list[str] = []
        if intent.skin_type and intent.skin_type in p.suited_skin:
            score += 3
            why.append(f"适配{intent.skin_type}")
        hit_needs = [n for n in intent.needs if n in p.suited_needs]
        if hit_needs:
            score += 2 * len(hit_needs)
            why.append("命中诉求 " + "、".join(hit_needs))
        if intent.budget:
            # 官方价在预算内的加 2 分；略超预算的按超出比例递减
            if p.list_price <= intent.budget:
                score += 2
                why.append(f"官方价 ¥{p.list_price:g} 在预算内")
            elif p.list_price <= intent.budget * 1.3:
                score += 1
                why.append(f"官方价 ¥{p.list_price:g} 略超预算（到手价通常更低）")
            else:
                score -= 1
        if not intent.skin_type and not intent.needs and not intent.budget:
            score += 1        # 无任何条件时按收录顺序给基线分
        if score > 0:
            scored.append((score, p, why))

    scored.sort(key=lambda x: (-x[0], x[1].list_price))
    return [
        {"key": p.key, "name": p.name, "brand": p.brand, "spec": p.spec,
         "category": p.category, "list_price": p.list_price, "why": why}
        for _, p, why in scored[:limit]
    ]


# ---------------------------------------------------------------------------
# 五段式渲染
# ---------------------------------------------------------------------------

SECTION_ORDER: tuple[tuple[str, str], ...] = (
    ("fit", "适配推荐"),
    ("price", "全网比价"),
    ("version", "版本差异"),
    ("advice", "入手建议"),
    ("risk", "风险提示"),
)


def _fit_section(intent: Intent, market: MarketResult | None, recs: list[dict]) -> dict:
    ctx: list[str] = []
    if intent.skin_type:
        ctx.append(f"肤质「{intent.skin_type}」")
    if intent.needs:
        ctx.append("诉求「" + "、".join(intent.needs) + "」")
    if intent.budget:
        ctx.append(f"预算 ¥{intent.budget:g}")
    head = ("按 " + " + ".join(ctx) + "，") if ctx else ""

    if market is not None:
        best = cheapest(market.offers)
        p = market.product
        lines: list[str] = []
        if ctx:
            lines.append("按 " + " + ".join(ctx))

        line = f"{head}已为你锁定 {p.brand} {p.name}（{p.spec}）"
        lines.append(f"已为你锁定 {p.brand} {p.name}（{p.spec}）")
        if best:
            line += (
                f"，当前最低到手价 ¥{cents_to_yuan(best['price_cents'])}"
                f"（{best.get('channel')}·{best.get('shop_name')}）"
            )
            lines.append(
                f"当前最低到手价 ¥{cents_to_yuan(best['price_cents'])}"
                f" · {best.get('channel')}·{best.get('shop_name')}"
            )
        line += "。"
        if not spec_matches(p, market.requested_spec):
            note = f"你提到的是 {market.requested_spec}，本次按收录规格 {p.spec} 的口径给价。"
            line += " " + note
            lines.append(note.rstrip("。"))
        return {"text": line, "lines": lines}

    # 未锁定具体商品 → 给候选清单（不假装答了用户的问题）
    if recs:
        items = "；".join(
            f"{r['brand']} {r['name']}（{r['spec']}，官方价 ¥{r['list_price']:g}）" for r in recs
        )
        lines = []
        if ctx:
            lines.append("按 " + " + ".join(ctx))
        lines.append(f"匹配到 {len(recs)} 款可选项")
        lines += [
            f"{r['brand']} {r['name']} · {r['spec']} · 官方价 ¥{r['list_price']:g}"
            for r in recs
        ]

        tail = f"{head}按你的条件匹配到 {len(recs)} 款可选项：{items}。"
        if intent.unmatched_reason:
            # 独立成句，避免与下一句粘连读作「该商品暂未收录 回复具体商品名」
            tail += f"{intent.unmatched_reason}。"
            lines.append(intent.unmatched_reason)
        tail += "回复具体商品名，我再给你五维结论。"
        lines.append("回复具体商品名，我再给你五维结论")
        return {"text": tail, "lines": lines}

    reason = intent.unmatched_reason or "暂未匹配到合适商品"
    catalog_hint = (
        "目前收录：雅诗兰黛小棕瓶、兰蔻小黑瓶、SK-II 神仙水、兰蔻菁纯面霜、"
        "资生堂红腰子、迪奥 999 口红"
    )
    return {
        "text": f"{reason}。{catalog_hint}。",
        "lines": [reason, catalog_hint],
    }


def _price_section(market: MarketResult | None) -> dict:
    if market is None or not market.offers:
        return {"text": "暂无可比报价。", "lines": ["暂无可比报价"]}

    ranked = market.offers
    rows = "；".join(
        f"{o['channel']}·{o['shop_name']} ¥{o['price']}"
        f"（{o['version']}{('·' + o['origin']) if o.get('origin') else ''}，"
        f"省 {o['drop_pct']}%）"
        for o in ranked
    )
    best = cheapest(ranked)
    channel_hint = describe_channels(ranked)

    parts = [f"{channel_hint} 共 {len(ranked)} 条报价，按到手价升序：{rows}。"]
    lines = [f"{channel_hint} 共 {len(ranked)} 条报价 · 按到手价升序"]

    if best:
        parts.append(
            f"最低为 {best['channel']}·{best['shop_name']} ¥{best['price']}"
            f"（官方价 ¥{best['list_price']}，优惠合计 ¥{best['benefit_total']}）。"
        )
        lines.append(
            f"最低 {best['channel']}·{best['shop_name']} ¥{best['price']}"
            f"（官方价 ¥{best['list_price']}，优惠合计 ¥{best['benefit_total']}）"
        )
    sponsored = [o for o in ranked if o.get("sponsored")]
    if sponsored:
        parts.append(
            "标注「赞助/佣金」的渠道为付费推广位，"
            "不参与排序、不影响名次，仅做信息披露。"
        )
        lines.append("标注「赞助/佣金」的为付费推广位 · 不参与排序")
    parts.append("到手价由「官方价 − 优惠券 − 平台满减 − 赠品折算 − 平台补贴」推导，可逐项复核。")
    lines.append("到手价由「官方价 − 优惠券 − 平台满减 − 赠品折算 − 平台补贴」推导，可逐项复核")
    if market.basis in ("seed", "mixed"):
        parts.append("【演示数据集】当前为功能验证用的内置数据，接入联盟凭据后自动切换为真实行情。")
        lines.append("演示数据集 · 接入联盟凭据后自动切换为真实行情")
    if market.unavailable_channels:
        parts.append(f"本次未取到数据的渠道：{'、'.join(market.unavailable_channels)}。")
        lines.append(f"本次未取到数据的渠道：{'、'.join(market.unavailable_channels)}")

    # 结构化报价行：前端渲染成对齐列表，避免把 5 条报价塞进一句话里
    items = [
        {
            "id": o.get("id"),
            "channel": o.get("channel"),
            "shop_name": o.get("shop_name"),
            "price": o.get("price"),
            "list_price": o.get("list_price"),
            "version": o.get("version"),
            "origin": o.get("origin"),
            "drop_pct": o.get("drop_pct"),
            "benefit_total": o.get("benefit_total"),
            "is_lowest": bool(best and o.get("id") == best.get("id")),
            "sponsored": bool(o.get("sponsored")),
            "risk_tags": list(o.get("risk_tags") or []),
        }
        for o in ranked
    ]
    return {"text": "".join(parts), "lines": lines, "items": items}


def _version_section(product: Product, offers: list[dict], intent: Intent) -> dict:
    rows = get_version_compare(product, offers)

    def _price_suffix(r: dict) -> str:
        return (
            f"最低 ¥{r['lowest_price']:g}" if r["lowest_price"] is not None
            else "本次无报价"
        )

    text = "；".join(
        f"{r['version']}：{r['warranty']}，{r['ingredient_diff']}（{_price_suffix(r)}）"
        for r in rows
    )
    lines = [
        f"{r['version']}（{_price_suffix(r)}）：{r['warranty']}；{r['ingredient_diff']}"
        for r in rows
    ]

    tail = (
        f"版本口径为 {' / '.join(VERSIONS)} 三类，日版 / 韩免 / 欧版属于「海外版」下的产地细分。"
        "本段仅为版本差异科普，不构成真伪判定，也不承诺正品。"
    )
    lines.append(
        f"版本口径为 {' / '.join(VERSIONS)} 三类 · 日版 / 韩免 / 欧版属「海外版」下的产地细分"
    )
    lines.append("本段仅为版本差异科普 · 不构成真伪判定，也不承诺正品")
    if intent.asks_version:
        tail += " 你问到版本差异，建议优先看「国内联保」与「保质期标注方式」两项。"
        lines.append("建议优先看「国内联保」与「保质期标注方式」两项")
    return {"text": f"{text}。{tail}", "lines": lines}


def _advice_section(market: MarketResult | None, trend: dict | None) -> dict:
    if not trend:
        return {
            "text": "行情数据暂不可用，无法判定当前档位。",
            "lines": ["行情数据暂不可用 · 无法判定当前档位"],
        }
    level = trend["level"]
    advice = trend["advice"]
    reason = trend["advice_reason"]
    extra = (
        f"90 天区间 ¥{trend['low_90d']:g} – ¥{trend['high_90d']:g}，"
        f"均价 ¥{trend['avg_90d']:g}，现价 ¥{trend['current']:g}。"
    )
    shape = trend.get("shape")
    shape_note = ""
    if shape and shape != "无数据":
        shape_note = f"走势形态识别为「{shape}」"
        if trend.get("fall_pct_from_peak"):
            shape_note += f"，较区间峰值回落 {trend['fall_pct_from_peak']}%"
        if trend.get("real_low_confirmed"):
            shape_note += "；区间低点已被后续反弹确认，属真实低点"
        shape_note += "。"
    basis_note = (
        "（行情基于内置演示数据集）" if trend.get("data_basis") == "seed" else ""
    )

    lines = [f"90 天行情「{level}」区间 · 建议：{advice}"]
    if reason:
        lines.append(reason.rstrip("。"))
    lines.append(
        f"90 天区间 ¥{trend['low_90d']:g} – ¥{trend['high_90d']:g}"
        f" · 均价 ¥{trend['avg_90d']:g} · 现价 ¥{trend['current']:g}"
    )
    if shape_note:
        lines.append(shape_note.rstrip("。"))
    if basis_note:
        lines.append("行情基于内置演示数据集")
    return {
        "text": f"当前处于 90 天行情「{level}」区间，建议：{advice}。{reason}{extra}{shape_note}{basis_note}",
        "lines": lines,
    }


def _risk_section(market: MarketResult | None) -> dict:
    lines: list[str] = []
    if market is None or not market.offers:
        body = "暂无可筛查的报价。"
        lines.append("暂无可筛查的报价")
    else:
        hits: dict[str, list[str]] = {}
        for o in market.offers:
            for t in o.get("risk_tags") or []:
                hits.setdefault(t, []).append(f"{o['channel']}·{o['shop_name']}")
        if hits:
            body = "本次命中的风险标签：" + "；".join(
                f"{t}（{'、'.join(v)}）" for t, v in hits.items()
            ) + "。"
            lines += [f"{t} · {'、'.join(v)}" for t, v in hits.items()]
        else:
            body = "本次报价未命中四大风险标签。"
            lines.append("本次报价未命中四大风险标签")
        missing = [t for t in RISK_TAGS if t not in hits]
        if missing:
            body += f" 未命中的标签：{'、'.join(missing)}。"
            lines.append(f"未命中：{'、'.join(missing)}")

    # 全站顶部已有免责条，这里只保留与风险筛查直接相关的一句，避免整页重复同一段话
    lines.append("本平台仅做风险筛查与提示 · 不提供真伪鉴定服务、不承诺正品")
    return {
        "text": (
            body
            + " 本平台仅做风险筛查与提示，不提供真伪鉴定服务、不承诺正品；"
            "商品正品性与售后维权由跳转电商平台全权负责。所有价格为行情参考价，非锁定成交价。"
        ),
        "lines": lines,
    }



def build_sections(
    *,
    intent: Intent,
    market: MarketResult | None,
    trend: dict | None,
    recs: list[dict],
) -> list[dict]:
    product = market.product if market else None
    offers = market.offers if market else []

    no_version = {
        "text": "未锁定具体商品，暂不做版本对比。",
        "lines": ["未锁定具体商品 · 暂不做版本对比"],
    }
    bodies = {
        "fit": _fit_section(intent, market, recs),
        "price": _price_section(market),
        "version": (
            _version_section(product, offers, intent) if product else no_version
        ),
        "advice": _advice_section(market, trend),
        "risk": _risk_section(market),
    }

    out: list[dict] = []
    for key, title in SECTION_ORDER:
        body = bodies[key]
        section: dict = {
            "key": key,
            "title": title,
            # text 为纯文本版（复制粘贴 / 非结构化消费方），与 reply 完全一致
            "text": body["text"].strip(),
            # lines 为结构化要点，前端按行渲染，避免整段结论挤成一大坨纯文字
            "lines": [ln for ln in body.get("lines", []) if ln],
        }
        if body.get("items"):
            section["items"] = body["items"]
        out.append(section)
    return out


def render_reply(sections: list[dict]) -> str:
    return "\n\n".join(f"【{s['title']}】{s['text']}" for s in sections)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def chat(text: str, *, session_id: str | None = None, db=None) -> dict:
    """一次对话：解析意图 → 取行情 → 生成五段结论。

    商品未收录时**不报错**，转为推荐候选 + 明确说明，保证对话不中断。
    """
    from services.trend import get_trend

    intent = parse_intent(text)
    market: MarketResult | None = None
    trend: dict | None = None
    recs: list[dict] = []

    if intent.product_key:
        market = get_offers(intent.product_key, session_id=session_id)
        best = cheapest(market.offers)
        current = cents_to_yuan(best["price_cents"]) if best else 0.0
        trend = get_trend(market.product, current, db=db)
        # 记录一次真实快照，让行情曲线随时间积累真实数据
        if db is not None:
            try:
                from services.trend import record_snapshot

                record_snapshot(db, market.product.key, market.offers)
            except Exception:      # pragma: no cover - 快照失败不影响对话
                pass
    else:
        recs = recommend(intent)

    sections = build_sections(intent=intent, market=market, trend=trend, recs=recs)
    product_key = intent.product_key

    return {
        "intent": intent.to_public(),
        "sections": sections,
        "reply": render_reply(sections),
        "product_key": product_key,
        "product_label": (
            f"{market.product.brand} {market.product.name}" if market else None
        ),
        "suggestions": [
            r["key"] for r in recs
        ] or (["小棕瓶", "小黑瓶", "神仙水", "菁纯", "红腰子", "迪奥999"]
              if market is None else []),
        "data_basis": market.basis if market else None,
        "data_sources": market.sources if market else [],
        "unavailable_channels": market.unavailable_channels if market else [],
        "note": market.note if market else None,
        "disclaimer": settings.disclaimer,
    }


__all__ = [
    "Intent", "SECTION_ORDER", "build_sections", "chat", "parse_intent",
    "recommend", "render_reply",
]
