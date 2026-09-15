"""行情聚合服务。

职责：把「商品对齐 → 多 Provider 取数 → 归一化 → 补 CPS 链接 → 标注数据来源」
串成一条链路，供 M1/M2/M3/M4 复用。业务规则不在此层重复实现（在 core.domain）。
"""
from __future__ import annotations

import logging

from core.catalog import Product, match_product
from core.config import settings
from core.domain import CHANNELS, normalize_offers, rank_offers
from core.errors import DomainError, NotFoundError, UpstreamError
from providers.base import ProviderNotConfigured, TTLCache
from providers.cps import build_sub_id, enrich_offers_with_links
from providers.live import build_registry

logger = logging.getLogger("caixuan.market")

_registry = None
_cache = TTLCache(ttl_seconds=settings.price_cache_ttl_seconds)


def registry():
    global _registry
    if _registry is None:
        _registry = build_registry()
    return _registry


def reset_registry() -> None:
    """测试用：重新装配并清缓存。"""
    global _registry
    _registry = build_registry()
    _cache.invalidate()


class MarketResult:
    """一次比价查询的完整结果。

    关于两类「缺数据」的口径区分（这是对用户最重要的诚实性信息）：
      · ``unavailable_channels``  —— 收录范围内、但本次**没拿到任何报价**的渠道
      · ``unconfigured_channels`` —— 联盟凭据**未接入**的渠道（数据若有，必来自种子）
    两者不能混为一谈：「未接入」说明的是我们的商务进度，而不是「现在没这个渠道」。
    """

    def __init__(
        self,
        product: Product,
        offers: list[dict],
        *,
        basis: str,
        sources: list[str],
        unavailable_channels: list[str],
        unconfigured_channels: list[str] | None = None,
        requested_spec: str | None = None,
        spec_matched: bool = True,
        note: str | None = None,
    ):
        self.product = product
        self.offers = offers
        self.basis = basis                    # live / seed / mixed
        self.sources = sources
        self.unavailable_channels = unavailable_channels
        self.unconfigured_channels = unconfigured_channels or []
        self.requested_spec = requested_spec
        self.spec_matched = spec_matched
        self.note = note


def resolve_product(query: str) -> tuple[Product, str | None, bool]:
    """输入 → 商品主数据。未收录时抛 NotFoundError（绝不回落其它商品）。"""
    res = match_product(query)
    if not res.ok or res.product is None:
        raise NotFoundError(
            "PRODUCT_NOT_LISTED",
            f"「{(query or '').strip()[:40]}」{res.unmatched_reason or '暂未收录'}。"
            "目前收录 6 款：雅诗兰黛小棕瓶、兰蔻小黑瓶、SK-II 神仙水、兰蔻菁纯面霜、"
            "资生堂红腰子、迪奥 999 口红。",
        )
    from core.catalog import spec_matches

    return res.product, res.requested_spec, spec_matches(res.product, res.requested_spec)


def _fetch_from_providers(product: Product) -> tuple[list[dict], str, list[str], list[str]]:
    """返回 (原始报价, basis, 命中的来源标注, 未接入的渠道)。"""
    reg = registry()
    mode = settings.data_mode.lower()
    collected: list[dict] = []
    sources: list[str] = []
    unconfigured: list[str] = []
    saw_live = False
    saw_seed = False

    seed_provider = reg.get("种子数据集")

    for p in reg.all():
        if p.channel == "种子数据集":
            continue
        if not p.is_configured():
            unconfigured.append(p.channel)
            continue
        try:
            rows = p.fetch(product)
        except ProviderNotConfigured:
            unconfigured.append(p.channel)
            continue
        except UpstreamError as exc:
            logger.warning("渠道 %s 取数失败：%s", p.channel, exc.message)
            unconfigured.append(p.channel)
            continue
        except Exception as exc:  # pragma: no cover - 防御性
            logger.exception("渠道 %s 取数异常", p.channel)
            unconfigured.append(p.channel)
            continue
        collected.extend(rows)
        sources.append(p.channel)
        saw_live = True

    # seed 模式 / hybrid 补齐：用内置数据集把缺失渠道补上
    need_seed = mode == "seed" or (mode == "hybrid" and not saw_live)
    if mode == "hybrid" and saw_live and seed_provider is not None:
        # hybrid：只为「未接入的渠道」补齐，避免与真实数据重复
        have = {str(r.get("channel")) for r in collected}
        missing = [c for c in CHANNELS if c not in have]
        if missing:
            try:
                rows = [r for r in seed_provider.fetch(product) if str(r.get("channel")) in missing]
                collected.extend(rows)
                saw_seed = True
                sources.append("种子数据集（补齐 " + "、".join(missing) + "）")
            except ProviderNotConfigured:
                pass
    elif need_seed and seed_provider is not None:
        try:
            collected.extend(seed_provider.fetch(product))
            saw_seed = True
            sources.append("种子数据集")
        except ProviderNotConfigured as exc:
            raise NotFoundError("PRODUCT_NOT_LISTED", str(exc)) from exc

    if not collected:
        raise UpstreamError(
            "NO_SOURCE_AVAILABLE",
            "所有数据源当前均不可用，请稍后重试。",
        )

    basis = "live" if saw_live and not saw_seed else ("seed" if saw_seed and not saw_live else "mixed")
    return collected, basis, sources, unconfigured


def get_offers(query: str, *, session_id: str | None = None) -> MarketResult:
    """主入口：查询词 → 归一化后的 5 渠道报价（含 CPS 链接）。"""
    product, requested_spec, spec_ok = resolve_product(query)

    cache_key = f"offers:{product.key}"
    cached = _cache.get(cache_key)
    if cached is None:
        raw, basis, sources, fetch_failures = _fetch_from_providers(product)
        offers = normalize_offers(raw, strict_derive=(settings.data_mode.lower() == "seed"))
        offers = rank_offers(offers)
        _cache.set(cache_key, (offers, basis, sources, fetch_failures))
    else:
        offers, basis, sources, fetch_failures = cached

    # 「未接入」= 收录范围内但联盟凭据缺失的渠道。这是**商务进度**的披露，
    # 与「本次没拿到报价」是两件事：种子模式会把未接入渠道补齐，
    # 此时若还把 5 个渠道都写成「未接入」，用户会误以为没有这几个渠道。
    configured = set(settings.configured_channels)
    unconfigured = [c for c in CHANNELS if c not in configured]
    for ch in fetch_failures:               # 已接入但本次取数失败的，也要如实列出
        if ch not in unconfigured:
            unconfigured.append(ch)

    # 「本次无报价」的渠道：由最终报价反推
    have = {str(o.get("channel")) for o in offers}
    unavailable = [c for c in CHANNELS if c not in have]

    sub_id = build_sub_id(session_id, product.key, "multi")
    offers = enrich_offers_with_links(product, offers, sub_id)

    notes: list[str] = []
    if not spec_ok and requested_spec:
        notes.append(
            f"你提到的是 {requested_spec}，当前收录规格为 {product.spec}，"
            f"价格按 {product.spec} 口径给出。"
        )
    if basis in ("seed", "mixed"):
        notes.append("当前展示为演示数据集，用于验证功能链路；接入联盟凭据后自动切换为真实行情。")
    if unavailable:
        notes.append(f"本次未取到报价的渠道：{'、'.join(unavailable)}。")

    return MarketResult(
        product=product,
        offers=offers,
        basis=basis,
        sources=sources,
        unavailable_channels=unavailable,
        unconfigured_channels=unconfigured,
        requested_spec=requested_spec,
        spec_matched=spec_ok,
        note=" ".join(notes) if notes else None,
    )


def lowest_of(offers: list[dict]) -> float:
    from core.domain import lowest_price

    return lowest_price(offers)


def clear_cache() -> None:
    _cache.invalidate()


def provider_status() -> list[dict]:
    reg = registry()
    out = []
    for st in reg.statuses():
        out.append({
            "channel": st.channel,
            "configured": st.configured,
            "mode": st.mode,
        })
    # 未在注册表里的渠道（live 模式下未配置就不会被注册）也要如实列出
    known = {x["channel"] for x in out}
    for ch in CHANNELS:
        if ch not in known:
            out.append({"channel": ch, "configured": False, "mode": "unavailable"})
    if settings.data_mode.lower() in ("seed", "hybrid"):
        out.append({"channel": "种子数据集", "configured": True, "mode": "seed"})
    return sorted(out, key=lambda x: (not x["configured"], x["channel"]))


__all__ = [
    "DomainError", "MarketResult", "clear_cache", "get_offers", "lowest_of",
    "provider_status", "registry", "reset_registry", "resolve_product",
]
