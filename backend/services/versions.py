"""版本差异对比服务（M2 版本维度 + M1 场景 3）。

口径：3 类主版本 国行 / 保税免税 / 海外版；日版、韩免、欧版为「海外版」下的产地细分。
只做**版本差异科普**，不判定真伪、不承诺正品。
"""
from __future__ import annotations

from core.catalog import Product
from core.domain import VERSION_ORDER, cents_to_yuan

_BASE_TEMPLATE: list[dict] = [
    {
        "version": "国行",
        "ingredient_diff": "按中国化妆品备案标准生产，成分与国内专柜一致",
        "shelf_life": "标注生产日期与限期使用日期，符合国标",
        "warranty": "支持国内专柜联保，可凭购买凭证售后",
        "fit": "看重售后与质保、送礼、首次购买者",
        "risk_tags": [],
    },
    {
        "version": "保税免税",
        "ingredient_diff": "多为原产国版本，与国行配方基本一致，个别香精/防腐剂比例略有差异",
        "shelf_life": "按原产国标注，需自行换算；批次波动较大",
        "warranty": "不支持国内专柜联保，售后依托发货平台",
        "fit": "追求性价比、自用、对售后要求不高者",
        "risk_tags": ["无专柜联保"],
    },
    {
        "version": "海外版",
        "ingredient_diff": "日版 / 韩免 / 欧版配方可能存在香精、酒精、防腐体系差异",
        "shelf_life": "部分地区仅标注批号或生产日期，需自行解码核对",
        "warranty": "不支持国内专柜联保；第三方店铺退换货政策参差",
        "fit": "熟悉版本差异、追求低价、自用囤货者",
        "risk_tags": ["无专柜联保", "第三方店铺售后风险"],
    },
]


def get_version_compare(product: Product, offers: list[dict]) -> list[dict]:
    """返回 3 类版本的差异对比；价格差价用本次实际命中报价计算（分为单位比较）。"""
    lowest_by_version: dict[str, int] = {}
    origin_by_version: dict[str, list[str]] = {}
    for o in offers:
        v = o.get("version")
        if not v:
            continue
        cents = int(o.get("price_cents", 0))
        if v not in lowest_by_version or cents < lowest_by_version[v]:
            lowest_by_version[v] = cents
        origin = o.get("origin")
        if origin:
            origin_by_version.setdefault(v, [])
            if origin not in origin_by_version[v]:
                origin_by_version[v].append(origin)

    base_cents = min(lowest_by_version.values()) if lowest_by_version else 0

    out: list[dict] = []
    for item in _BASE_TEMPLATE:
        v = item["version"]
        row = dict(item)
        cents = lowest_by_version.get(v)
        row["lowest_price"] = cents_to_yuan(cents) if cents is not None else None
        row["price_gap"] = (
            cents_to_yuan(cents - base_cents) if cents is not None else None
        )
        if cents is None:
            row["price_gap_note"] = "本次无报价"
        elif cents == base_cents:
            row["price_gap_note"] = "本次最低"
        else:
            row["price_gap_note"] = f"较最低价高 ¥{cents_to_yuan(cents - base_cents):g}"
        row["available"] = cents is not None
        row["origins"] = origin_by_version.get(v, [])
        out.append(row)

    # 有报价的版本排前面，其次按固定顺序
    out.sort(key=lambda r: (not r["available"], VERSION_ORDER[r["version"]]))
    return out


def public_versions() -> list[str]:
    return list(VERSION_ORDER.keys())
