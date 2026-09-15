"""内置种子数据集 Provider。

用途：商务资质（各联盟 CPS / 保税仓数据方）未到位时，让产品**功能完整可演示**，
且不伪造实时性 —— 每个报价都带 ``data_basis="seed"``，前端如实标注「演示数据集」。

数据纪律（与本项目合规口径一致）：
  · 一律不写 ``price``，到手价由「官方价 − 优惠拆解」推导，保证数学自洽
  · 临期预警靠 ``shelf_life_months`` 阈值自动打标，不手工写标签
  · 至少保留一条 ``shelf_life_months <= 6`` 的数据，使阈值分支被真实覆盖
  · 保留一条 ``sponsored=True`` 的数据，使「赞助位标注 + 不置顶」逻辑被真实覆盖
  · 版本只取 国行 / 保税免税 / 海外版；海外版才写 origin（产地细分）
"""
from __future__ import annotations

from core.catalog import Product
from providers.base import ProviderNotConfigured

CHANNEL = "种子数据集"

#: 渠道 -> (店铺名, 店铺类型)
_SHOPS: dict[str, tuple[str, str]] = {
    "天猫": ("天猫自营", "自营"),
    "京东": ("京东自营", "自营"),
    "拼多多": ("拼多多品牌店", "品牌旗舰店"),
    "唯品会": ("唯品会自营", "自营"),
    "保税仓": ("保税仓直发", "自营"),
}

_WARRANTY_CN = "支持国内专柜联保"
_WARRANTY_OTHER = "不支持国内专柜联保"


def _o(
    channel: str,
    version: str,
    *,
    list_price: float,
    coupon: float = 0,
    discount: float = 0,
    gift: float = 0,
    subsidy: float = 0,
    origin: str | None = None,
    months: int = 30,
    extra_risk: tuple[str, ...] = (),
    note: str | None = None,
    sponsored: bool = False,
) -> dict:
    """构造一条报价。

    约定：国行 = 支持国内专柜联保；保税免税 / 海外版 = 不支持（并自动带该风险标签）。
    """
    shop, shop_type = _SHOPS[channel]
    risk: list[str] = list(extra_risk)
    if version != "国行" and "无专柜联保" not in risk:
        risk.append("无专柜联保")
    if version == "海外版" and "第三方店铺售后风险" not in risk and shop_type != "自营":
        risk.append("第三方店铺售后风险")

    return {
        "id": f"{channel}-{version}",
        "channel": channel,
        "shop_name": shop,
        "shop_type": shop_type,
        "version": version,
        "origin": origin,
        "list_price": list_price,
        "benefits": {
            "coupon": coupon,
            "platform_discount": discount,
            "gift_value": gift,
            "subsidy": subsidy,
        },
        "risk_tags": risk,
        "shelf_life_months": months,
        "warranty": _WARRANTY_CN if version == "国行" else _WARRANTY_OTHER,
        "note": note,
        "sponsored": sponsored,
        "data_basis": "seed",
    }


# ---------------------------------------------------------------------------
# 种子数据：6 款主数据商品 × 5 渠道
#
# 数值设计纪律（避免演示数据自相矛盾）：
#   1. 到手价一律不写，由优惠拆解推导（见 core.domain.normalize_offer）
#   2. 平台补贴占官方价普遍控制在 10%~14% —— 这是真实电商的常见量级；
#      若每条都 ≥15%，「大额补贴」提醒会对每款商品都成立，等于没有筛选能力。
#      因此只保留**一条**真实的大额补贴（神仙水·保税仓 26%），使该分支既有覆盖
#      又不至于泛滥。
#   3. 每款商品的到手价梯度模拟真实格局：拼多多(海外版) 最低 → 唯品会(保税免税)
#      → 天猫(国行) → 京东(国行) → 保税仓(保税免税)
#   4. 每款保留一条「捆绑消费溢价」与一条「临期」数据，覆盖四个风险标签
# ---------------------------------------------------------------------------
SEED_OFFERS: dict[str, list[dict]] = {
    # 雅诗兰黛 小棕瓶 · 官方价 1080
    #  天猫 ¥920(85.2%) 京东 ¥945(87.5%) 唯品会 ¥858(79.4%) 保税仓 ¥972(90.0%)
    #  拼多多 ¥825(76.4%) —— 最低，但临期 5 个月
    "小棕瓶": [
        _o("天猫", "国行", list_price=1080, coupon=30, discount=50, gift=80, months=30),
        _o("京东", "国行", list_price=1080, coupon=20, discount=40, gift=75, months=32),
        _o("唯品会", "保税免税", list_price=1080, coupon=22, discount=60, gift=140, months=26,
           extra_risk=("捆绑消费溢价",), note="套装捆绑销售，单件折算后含溢价"),
        _o("保税仓", "保税免税", list_price=1080, subsidy=108, months=28),
        _o("拼多多", "海外版", list_price=1080, coupon=40, discount=60, subsidy=155,
           origin="日版", months=5, note="剩余保质期约 5 个月，介意效期者慎选"),
    ],
    # 兰蔻 小黑瓶 · 官方价 980
    #  天猫 ¥800(81.6%) 京东 ¥825(84.2%) 唯品会 ¥787(80.3%) 保税仓 ¥882(90.0%)
    #  拼多多 ¥765(78.1%)
    "小黑瓶": [
        _o("天猫", "国行", list_price=980, coupon=25, discount=60, gift=95, months=30),
        _o("京东", "国行", list_price=980, coupon=20, discount=50, gift=85, months=31),
        _o("唯品会", "保税免税", list_price=980, coupon=18, discount=55, gift=120, months=25,
           extra_risk=("捆绑消费溢价",), note="与眼霜组成套装，折算后含溢价"),
        _o("保税仓", "保税免税", list_price=980, subsidy=98, months=27),
        _o("拼多多", "海外版", list_price=980, coupon=35, discount=50, subsidy=130,
           origin="韩免", months=18),
    ],
    # SK-II 神仙水 · 官方价 1540
    #  天猫 ¥1270(82.5%) 京东 ¥1300(84.4%) 唯品会 ¥1240(80.5%)
    #  保税仓 ¥1140(74.0%) —— 全场事实最低，但为**付费推广位**（sponsored）
    #  拼多多 ¥1210(78.6%) —— 非赞助位最低，因此「最低到手价」徽章归它
    "神仙水": [
        _o("天猫", "国行", list_price=1540, coupon=50, discount=100, gift=120, months=34),
        _o("京东", "国行", list_price=1540, coupon=40, discount=90, gift=110, months=33),
        _o("唯品会", "保税免税", list_price=1540, coupon=30, discount=110, gift=160, months=28,
           extra_risk=("捆绑消费溢价",), note="搭配清莹露套装，单件折算含溢价"),
        # 该条为付费推广位 + 唯一的大额补贴：同时验证「赞助位不置顶」与「大额补贴提醒」
        _o("保税仓", "保税免税", list_price=1540, subsidy=400, months=26, sponsored=True),
        _o("拼多多", "海外版", list_price=1540, coupon=60, discount=90, subsidy=180,
           origin="日版", months=20),
    ],
    # 兰蔻 菁纯面霜 · 官方价 2680
    #  天猫 ¥2340(87.3%) 京东 ¥2380(88.8%) 唯品会 ¥2270(84.7%) 保税仓 ¥2412(90.0%)
    #  拼多多 ¥2160(80.6%)
    "菁纯": [
        _o("天猫", "国行", list_price=2680, coupon=80, discount=200, gift=260, months=30),
        _o("京东", "国行", list_price=2680, coupon=60, discount=180, gift=240, months=32),
        _o("唯品会", "保税免税", list_price=2680, coupon=50, discount=220, gift=320, months=24,
           extra_risk=("捆绑消费溢价",), note="买正装赠同系列精华，折算后含溢价"),
        _o("保税仓", "保税免税", list_price=2680, subsidy=268, months=27),
        _o("拼多多", "海外版", list_price=2680, coupon=100, discount=180, subsidy=240,
           origin="欧版", months=22),
    ],
    # 资生堂 红腰子 · 官方价 1080
    #  天猫 ¥910(84.3%) 京东 ¥935(86.6%) 唯品会 ¥850(78.7%) 保税仓 ¥972(90.0%)
    #  拼多多 ¥820(75.9%)
    "红腰子": [
        _o("天猫", "国行", list_price=1080, coupon=40, discount=60, gift=90, months=29),
        _o("京东", "国行", list_price=1080, coupon=30, discount=55, gift=85, months=31),
        _o("唯品会", "保税免税", list_price=1080, coupon=25, discount=70, gift=150, months=23,
           extra_risk=("捆绑消费溢价",), note="套装含替换装，折算后含溢价"),
        _o("保税仓", "保税免税", list_price=1080, subsidy=108, months=26),
        _o("拼多多", "海外版", list_price=1080, coupon=45, discount=65, subsidy=150,
           origin="日版", months=16),
    ],
    # 迪奥 999 口红 · 官方价 370
    #  天猫 ¥305(82.4%) 京东 ¥315(85.1%) 唯品会 ¥293(79.2%) 保税仓 ¥333(90.0%)
    #  拼多多 ¥275(74.3%)
    "迪奥999": [
        _o("天猫", "国行", list_price=370, coupon=15, discount=20, gift=30, months=36),
        _o("京东", "国行", list_price=370, coupon=10, discount=20, gift=25, months=34),
        _o("唯品会", "保税免税", list_price=370, coupon=12, discount=25, gift=40, months=30),
        _o("保税仓", "保税免税", list_price=370, subsidy=37, months=28),
        _o("拼多多", "海外版", list_price=370, coupon=20, discount=25, subsidy=50,
           origin="韩免", months=15),
    ],
}


class SeedProvider:
    """内置种子数据集。始终可用（``is_configured() == True``），mode = seed。"""

    channel = CHANNEL
    mode = "seed"

    def is_configured(self) -> bool:
        return True

    def fetch(self, product: Product) -> list[dict]:
        rows = SEED_OFFERS.get(product.key)
        if rows is None:
            raise ProviderNotConfigured(f"种子数据集未收录「{product.key}」的报价")
        return [dict(r) for r in rows]
