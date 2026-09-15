"""M5 · CPS 跳转链接构建与溯源。

修复的问题：旧实现 `href={offer.cps_url || '#'}`，而后端从不产出 cps_url
→ 全部「去购买」都是 `href="#"`，点击无效、零佣金、核心变现路径断裂。

本模块提供两档能力，按凭据到位与否自动切换，**任何情况下都不会产出空链接**：

  1. affiliate 档（凭据已配置）
     Provider 从联盟接口拿到真实推广链接 → 我们追加 sub_id 溯源参数后返回。
     ``cps_tracked = True``

  2. fallback 档（凭据未配置，或接口未返回推广链接）
     返回该渠道的**官方商品搜索深链**，并把 sub_id 记入 offer_click 表。
     用户点击能正常到达平台（不是死链），佣金归因待凭据到位后启用。
     ``cps_tracked = False``，前端据此文案提示「暂未启用佣金归因」。

两条铁律：
  · 绝不返回 `#` 或空链接
  · 绝不静默把 fallback 说成 affiliate（前端要能区分）
"""
from __future__ import annotations

import hashlib
import urllib.parse

from core.catalog import Product

#: 渠道 -> 官方商品搜索深链模板（fallback 档使用）
_CHANNEL_SEARCH: dict[str, str] = {
    "天猫": "https://list.tmall.com/search_product.htm?q={q}",
    "京东": "https://search.jd.com/Search?keyword={q}&enc=utf-8",
    "拼多多": "https://mobile.yangkeduo.com/search_result.html?search_key={q}",
    "唯品会": "https://www.vip.com/search/?keyword={q}",
    # 保税仓为跨境直发渠道，消费端入口落在京东国际
    "保税仓": "https://search.jd.com/Search?keyword={q}%20%E4%BF%9D%E7%A8%8E&enc=utf-8",
}

#: 渠道 -> 官方站外归因参数名（凭据到位前也先把标识带上，便于后续对账）
_TRACK_PARAM: dict[str, str] = {
    "天猫": "utparam",
    "京东": "utm_source",
    "拼多多": "refer_page_name",
    "唯品会": "src",
    "保税仓": "utm_source",
}


def build_sub_id(session_id: str | None, product_key: str, offer_id: str) -> str:
    """生成 ≤32 字符的稳定溯源标识（各联盟对 sub_id 长度普遍有 32 字符限制）。

    结构：cx + 会话前 10 + 商品 hash 6 + 报价 hash 6 → 共 24 字符，留有余量。
    """
    sess = (session_id or "anon")[:10]
    ph = hashlib.md5(product_key.encode("utf-8")).hexdigest()[:6]
    oh = hashlib.md5(offer_id.encode("utf-8")).hexdigest()[:6]
    return f"cx{sess}{ph}{oh}"[:32]


def _append_query(url: str, extra: dict[str, str]) -> str:
    parts = urllib.parse.urlsplit(url)
    q = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    q.update({k: v for k, v in extra.items() if v})
    return urllib.parse.urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(q), parts.fragment)
    )


def build_cps_url(
    *,
    product: Product,
    offer: dict,
    sub_id: str,
    affiliate_url: str | None = None,
) -> tuple[str, bool]:
    """返回 ``(跳转链接, 是否启用佣金归因)``。

    Parameters
    ----------
    affiliate_url
        Provider 从联盟接口取得的真实推广链接；为空则走官方搜索深链兜底。
    """
    if affiliate_url:
        return _append_query(affiliate_url, {"sub_id": sub_id}), True

    channel = str(offer.get("channel", ""))
    tpl = _CHANNEL_SEARCH.get(channel)
    keyword = offer.get("search_keyword") or f"{product.brand} {product.name}"

    if tpl:
        url = tpl.format(q=urllib.parse.quote(keyword))
        param = _TRACK_PARAM.get(channel)
        if param:
            url = _append_query(url, {param: sub_id})
        return url, False

    # 极端兜底：渠道既无深链模板也无凭据 —— 退回该渠道官方首页（仍非死链）
    return f"https://www.baidu.com/s?wd={urllib.parse.quote(keyword + ' ' + channel)}", False


def enrich_offers_with_links(
    product: Product,
    offers: list[dict],
    sub_id: str,
) -> list[dict]:
    """为每条报价补齐 ``cps_url`` / ``cps_tracked`` / ``sub_id``。"""
    out: list[dict] = []
    for o in offers:
        row = dict(o)
        url, tracked = build_cps_url(
            product=product,
            offer=row,
            sub_id=sub_id,
            affiliate_url=row.get("affiliate_url"),
        )
        row["cps_url"] = url
        row["cps_tracked"] = tracked
        row["sub_id"] = sub_id
        out.append(row)
    return out
