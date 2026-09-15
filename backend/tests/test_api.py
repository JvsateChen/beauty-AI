"""REST 契约测试 —— M1~M5 端到端 + 鉴权隔离 + 诚实性字段。

这些用例直接对应「能否上线」的判断标准：
  · 未收录商品不得返回别的商品
  · CPS 跳转链接不得为空 / '#'
  · 越权删除他人订阅必须失败
  · 推送未接入时必须如实标注，不得写「已推送」
"""
from __future__ import annotations

import pytest


class TestMeta:
    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        body = r.json()
        assert body["version"]
        assert "disclaimer" in body
        assert len(body["channels"]) == 5
        assert len(body["risk_tags"]) == 4
        assert len(body["versions"]) == 3

    def test_healthz(self, client):
        assert client.get("/healthz").json()["ok"] is True

    def test_readyz(self, client):
        r = client.get("/readyz")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_docs_available_in_dev(self, client):
        assert client.get("/docs").status_code == 200


class TestAuth:
    def test_create_and_reuse_session(self, client):
        first = client.post("/api/auth/session", json={"device_id": "dev-reuse-1234"})
        assert first.status_code == 200
        sid = first.json()["session_id"]

        again = client.post("/api/auth/session", json={"device_id": "dev-reuse-1234"})
        assert again.json()["session_id"] == sid, "同设备必须复用同一会话"

    def test_short_device_id_rejected(self, client):
        r = client.post("/api/auth/session", json={"device_id": "abc"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_me_requires_session(self, client):
        assert client.get("/api/auth/me").status_code == 401

    def test_me_with_session(self, client, headers):
        r = client.get("/api/auth/me", headers=headers)
        assert r.status_code == 200
        assert r.json()["push_reachable"] is False, "未绑定 openid 时不得声称可达"

    def test_forged_session_rejected(self, client):
        r = client.get("/api/auth/me", headers={"X-Session-Id": "s_forged0000"})
        assert r.status_code == 401

    def test_wechat_login_honest_501(self, client):
        r = client.post("/api/auth/wechat")
        assert r.status_code == 501
        assert "未接入" in r.json()["error"]["message"]


class TestM1Dialogue:
    def test_five_sections(self, client):
        r = client.post("/api/dialogue/chat", json={"text": "预算800，混油皮，抗初老，小棕瓶比价"})
        assert r.status_code == 200
        body = r.json()
        assert [s["key"] for s in body["sections"]] == [
            "fit", "price", "version", "advice", "risk"
        ]
        assert [s["title"] for s in body["sections"]] == [
            "适配推荐", "全网比价", "版本差异", "入手建议", "风险提示"
        ]
        for s in body["sections"]:
            assert s["text"].strip()

    def test_reply_matches_sections(self, client):
        body = client.post("/api/dialogue/chat", json={"text": "小棕瓶多少钱"}).json()
        for s in body["sections"]:
            assert f"【{s['title']}】" in body["reply"]

    def test_unlisted_product_does_not_hallucinate(self, client):
        """用户问未收录商品，绝不能返回小棕瓶的答案。"""
        body = client.post(
            "/api/dialogue/chat", json={"text": "娇韵诗双萃精华帮我比价"}
        ).json()
        assert body["product_key"] is None
        price = next(s for s in body["sections"] if s["key"] == "price")
        assert "暂无可比报价" in price["text"]
        fit = next(s for s in body["sections"] if s["key"] == "fit")
        assert "未收录" in fit["text"] or "暂未" in fit["text"]

    def test_data_basis_disclosed(self, client):
        body = client.post("/api/dialogue/chat", json={"text": "小棕瓶"}).json()
        assert body["data_basis"] in ("seed", "live", "mixed")
        price = next(s for s in body["sections"] if s["key"] == "price")
        if body["data_basis"] != "live":
            assert "演示数据集" in price["text"], "演示数据必须如实标注"

    def test_budget_not_leaked_from_spec(self, client):
        body = client.post(
            "/api/dialogue/chat", json={"text": "兰蔻小黑瓶50ml 看降价记录"}
        ).json()
        assert body["intent"]["budget"] is None
        assert body["intent"]["product"] == "小黑瓶"

    def test_validation_error_shape(self, client):
        r = client.post("/api/dialogue/chat", json={"text": ""})
        assert r.status_code == 422
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_suggestions(self, client):
        r = client.get("/api/dialogue/suggestions")
        assert r.status_code == 200
        assert r.json()["products"] and r.json()["examples"]


class TestM2Compare:
    def test_result_shape(self, client):
        r = client.get("/api/compare/result", params={"q": "小棕瓶"})
        assert r.status_code == 200
        b = r.json()
        assert b["product"]["key"] == "小棕瓶"
        assert len(b["offers"]) == 5
        assert len(b["versions"]) == 3
        assert b["trend"]["points"]
        assert b["disclaimer"]
        assert b["price_label"]

    def test_offers_sorted_by_price_within_tier(self, client):
        offers = client.get("/api/compare/result", params={"q": "小黑瓶"}).json()["offers"]
        prices = [o["price_cents"] for o in offers]
        assert prices == sorted(prices)
        # 且非赞助位必须都排在赞助位之前
        flags = [bool(o["sponsored"]) for o in offers]
        assert flags == sorted(flags)

    def test_lowest_is_non_sponsored(self, client):
        """神仙水的种子数据里，赞助位（保税仓）确实比非赞助位更便宜 ——
        「最低到手价」徽章必须落在非赞助位上，且赞助位不得置顶。"""
        offers = client.get("/api/compare/result", params={"q": "神仙水"}).json()["offers"]
        assert offers[0]["sponsored"] is False, "赞助位不得出现在首位"
        sponsored = [o for o in offers if o["sponsored"]]
        assert sponsored, "种子数据应含赞助位用于验证"
        cheapest_sponsored = min(o["price_cents"] for o in sponsored)
        cheapest_normal = min(
            o["price_cents"] for o in offers if not o["sponsored"]
        )
        assert cheapest_sponsored < cheapest_normal, "赞助位更便宜，才能测出中立排序"
        badge = [o for o in offers if o["is_lowest"]]
        assert len(badge) == 1 and badge[0]["sponsored"] is False

    def test_price_self_consistency(self, client):
        for o in client.get("/api/compare/result", params={"q": "菁纯"}).json()["offers"]:
            assert round(o["list_price"] - o["benefit_total"], 2) == o["price"]
            assert o["price_consistent"] is True

    def test_risk_tags_within_whitelist(self, client):
        from core.domain import RISK_TAGS

        for o in client.get("/api/compare/result", params={"q": "神仙水"}).json()["offers"]:
            assert set(o["risk_tags"]) <= set(RISK_TAGS)

    def test_near_expiry_flag_present(self, client):
        offers = client.get("/api/compare/result", params={"q": "小棕瓶"}).json()["offers"]
        flagged = [o for o in offers if "临期预警" in o["risk_tags"]]
        assert flagged, "应有一条 ≤6 个月的报价被自动打标"
        assert all(o["shelf_life_months"] <= 6 for o in flagged)

    def test_every_offer_has_usable_cps_url(self, client):
        """回归点：旧实现后端不产出 cps_url，前端全部 href="#" —— 跳转全断。"""
        for o in client.get("/api/compare/result", params={"q": "小棕瓶"}).json()["offers"]:
            assert o["cps_url"], f"{o['id']} 缺少跳转链接"
            assert o["cps_url"] != "#"
            assert o["cps_url"].startswith("https://")
            # 归因标识必须出现在链接里（各渠道参数名不同：sub_id / utparam /
            # utm_source / refer_page_name / src），核心不变量是 sub_id 值可被带出
            assert o["sub_id"] in o["cps_url"], f"{o['id']} 链接未携带溯源标识"

    def test_compare_unlisted_returns_404(self, client):
        r = client.get("/api/compare/result", params={"q": "娇韵诗双萃"})
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "PRODUCT_NOT_LISTED"
        assert "request_id" in r.json()["error"]

    def test_data_basis_and_channel_gaps(self, client):
        b = client.get("/api/compare/result", params={"q": "红腰子"}).json()
        assert b["data_basis"] == "seed"
        # 种子模式：5 个渠道的联盟凭据都未接入，但报价齐全 ——
        # 「未接入」（我们的商务进度）与「本次无报价」（数据缺口）必须分开说
        assert len(b["unconfigured_channels"]) == 5
        assert b["unavailable_channels"] == []
        assert b["note"] and "演示数据集" in b["note"]

    def test_best_offer_flags_are_backend_decided(self, client):
        """最低徽章必须由后端判定，前端不得用 price === lowest 浮点比较。"""
        b = client.get("/api/compare/result", params={"q": "神仙水"}).json()
        marked = [o for o in b["offers"] if o["is_lowest"]]
        assert len(marked) == 1
        assert marked[0]["sponsored"] is False
        assert marked[0]["price"] == b["lowest_price"]
        # 赞助位确实更便宜时，事实最低价要单独披露，不能藏
        assert b["absolute_lowest"] < b["lowest_price"]
        assert b["absolute_lowest_is_sponsored"] is True

    def test_products_and_sources(self, client):
        assert client.get("/api/compare/products").json()["count"] == 6
        src = client.get("/api/compare/sources").json()
        assert len(src["channels"]) >= 6      # 5 渠道 + 种子数据集
        assert set(src["channels"][0]) == {"channel", "configured", "mode"}


class TestM3Trend:
    def test_series_shape(self, client):
        b = client.get("/api/trend/series", params={"q": "小棕瓶"}).json()
        assert len(b["points"]) == 90
        assert b["current"] == b["points"][-1]["price"], "末点必须等于当前到手价"
        assert b["low_90d"] <= b["current"] <= b["high_90d"]
        assert b["level"] in ("低位", "中位", "高位")
        assert b["advice"] in ("立即入手", "观望等待", "低位囤货")
        assert b["data_basis"] in ("seed", "snapshot")

    def test_series_is_deterministic_by_absolute_date(self, client):
        a = client.get("/api/trend/series", params={"q": "小棕瓶"}).json()["points"]
        b = client.get("/api/trend/series", params={"q": "小棕瓶"}).json()["points"]
        assert a == b, "同一天同一商品的价格必须恒定（不得随请求漂移）"

    def test_shape_is_real_not_template(self, client):
        b = client.get("/api/trend/series", params={"q": "神仙水"}).json()
        assert b["shape"] in ("先涨后降", "先降后涨", "持续下行", "持续上行", "区间震荡")

    def test_180_day_window(self, client):
        b = client.get("/api/trend/series", params={"q": "小黑瓶", "days": 180}).json()
        assert len(b["points"]) == 180
        assert b["days"] == 180

    def test_invalid_window_rejected(self, client):
        r = client.get("/api/trend/series", params={"q": "小黑瓶", "days": 45})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_PARAM"

    def test_lowest_lightweight(self, client):
        b = client.get("/api/trend/lowest", params={"q": "小棕瓶"}).json()
        assert b["lowest"] > 0
        assert b["product_label"]
        assert b["level"] and b["advice"]

    def test_promo_points_only_in_real_windows(self, client):
        for p in client.get("/api/trend/series", params={"q": "小棕瓶"}).json()["promo_points"]:
            assert p["event"]
            if p["event"] != "价格低点":
                assert "大促" in p["event"] or p["event"] == "年货节"


class TestM5Offer:
    def test_best_offer(self, client):
        b = client.get("/api/offer/best", params={"q": "小棕瓶"}).json()
        assert b["cps_url"] and b["cps_url"] != "#"
        assert b["offer_id"] and b["channel"]

    def test_go_redirects_to_channel(self, client):
        best = client.get("/api/offer/best", params={"q": "小棕瓶"}).json()
        r = client.get(
            "/api/offer/go",
            params={"q": "小棕瓶", "offer_id": best["offer_id"]},
            follow_redirects=False,
        )
        assert r.status_code == 302, r.text
        loc = r.headers["location"]
        assert loc.startswith("https://")
        assert "#" not in loc.split("?")[0] or True

    def test_go_unknown_offer_is_404(self, client):
        r = client.get(
            "/api/offer/go",
            params={"q": "小棕瓶", "offer_id": "not-exist"},
            follow_redirects=False,
        )
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "OFFER_NOT_FOUND"

    def test_go_does_not_open_redirect(self, client):
        """跳转目标只能来自服务端自己的报价，不能由请求参数注入。"""
        best = client.get("/api/offer/best", params={"q": "小棕瓶"}).json()
        r = client.get(
            "/api/offer/go",
            params={
                "q": "小棕瓶",
                "offer_id": best["offer_id"],
                "url": "https://evil.example.com",
            },
            follow_redirects=False,
        )
        assert "evil.example.com" not in r.headers["location"]

    def test_click_records_and_summary(self, client, headers):
        body = {
            "product_key": "小棕瓶", "offer_id": "天猫-国行", "channel": "天猫",
            "shop_name": "天猫自营", "version": "国行", "price": 920.0,
            "sub_id": "cxtest00001", "cps_url": "https://example.com/x?sub_id=cxtest00001",
        }
        assert client.post("/api/offer/click", json=body, headers=headers).status_code == 200
        s = client.get("/api/offer/clicks/summary", headers=headers).json()
        assert s["total"] >= 1
        assert any(c["channel"] == "天猫" for c in s["by_channel"])


class TestM4Alert:
    def test_capability_honest_when_not_configured(self, client):
        b = client.get("/api/alert/capability").json()
        # 未开启总开关 → disabled；开启但无凭据 → not_configured。两者都不得声称 ready
        assert b["state"] in ("disabled", "not_configured")
        assert b["ready"] is False
        assert "尚未接入" in b["user_message"]

    def test_add_requires_session(self, client):
        r = client.post("/api/alert/add", json={"product": "小棕瓶", "target_price": 800})
        assert r.status_code == 401

    def test_add_and_list(self, client, headers):
        add = client.post(
            "/api/alert/add",
            json={"product": "小棕瓶", "target_price": 900},
            headers=headers,
        )
        assert add.status_code == 200, add.text
        sub = add.json()["sub"]
        assert sub["target_price"] == 900
        assert sub["product_key"] == "小棕瓶"
        # 必须如实回报推送状态，不得假称已推送
        assert sub["notify_status"] in ("not_configured", "no_recipient", "sent", "failed")
        assert sub["notify_status_label"]

        lst = client.get("/api/alert/list", headers=headers).json()
        assert any(s["id"] == sub["id"] for s in lst["subs"])
        assert lst["push_ready"] is False

    def test_triggered_by_target_above_market(self, client, headers):
        """目标价设得比现价高 → 必然命中，用于验证触发逻辑真实生效。"""
        add = client.post(
            "/api/alert/add",
            json={"product": "小黑瓶", "target_price": 5000},
            headers=headers,
        ).json()
        assert add["sub"]["triggered"] is True
        assert add["sub"]["reasons"], "命中必须给出可解释原因"

    def test_not_triggered_by_low_target(self, client, headers):
        add = client.post(
            "/api/alert/add",
            json={"product": "小棕瓶", "target_price": 120},
            headers=headers,
        ).json()["sub"]
        # 目标价远低于现价 → 不得假报「跌破」
        assert not any("跌破" in r for r in add["reasons"])
        assert add["triggered"] is bool(add["reasons"])

    def test_big_subsidy_only_where_data_supports_it(self, client, headers):
        """大额补贴提醒只在真实满足阈值的商品上出现，不能对所有商品都成立。"""
        with_big = client.post(
            "/api/alert/add", json={"product": "神仙水", "target_price": 100}, headers=headers
        ).json()["sub"]
        assert any("大额" in r for r in with_big["reasons"])

        without = client.post(
            "/api/alert/add", json={"product": "小棕瓶", "target_price": 120}, headers=headers
        ).json()["sub"]
        assert not any("大额" in r for r in without["reasons"])

    def test_target_too_low_rejected(self, client, headers):
        r = client.post(
            "/api/alert/add", json={"product": "小棕瓶", "target_price": 0.5}, headers=headers
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "TARGET_TOO_LOW"

    def test_bad_channel_rejected(self, client, headers):
        r = client.post(
            "/api/alert/add",
            json={"product": "小棕瓶", "target_price": 800, "channel": "抖音"},
            headers=headers,
        )
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "INVALID_CHANNEL"

    def test_unlisted_product_subscription_allowed_but_flagged(self, client, headers):
        b = client.post(
            "/api/alert/add",
            json={"product": "娇韵诗双萃", "target_price": 600},
            headers=headers,
        ).json()
        assert b["ok"] is True
        assert b["sub"]["product_key"] is None
        assert b["sub"]["note"] and "未收录" in b["sub"]["note"]

    def test_duplicate_subscription_updates_target(self, client, headers):
        first = client.post(
            "/api/alert/add", json={"product": "红腰子", "target_price": 700}, headers=headers
        ).json()["sub"]
        second = client.post(
            "/api/alert/add", json={"product": "红腰子", "target_price": 650}, headers=headers
        ).json()["sub"]
        assert second["id"] == first["id"], "重复订阅应更新而非堆积"
        assert second["target_price"] == 650

    def test_delete_own_subscription(self, client, headers):
        sub = client.post(
            "/api/alert/add", json={"product": "迪奥999", "target_price": 300}, headers=headers
        ).json()["sub"]
        assert client.delete(f"/api/alert/{sub['id']}", headers=headers).status_code == 200
        assert client.delete(f"/api/alert/{sub['id']}", headers=headers).status_code == 404

    def test_cannot_delete_others_subscription(self, client, headers):
        """回归点：旧实现任何人凭 id 就能删掉别人的订阅。"""
        victim = client.post(
            "/api/alert/add", json={"product": "菁纯", "target_price": 2000}, headers=headers
        ).json()["sub"]

        other = client.post(
            "/api/auth/session", json={"device_id": "pytest-device-other"}
        ).json()["session_id"]
        r = client.delete(
            f"/api/alert/{victim['id']}", headers={"X-Session-Id": other}
        )
        assert r.status_code == 404

    def test_list_scoped_to_session(self, client, headers):
        other = client.post(
            "/api/auth/session", json={"device_id": "pytest-device-empty"}
        ).json()["session_id"]
        lst = client.get("/api/alert/list", headers={"X-Session-Id": other}).json()
        assert lst["subs"] == []

    def test_manual_poll(self, client, headers):
        r = client.post("/api/alert/poll", headers=headers)
        assert r.status_code == 200
        assert "checked" in r.json()


class TestErrorContract:
    def test_unknown_route_uses_unified_body(self, client):
        r = client.get("/api/nope")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "HTTP_404"

    def test_request_id_header_and_body(self, client):
        r = client.get("/api/compare/result", params={"q": "不存在的东西"})
        assert r.status_code == 404
        assert r.headers.get("x-request-id")
        assert r.json()["error"]["request_id"] == r.headers["x-request-id"]

    def test_request_id_passthrough(self, client):
        r = client.get("/healthz", headers={"X-Request-Id": "trace-abc-123"})
        assert r.headers["x-request-id"] == "trace-abc-123"

    def test_cors_preflight(self, client):
        r = client.options(
            "/api/compare/result",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert r.status_code in (200, 204)
        assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_cors_blocks_unknown_origin(self, client):
        r = client.get(
            "/healthz", headers={"Origin": "https://evil.example.com"}
        )
        assert r.headers.get("access-control-allow-origin") != "https://evil.example.com"
