"""商品主数据与 SKU 对齐。

替换旧实现的两个硬伤：
  1. `key in query or query in key` 子串匹配 —— 「小棕瓶精华」能命中，但「安瓶」这类
     子串会误命中，且品牌+商品的组合表达（「兰蔻那瓶精华」）全部失配。
  2. 匹配不上时静默回落「小棕瓶」—— 用户问神仙水却得到小棕瓶的答案，
     属于**捏造回答**。现在改为显式返回未收录，由 API 层如实告知。

匹配策略（按特异性打分，取最高分且过阈值）：
  · 文本归一化：全角→半角、大小写、去空白与常见分隔符、别名同义映射
  · 别名匹配：命中别名越长越具体 → 分越高
  · 规格抽取：单独抽出 50ml / 3.5g 等容量，容量不符时仍返回该商品但标注请求规格
  · 只在没有任何候选时返回未收录，绝不回落其它商品
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Product:
    key: str
    name: str
    brand: str
    brand_en: str
    spec: str
    category: str
    sku: str
    list_price: float
    aliases: tuple[str, ...] = field(default_factory=tuple)
    #: 该商品主打的肤质 / 诉求标签，供 M1 适配推荐做匹配打分
    suited_skin: tuple[str, ...] = ()
    suited_needs: tuple[str, ...] = ()

    def to_public(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "brand": self.brand,
            "brand_en": self.brand_en,
            "spec": self.spec,
            "category": self.category,
            "sku": self.sku,
            "list_price": self.list_price,
        }


#: 商品主数据（一期收录 6 款；扩充即在此追加，offers 种子数据同步补 5 渠道）
CATALOG: dict[str, Product] = {
    "小棕瓶": Product(
        key="小棕瓶",
        name="特润修护肌活精华露（小棕瓶）",
        brand="雅诗兰黛", brand_en="Estée Lauder",
        spec="50ml", category="精华", sku="ANR-50", list_price=1080.0,
        aliases=(
            "小棕瓶", "小棕瓶精华", "棕瓶", "特润修护", "特润修护肌活精华露",
            "advanced night repair", "anr", "雅诗兰黛精华", "雅诗兰黛小棕瓶",
            "estee lauder",
        ),
        suited_skin=("混油", "油皮", "干皮", "混干", "中性"),
        suited_needs=("抗初老", "抗老", "修护", "淡纹", "紧致"),
    ),
    "小黑瓶": Product(
        key="小黑瓶",
        name="精华肌底液（小黑瓶）",
        brand="兰蔻", brand_en="Lancôme",
        spec="50ml", category="精华", sku="GEN-50", list_price=980.0,
        aliases=(
            "小黑瓶", "小黑瓶精华", "肌底液", "精华肌底液",
            "genifique", "兰蔻精华", "兰蔻小黑瓶", "lancome",
        ),
        suited_skin=("混油", "油皮", "干皮", "混干", "中性", "敏感肌"),
        suited_needs=("修护", "保湿", "抗初老", "舒缓"),
    ),
    "神仙水": Product(
        key="神仙水",
        name="护肤精华露（神仙水）",
        brand="SK-II", brand_en="SK-II",
        spec="230ml", category="精华水", sku="FTE-230", list_price=1540.0,
        aliases=(
            "神仙水", "护肤精华露", "sk2", "sk-ii", "skii",
            "facial treatment essence", "sktwo",
        ),
        suited_skin=("混油", "油皮", "混干", "中性"),
        suited_needs=("保湿", "控油", "提亮", "美白"),
    ),
    "菁纯": Product(
        key="菁纯",
        name="菁纯臻颜面霜",
        brand="兰蔻", brand_en="Lancôme",
        spec="60ml", category="面霜", sku="ABS-60", list_price=2680.0,
        aliases=(
            "菁纯", "菁纯面霜", "菁纯臻颜", "菁纯臻颜面霜",
            "absolue", "兰蔻面霜", "lancome absolue",
        ),
        suited_skin=("干皮", "混干", "中性", "敏感肌"),
        suited_needs=("抗老", "紧致", "淡纹", "保湿"),
    ),
    "红腰子": Product(
        key="红腰子",
        name="红妍肌活精华露（红腰子）",
        brand="资生堂", brand_en="Shiseido",
        spec="50ml", category="精华", sku="ULT-50", list_price=1080.0,
        aliases=(
            "红腰子", "红妍肌活", "红妍肌活精华露", "ultimune",
            "资生堂精华", "资生堂红腰子", "shiseido",
        ),
        suited_skin=("敏感肌", "干皮", "混干", "混油", "中性", "痘肌"),
        suited_needs=("舒缓", "修护", "保湿", "抗初老"),
    ),
    "迪奥999": Product(
        key="迪奥999",
        name="烈艳蓝金唇膏 999",
        brand="迪奥", brand_en="Dior",
        spec="3.5g", category="口红", sku="DIO-999", list_price=370.0,
        aliases=(
            "999", "迪奥999", "烈艳蓝金", "蓝金唇膏", "dior 999",
            "迪奥口红", "dior",
        ),
        suited_skin=(),
        suited_needs=("彩妆", "显白", "口红"),
    ),
}

_VARIANT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ml|毫升|g|克|oz)", re.IGNORECASE)

# 归一化时的同义替换（在去空白之后应用）
_SYNONYMS: tuple[tuple[str, str], ...] = (
    ("skⅱ", "skii"), ("sk-ⅱ", "skii"), ("sk-ii", "skii"), ("sk2", "skii"),
    ("estéelauder", "esteelauder"), ("lancôme", "lancome"),
    ("小棕瓶", "小棕瓶"),
)


def normalize(text: str) -> str:
    """归一化：NFKC（全角→半角）+ 小写 + 去空白与常见分隔符。"""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text).lower()
    s = s.replace("‐", "-").replace("–", "-").replace("—", "-")
    s = re.sub(r"[\s\u3000·、,，。.!！?？:：;；'\"“”‘’()（）\[\]【】/\\|~*+]+", "", s)
    for a, b in _SYNONYMS:
        s = s.replace(a, b)
    return s


def extract_spec(text: str) -> str | None:
    """抽取用户提到的容量，如「50ml」「3.5 g」「230 毫升」。"""
    if not text:
        return None
    m = _VARIANT_RE.search(unicodedata.normalize("NFKC", text).lower())
    if not m:
        return None
    num, unit = m.group(1), m.group(2).lower()
    unit = {"毫升": "ml", "克": "g"}.get(unit, unit)
    return f"{num}{unit}"


@dataclass
class MatchResult:
    product: Product | None
    matched_alias: str | None
    score: int
    requested_spec: str | None
    #: None 表示匹配成功；否则是未收录的原因
    unmatched_reason: str | None
    #: 是否只是品牌级命中（用户没说具体商品）
    brand_only: bool = False

    @property
    def ok(self) -> bool:
        return self.product is not None


def match_product(text: str, *, min_score: int = 2) -> MatchResult:
    """把用户输入对齐到商品主数据。

    返回 MatchResult；未收录时 product=None 且带 unmatched_reason，
    **不会**回落到任何默认商品。
    """
    norm = normalize(text)
    spec = extract_spec(text)

    if not norm:
        return MatchResult(None, None, 0, spec, "输入为空")

    best: tuple[int, str, Product] | None = None
    for p in CATALOG.values():
        for alias in (p.key,) + p.aliases:
            na = normalize(alias)
            if len(na) < min_score:
                continue
            if na in norm:
                # 别名越长越具体；同时同名商品 key 命中略加权
                score = len(na) + (1 if alias == p.key else 0)
                if best is None or score > best[0]:
                    best = (score, alias, p)

    if best is not None:
        return MatchResult(best[2], best[1], best[0], spec, None)

    # 品牌级识别：用户只说了品牌，没说商品
    for p in CATALOG.values():
        for b in (p.brand, p.brand_en):
            nb = normalize(b)
            if len(nb) >= 2 and nb in norm:
                return MatchResult(
                    None, None, 0, spec,
                    f"只识别到品牌「{p.brand}」，请指明具体商品（如 {p.name}）。",
                    brand_only=True,
                )

    return MatchResult(None, None, 0, spec, "该商品暂未收录")


def suggest_products(limit: int = 6) -> list[dict]:
    return [p.to_public() for p in list(CATALOG.values())[:limit]]


def get_product(key: str) -> Product | None:
    return CATALOG.get(key)


def spec_matches(product: Product, requested_spec: str | None) -> bool:
    """请求规格是否与收录规格一致；未提规格一律视为一致。"""
    if not requested_spec:
        return True
    return normalize(requested_spec) == normalize(product.spec)
