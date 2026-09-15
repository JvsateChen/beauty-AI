"""core.domain 口径测试 —— 价格自洽、排序中立、档位与形态识别。"""
from __future__ import annotations

from datetime import date

from core.domain import (
    RISK_TAGS,
    absolute_lowest,
    cents_to_yuan,
    cheapest,
    classify_level,
    detect_low_windows,
    detect_trend_shape,
    lowest_price,
    normalize_offer,
    normalize_offers,
    promo_label,
    rank_offers,
    yuan_to_cents,
)


class TestMoney:
    def test_yuan_to_cents_rounding(self):
        assert yuan_to_cents(1080) == 108000
        assert yuan_to_cents(19.99) == 1999
        assert yuan_to_cents("12.5") == 1250
        assert yuan_to_cents(None) == 0
        assert yuan_to_cents("abc") == 0

    def test_cents_to_yuan_no_float_noise(self):
        # 0.1 + 0.2 类浮点误差不得外泄到 JSON
        assert cents_to_yuan(30) == 0.3
        assert cents_to_yuan(1) + cents_to_yuan(2) == 0.03
        assert isinstance(cents_to_yuan(1234), float)


class TestNormalizeOffer:
    def _raw(self, **kw):
        base = {
            "id": "x-1", "channel": "天猫", "shop_name": "天猫自营",
            "shop_type": "自营", "version": "国行", "list_price": 1080,
            "benefits": {"coupon": 30, "platform_discount": 50,
                         "gift_value": 80, "subsidy": 0},
            "risk_tags": [],
        }
        base.update(kw)
        return base

    def test_derive_price_is_self_consistent(self):
        o = normalize_offer(self._raw())
        # 1080 - (30+50+80) = 920
        assert o["price"] == 920.0
        assert o["benefit_total"] == 160.0
        assert o["price_cents"] == 92000
        assert o["price_consistent"] is True
        # 派生关系必须可复算
        assert o["list_price"] - o["benefit_total"] == o["price"]

    def test_drop_pct(self):
        o = normalize_offer(self._raw())
        assert o["drop_pct"] == round((1 - 920 / 1080) * 100, 1)

    def test_strict_derive_ignores_given_price(self):
        """种子模式：以优惠拆解为准，手填 price 不会破坏自洽。"""
        o = normalize_offer(self._raw(price=999), strict_derive=True)
        assert o["price"] == 920.0
        assert o["price_consistent"] is True

    def test_live_mode_flags_inconsistency(self):
        """真实源模式：以平台到手价为准，但与拆解不符时如实标记。"""
        o = normalize_offer(self._raw(price=999), strict_derive=False)
        assert o["price"] == 999.0
        assert o["price_consistent"] is False

    def test_risk_tags_whitelist_filters_dirty_data(self):
        o = normalize_offer(self._raw(risk_tags=["临期预警", "假货", "内部渠道"]))
        assert o["risk_tags"] == ["临期预警"]
        assert all(t in RISK_TAGS for t in o["risk_tags"])

    def test_near_expiry_auto_tagged_at_threshold(self):
        """剩余 6 个月（=阈值）必须自动打标；7 个月不打标。"""
        assert "临期预警" in normalize_offer(self._raw(shelf_life_months=6))["risk_tags"]
        assert "临期预警" in normalize_offer(self._raw(shelf_life_months=5))["risk_tags"]
        assert "临期预警" not in normalize_offer(self._raw(shelf_life_months=7))["risk_tags"]

    def test_near_expiry_not_duplicated(self):
        o = normalize_offer(self._raw(shelf_life_months=3, risk_tags=["临期预警"]))
        assert o["risk_tags"].count("临期预警") == 1

    def test_negative_price_clamped_and_flagged(self):
        o = normalize_offer(self._raw(benefits={"coupon": 5000}))
        assert o["price_cents"] == 0
        assert o["price_consistent"] is False


class TestRanking:
    def _set(self):
        return normalize_offers([
            {"id": "a", "channel": "天猫", "shop_name": "A", "version": "国行",
             "list_price": 1000, "benefits": {"coupon": 100}, "sponsored": False},
            {"id": "b", "channel": "拼多多", "shop_name": "B", "version": "海外版",
             "list_price": 1000, "benefits": {"coupon": 300}, "sponsored": False},
            # 赞助位：价格居中且佣金高 —— 必须不参与默认排序
            {"id": "c", "channel": "保税仓", "shop_name": "C", "version": "保税免税",
             "list_price": 1000, "benefits": {"subsidy": 200}, "sponsored": True},
        ])

    def test_sponsor_never_affects_order(self):
        ranked = rank_offers(self._set())
        # 非赞助位按到手价升序在前，赞助位整体殿后
        assert [o["id"] for o in ranked] == ["b", "a", "c"]

    def test_sponsor_never_takes_top_slot_even_if_cheapest(self):
        """「付费买名次」必须在算法层被关闭 —— 赞助位再便宜也不置顶。"""
        offers = normalize_offers([
            {"id": "normal", "channel": "天猫", "shop_name": "N", "version": "国行",
             "list_price": 1000, "benefits": {"coupon": 100}, "sponsored": False},
            {"id": "paid", "channel": "保税仓", "shop_name": "P", "version": "保税免税",
             "list_price": 1000, "benefits": {"subsidy": 500}, "sponsored": True},
        ])
        ranked = rank_offers(offers)
        assert ranked[0]["id"] == "normal"
        assert ranked[0]["price_cents"] > ranked[1]["price_cents"], (
            "赞助位确实更便宜，但它不得占据首位"
        )

    def test_cheapest_excludes_sponsored(self):
        ranked = rank_offers(self._set())
        # 全场最低是 b（¥700）；即便赞助位更便宜，也不给「最低」名分
        assert cheapest(ranked)["id"] == "b"

    def test_absolute_lowest_reveals_fact(self):
        """事实最低价要能单独披露，不能因为对方是赞助位就瞒着。"""
        offers = normalize_offers([
            {"id": "normal", "channel": "天猫", "shop_name": "N", "version": "国行",
             "list_price": 1000, "benefits": {"coupon": 100}, "sponsored": False},
            {"id": "paid", "channel": "保税仓", "shop_name": "P", "version": "保税免税",
             "list_price": 1000, "benefits": {"subsidy": 500}, "sponsored": True},
        ])
        assert cheapest(offers)["id"] == "normal"
        assert absolute_lowest(offers)["id"] == "paid"
        assert lowest_price(offers) == 500.0

    def test_cheapest_falls_back_when_all_sponsored(self):
        only = normalize_offers([
            {"id": "s", "channel": "天猫", "shop_name": "S", "version": "国行",
             "list_price": 1000, "benefits": {"coupon": 10}, "sponsored": True},
        ])
        assert cheapest(only)["id"] == "s"

    def test_lowest_price_reports_fact_including_sponsor(self):
        # 价格是客观事实，不因赞助而隐瞒
        assert lowest_price(self._set()) == 700.0

    def test_tie_puts_sponsor_last(self):
        offers = normalize_offers([
            {"id": "p", "channel": "天猫", "shop_name": "P", "version": "国行",
             "list_price": 1000, "benefits": {"coupon": 100}, "sponsored": True},
            {"id": "q", "channel": "京东", "shop_name": "Q", "version": "国行",
             "list_price": 1000, "benefits": {"coupon": 100}, "sponsored": False},
        ])
        assert [o["id"] for o in rank_offers(offers)] == ["q", "p"]

    def test_empty(self):
        assert rank_offers([]) == []
        assert cheapest([]) is None
        assert absolute_lowest([]) is None
        assert lowest_price([]) == 0.0


class TestClassifyLevel:
    def test_low(self):
        level, advice, _ = classify_level(100, 100, 200, 150)
        assert (level, advice) == ("低位", "低位囤货")

    def test_high(self):
        level, advice, _ = classify_level(200, 100, 200, 150)
        assert (level, advice) == ("高位", "观望等待")

    def test_mid_below_avg(self):
        level, advice, _ = classify_level(140, 100, 200, 150)
        assert (level, advice) == ("中位", "立即入手")

    def test_mid_above_avg(self):
        level, advice, _ = classify_level(180, 100, 200, 150)
        assert (level, advice) == ("中位", "观望等待")

    def test_no_history_is_mid(self):
        level, _, _ = classify_level(100, 0, 0, 0)
        assert level == "中位"


class TestTrendShape:
    def test_rise_then_fall_detected(self):
        # 前段走高、后段回落
        prices = [100, 110, 120, 130, 125, 118, 112, 108, 105, 103, 101, 100]
        info = detect_trend_shape(prices)
        assert info["rise_then_fall"] is True
        assert info["shape"] == "先涨后降"
        assert info["peak"]["index"] == 3
        assert info["fall_pct_from_peak"] > 0

    def test_monotonic_uptrend_classified_as_up(self):
        """回归点：单调上行曾被误判成「先降后涨」（因为最低点必在起点）。"""
        prices = [100 + i * 2 for i in range(12)]
        info = detect_trend_shape(prices)
        assert info["shape"] == "持续上行"
        assert info["rise_then_fall"] is False

    def test_monotonic_downtrend_classified_as_down(self):
        prices = [200 - i * 3 for i in range(12)]
        info = detect_trend_shape(prices)
        assert info["shape"] == "持续下行"
        assert info["rise_then_fall"] is False

    def test_fall_then_rise_detected(self):
        prices = [130, 125, 120, 110, 105, 100, 106, 112, 118, 122, 126, 128]
        info = detect_trend_shape(prices)
        assert info["shape"] == "先降后涨"

    def test_flat_series_is_range_bound(self):
        prices = [100, 100.5, 99.5, 100.2, 99.8, 100.1, 99.9, 100.3, 99.7, 100, 100.2, 99.8]
        assert detect_trend_shape(prices)["shape"] == "区间震荡"

    def test_real_low_requires_confirmation(self):
        # 低点在末尾 —— 无法确认，不能称作「真实低点」
        prices = [130, 125, 120, 115, 110, 108, 106, 104, 102, 100, 98, 95]
        info = detect_trend_shape(prices)
        assert info["real_low_confirmed"] is False

        # 低点在中间且已反弹 ≥1% —— 可确认
        confirmed = [130, 125, 120, 110, 105, 100, 106, 112, 118, 122, 126, 128]
        info2 = detect_trend_shape(confirmed)
        assert info2["real_low_confirmed"] is True

    def test_empty_series(self):
        info = detect_trend_shape([])
        assert info["shape"] == "无数据"
        assert info["real_low_confirmed"] is False


class TestPromoCalendar:
    def test_real_windows_only(self):
        assert promo_label(date(2026, 6, 1)) == "618 大促期"
        assert promo_label(date(2026, 11, 1)) == "双 11 大促期"
        assert promo_label(date(2026, 12, 12)) == "双 12 大促期"

    def test_regular_day_has_no_label(self):
        assert promo_label(date(2026, 8, 26)) is None
        assert promo_label(date(2026, 9, 15)) is None


class TestLowWindows:
    def test_low_window_detected_on_real_dip(self):
        points = [{"date": f"2026-06-{i:02d}", "price": p} for i, p in
                  enumerate([200, 200, 200, 300, 200, 200, 200], start=1)]
        # 中间点 300 是局部高点，不应入选；构造一个真实下探序列
        points = [{"date": f"2026-06-{i:02d}", "price": p} for i, p in
                  enumerate([200, 210, 220, 180, 230, 240, 250], start=1)]
        windows = detect_low_windows(points, window=2, drop=0.97)
        assert windows, "应识别出 6-04 的低点窗口"
        assert any(w["date"] == "2026-06-04" for w in windows)

    def test_no_label_when_not_in_promo_window(self):
        points = [{"date": f"2026-08-{i:02d}", "price": p} for i, p in
                  enumerate([200, 210, 220, 180, 230, 240, 250], start=1)]
        windows = detect_low_windows(points, window=2, drop=0.97)
        assert all(w["event"] == "价格低点" for w in windows)

    def test_label_used_inside_real_promo_window(self):
        points = [{"date": f"2026-11-{i:02d}", "price": p} for i, p in
                  enumerate([500, 510, 520, 400, 530, 540, 550], start=8)]
        windows = detect_low_windows(points, window=2, drop=0.97)
        assert windows and windows[0]["event"] == "双 11 大促期"
