"""CPS 链接与推送通道测试。

这两块是「变现」与「承诺」的落点，最容易出现「界面说有、实际没有」的问题，
因此单独成文件覆盖：
  · CPS 链接在**任何**情况下都不能是空串或 '#'
  · sub_id 必须满足各联盟 32 字符上限
  · 推送凭据缺失必须回报 not_configured，绝不能声称已推送
"""
from __future__ import annotations

import pytest

from core.catalog import CATALOG
from providers.cps import build_cps_url, build_sub_id, enrich_offers_with_links


class TestSubId:
    def test_within_32_chars(self):
        for sid in (None, "s_short", "s_" + "a" * 40):
            assert len(build_sub_id(sid, "小棕瓶", "天猫-国行")) <= 32

    def test_stable_and_unique(self):
        a = build_sub_id("sess1", "小棕瓶", "天猫-国行")
        b = build_sub_id("sess1", "小棕瓶", "天猫-国行")
        c = build_sub_id("sess1", "小黑瓶", "天猫-国行")
        d = build_sub_id("sess2", "小棕瓶", "天猫-国行")
        assert a == b
        assert a != c and a != d

    def test_prefix(self):
        assert build_sub_id("sess1", "小棕瓶", "x").startswith("cx")


class TestCpsUrl:
    def _offer(self, channel: str, **kw):
        return {"channel": channel, "shop_name": f"{channel}店", **kw}

    def test_affiliate_url_wins_and_marks_tracked(self):
        url, tracked = build_cps_url(
            product=CATALOG["小棕瓶"],
            offer=self._offer("天猫"),
            sub_id="cxabc",
            affiliate_url="https://uland.taobao.com/coupon/edetail?e=xxx",
        )
        assert tracked is True
        assert "sub_id=cxabc" in url
        assert url.startswith("https://uland.taobao.com/")

    @pytest.mark.parametrize("channel", ["天猫", "京东", "拼多多", "唯品会", "保税仓"])
    def test_fallback_never_empty(self, channel):
        url, tracked = build_cps_url(
            product=CATALOG["小棕瓶"], offer=self._offer(channel), sub_id="cxabc"
        )
        assert tracked is False
        assert url and url != "#"
        assert url.startswith("https://")

    def test_unknown_channel_still_gets_link(self):
        url, tracked = build_cps_url(
            product=CATALOG["小棕瓶"], offer=self._offer("未知渠道"), sub_id="cxabc"
        )
        assert url and url != "#"
        assert tracked is False

    def test_search_keyword_override(self):
        url, _ = build_cps_url(
            product=CATALOG["小棕瓶"],
            offer=self._offer("京东", search_keyword="雅诗兰黛 小棕瓶 50ml"),
            sub_id="cxabc",
        )
        assert "%E9%9B%85%E8%AF%97%E5%85%B0%E9%BB%9B" in url or "keyword=" in url

    def test_existing_query_params_preserved(self):
        url, tracked = build_cps_url(
            product=CATALOG["小棕瓶"],
            offer=self._offer("天猫"),
            sub_id="cxabc",
            affiliate_url="https://x.com/p?a=1&b=2",
        )
        assert "a=1" in url and "b=2" in url and "sub_id=cxabc" in url
        assert tracked is True


class TestEnrich:
    def test_every_offer_gets_link_and_flags(self):
        offers = [{"id": "x", "channel": c, "shop_name": c} for c in
                  ("天猫", "京东", "拼多多", "唯品会", "保税仓")]
        out = enrich_offers_with_links(CATALOG["小棕瓶"], offers, "cxsub")
        assert len(out) == 5
        for o in out:
            assert o["cps_url"] and o["cps_url"] != "#"
            assert o["cps_tracked"] is False
            assert o["sub_id"] == "cxsub"

    def test_original_list_not_mutated(self):
        offers = [{"id": "x", "channel": "天猫", "shop_name": "A"}]
        enrich_offers_with_links(CATALOG["小棕瓶"], offers, "cxsub")
        assert "cps_url" not in offers[0]


class TestPushStatus:
    def test_not_configured_is_honest(self):
        from services.push import push_status

        st = push_status()
        assert st["ready"] is False
        assert st["state"] in ("disabled", "not_configured")
        assert "尚未接入" in st["user_message"]

    def test_template_data_field_mapping(self):
        from services.push import build_template_data

        data = build_template_data(
            product_label="雅诗兰黛 特润修护肌活精华露（小棕瓶）50ml",
            lowest=748.0, target=800.0, lowest_channel="拼多多·品牌店",
        )
        assert set(data) == {"thing1", "amount2", "amount3", "date4", "thing5"}
        # thing 类型微信限制 20 字符，必须已裁剪
        assert len(data["thing1"]["value"]) <= 20
        assert len(data["thing5"]["value"]) <= 20
        assert data["amount2"]["value"] == 748.0

    def test_send_when_disabled_returns_skipped_not_sent(self):
        from services.push import send_price_alert

        outcomes = send_price_alert(
            product_label="小棕瓶", lowest=700, target=800,
            lowest_channel="拼多多", mp_openid="oX", mini_openid="oY",
        )
        assert outcomes
        assert all(o.status == "skipped" for o in outcomes)
        assert all(o.detail == "not_configured" for o in outcomes)

    def test_payload_encoding_is_json_safe(self):
        from services.push import encode_payload

        assert encode_payload(None) is None
        raw = {"a": {"b": [1, 2]}, "nested": {"x": object()}}
        out = encode_payload(raw)
        assert isinstance(out, dict)
        assert out["a"] == {"b": [1, 2]}


class TestAlertEvaluation:
    def _sub(self, target_cents=80000, channel=None):
        from core.models import AlertSubscription

        return AlertSubscription(
            id="al_test", session_id="s_x", product_input="小棕瓶",
            product_key="小棕瓶", product_label="雅诗兰黛 小棕瓶 50ml",
            target_price_cents=target_cents, channel=channel, status="监测中",
        )

    def _offers(self):
        from core.domain import normalize_offers

        return normalize_offers([
            {"id": "a", "channel": "天猫", "shop_name": "天猫自营", "version": "国行",
             "list_price": 1080, "benefits": {"coupon": 180}, "risk_tags": []},
            {"id": "b", "channel": "拼多多", "shop_name": "拼多多品牌店", "version": "海外版",
             "list_price": 1080, "benefits": {"subsidy": 400}, "risk_tags": []},
        ])

    def _trend(self, prior_low: float):
        # 最后一点代表今日；此前 89 天最低由 prior_low 控制
        points = [{"date": f"2026-06-{i:02d}", "price": prior_low} for i in range(1, 90)]
        points.append({"date": "2026-08-26", "price": 700.0})
        return {"points": points}

    def test_hit_target_and_new_low(self):
        from services.alert import evaluate

        ev = evaluate(self._sub(), self._offers(), self._trend(900.0))
        joined = " ".join(ev.reasons)
        assert "跌破" in joined
        assert "新低" in joined

    def test_big_subsidy_detected(self):
        from services.alert import evaluate

        ev = evaluate(self._sub(target_cents=100), self._offers(), self._trend(900.0))
        assert any("大额" in r for r in ev.reasons)

    def test_no_false_alarm_when_price_is_above_history(self):
        """此前 90 天最低比现价低 → 不得报「创历史新低」。"""
        from services.alert import evaluate

        ev = evaluate(self._sub(target_cents=100), self._offers(), self._trend(600.0))
        assert not any("新低" in r for r in ev.reasons)

    def test_channel_scoping(self):
        from services.alert import evaluate

        # 只盯天猫时，拼多多的 ¥680 不应参与
        sub = self._sub(target_cents=70000, channel="天猫")
        ev = evaluate(sub, self._offers(), self._trend(900.0))
        assert ev.lowest_channel == "天猫"
        assert ev.lowest_cents == 90000

    def test_empty_scope(self):
        from services.alert import evaluate

        ev = evaluate(self._sub(channel="京东"), self._offers(), self._trend(900.0))
        assert ev.reasons == []
        assert ev.lowest_cents is None

    def test_prior_low_excludes_today(self):
        from services.alert import _prior_low_cents

        trend = {"points": [{"date": "2026-08-25", "price": 900},
                            {"date": "2026-08-26", "price": 700}]}
        assert _prior_low_cents(trend) == 90000

    def test_prior_low_needs_two_points(self):
        from services.alert import _prior_low_cents

        assert _prior_low_cents({"points": [{"date": "x", "price": 900}]}) is None
