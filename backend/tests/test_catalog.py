"""商品主数据对齐测试 —— 重点是「绝不回落」与「别名/规格」处理。"""
from __future__ import annotations

from core.catalog import CATALOG, extract_spec, match_product, normalize, spec_matches


class TestNormalize:
    def test_fullwidth_and_case(self):
        assert normalize("ＳＫ－ＩＩ") == normalize("sk-ii")
        assert normalize("Estée Lauder") == normalize("estee lauder")

    def test_strips_separators(self):
        assert normalize("小棕瓶 · 50ml") == "小棕瓶50ml"


class TestSpecExtraction:
    def test_ml(self):
        assert extract_spec("小棕瓶 50ml") == "50ml"
        assert extract_spec("神仙水 230 毫升") == "230ml"

    def test_weight(self):
        assert extract_spec("迪奥999 3.5g") == "3.5g"
        assert extract_spec("口红 3.5 克") == "3.5g"

    def test_none(self):
        assert extract_spec("小棕瓶多少钱") is None


class TestMatching:
    def test_alias_hit(self):
        assert match_product("小棕瓶").product.key == "小棕瓶"
        assert match_product("兰蔻小黑瓶").product.key == "小黑瓶"
        assert match_product("sk2 神仙水").product.key == "神仙水"
        assert match_product("红腰子精华").product.key == "红腰子"
        assert match_product("迪奥999").product.key == "迪奥999"

    def test_english_alias(self):
        assert match_product("advanced night repair").product.key == "小棕瓶"
        assert match_product("Genifique").product.key == "小黑瓶"

    def test_longest_alias_wins(self):
        r = match_product("雅诗兰黛小棕瓶精华50ml")
        assert r.product.key == "小棕瓶"
        assert r.requested_spec == "50ml"

    def test_unlisted_never_falls_back(self):
        """旧实现会把未收录商品静默回落成小棕瓶 —— 这里必须为空。"""
        r = match_product("娇韵诗双萃精华")
        assert r.product is None
        assert r.ok is False
        assert r.unmatched_reason

    def test_brand_only_asks_for_product(self):
        r = match_product("雅诗兰黛有什么值得买")
        assert r.product is None
        assert r.brand_only is True
        assert "品牌" in (r.unmatched_reason or "")

    def test_empty_input(self):
        r = match_product("   ")
        assert r.ok is False
        assert r.unmatched_reason == "输入为空"

    def test_substring_false_positive_avoided(self):
        """「安瓶」曾因 `key in query` 的子串匹配误命中 —— 现不应命中任何商品。"""
        assert match_product("安瓶精华").product is None

    def test_noise_text_still_matches(self):
        assert match_product("帮我看看这个 小棕瓶 值不值得买").product.key == "小棕瓶"


class TestSpecMatch:
    def test_same_spec(self):
        assert spec_matches(CATALOG["小棕瓶"], "50ml") is True

    def test_different_spec_flagged(self):
        assert spec_matches(CATALOG["小棕瓶"], "100ml") is False

    def test_no_request_is_ok(self):
        assert spec_matches(CATALOG["小棕瓶"], None) is True


class TestCatalogIntegrity:
    def test_catalog_fields_complete(self):
        for key, p in CATALOG.items():
            assert p.key == key
            assert p.name and p.brand and p.spec and p.sku
            assert p.list_price > 0
            assert key in p.aliases, "别名里必须含 key 本身"

    def test_seed_covers_all_catalog_products(self):
        from providers.seed import SEED_OFFERS

        assert set(SEED_OFFERS) == set(CATALOG), "种子数据集与主数据必须一一对应"
        for key, rows in SEED_OFFERS.items():
            assert len(rows) == 5, f"{key} 应覆盖 5 个渠道"
            channels = {r["channel"] for r in rows}
            assert len(channels) == 5

    def test_seed_has_near_expiry_coverage(self):
        """至少一条 ≤6 个月，保证临期阈值分支被真实覆盖。"""
        from providers.seed import SEED_OFFERS

        months = [r["shelf_life_months"] for rows in SEED_OFFERS.values() for r in rows]
        assert any(m <= 6 for m in months)

    def test_seed_has_sponsored_coverage(self):
        from providers.seed import SEED_OFFERS

        flags = [r.get("sponsored", False) for rows in SEED_OFFERS.values() for r in rows]
        assert any(flags), "至少一条赞助位，用于验证「标注且不置顶」"

    def test_seed_never_hardcodes_price(self):
        """种子数据一律不写 price，到手价必须由优惠拆解推导出来。"""
        from providers.seed import SEED_OFFERS

        for rows in SEED_OFFERS.values():
            for r in rows:
                assert "price" not in r, f"{r['id']} 不应手填 price"
