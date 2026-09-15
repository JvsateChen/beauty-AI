"""M1 意图解析测试 —— 重点是「预算不得误取规格」这一回归点。"""
from __future__ import annotations

from services.dialogue import parse_intent, recommend


class TestBudget:
    def test_explicit_budget_with_currency(self):
        assert parse_intent("预算800").budget == 800
        assert parse_intent("预算 800 元以内").budget == 800
        assert parse_intent("800块左右").budget == 800

    def test_budget_not_taken_from_capacity(self):
        """回归点：旧实现把「50ml」的 50 读成预算 50。"""
        i = parse_intent("兰蔻小黑瓶50ml，看近3个月降价记录")
        assert i.budget is None
        assert i.product_key == "小黑瓶"

    def test_budget_not_taken_from_weight(self):
        i = parse_intent("迪奥999 3.5g 多少钱")
        assert i.budget is None

    def test_budget_with_capacity_still_parsed(self):
        i = parse_intent("预算1000，小棕瓶50ml")
        assert i.budget == 1000
        assert i.product_key == "小棕瓶"

    def test_k_and_wan_units(self):
        assert parse_intent("预算2k").budget == 2000
        assert parse_intent("预算1千").budget == 1000
        assert parse_intent("预算1万").budget == 10000

    def test_out_of_range_ignored(self):
        # 5 元不是合理预算（低于下限）→ 不当作预算
        assert parse_intent("预算5").budget is None
        assert parse_intent("预算999999").budget is None


class TestOtherFields:
    def test_skin_and_needs(self):
        i = parse_intent("我是混油皮，想抗初老和淡纹")
        assert i.skin_type == "混油"
        assert set(i.needs) >= {"抗初老", "淡纹"}

    def test_channels_dedup_and_std(self):
        i = parse_intent("对比天猫和保税仓价格")
        assert i.channels_pref == ["天猫", "保税仓"]
        i2 = parse_intent("保税和保税仓")
        assert i2.channels_pref == ["保税仓"]

    def test_flags(self):
        assert parse_intent("国行和免税版有什么区别").asks_version is True
        assert parse_intent("哪家最便宜").asks_price is True
        assert parse_intent("你好").asks_price is False

    def test_unmatched_reason_exposed(self):
        i = parse_intent("娇韵诗双萃怎么样")
        assert i.product_key is None
        assert i.unmatched_reason

    def test_public_shape(self):
        pub = parse_intent("预算800 混油皮").to_public()
        assert set(pub) >= {
            "budget", "skin_type", "needs", "product", "channels_pref",
            "asks_version", "asks_price", "unmatched_reason",
        }


class TestRecommend:
    def test_skin_need_scoring(self):
        recs = recommend(parse_intent("敏感肌，想舒缓修护"))
        assert recs, "应给出候选"
        assert recs[0]["key"] in ("红腰子", "小黑瓶")

    def test_budget_filtering(self):
        recs = recommend(parse_intent("预算500，随便推荐"))
        assert recs
        assert all(r["list_price"] <= 500 * 1.3 for r in recs)

    def test_lipstick_need(self):
        recs = recommend(parse_intent("想要彩妆口红"))
        assert any(r["key"] == "迪奥999" for r in recs)

    def test_empty_conditions_gives_baseline(self):
        recs = recommend(parse_intent("推荐一款大牌"))
        assert recs, "无条件时也应给出基线候选"
