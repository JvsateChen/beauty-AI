#!/usr/bin/env python
"""M1~M5 端到端冒烟检查（可被 CI 直接调用，退出码即结论）。

与 pytest 的分工：
  · pytest      —— 用 TestClient 在进程内验证业务规则与契约字段
  · smoke.py    —— 走真实 HTTP 打一个**已启动**的服务，验证「部署起来能用」
                   （中间件、CORS、跳转、会话、静态配置全部是真链路）

用法：
    python scripts/smoke.py --base http://127.0.0.1:8000

退出码：
    0  全部通过
    1  有检查项失败（逐条打印失败原因）
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 20


class Checker:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.passed = 0
        self.failed: list[str] = []

    # ---------------------------------------------------------------- 工具
    def http(self, path: str, *, method: str = "GET", body: dict | None = None,
             headers: dict | None = None, follow: bool = True):
        url = f"{self.base}{path}"
        data = json.dumps(body).encode() if body is not None else None
        h = {"Accept": "application/json", **(headers or {})}
        if data is not None:
            h["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=h, method=method)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **kw):   # noqa: D102
                return None

        opener = urllib.request.build_opener() if follow else \
            urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(req, timeout=TIMEOUT) as r:
                raw = r.read().decode("utf-8", "replace")
                try:
                    return r.status, json.loads(raw), dict(r.headers)
                except ValueError:
                    return r.status, raw, dict(r.headers)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            try:
                return e.code, json.loads(raw), dict(e.headers)
            except ValueError:
                return e.code, raw, dict(e.headers)

    def check(self, name: str, cond: bool, detail: str = "") -> bool:
        if cond:
            self.passed += 1
            print(f"  [PASS] {name}")
        else:
            self.failed.append(f"{name} —— {detail}")
            print(f"  [FAIL] {name} —— {detail}")
        return cond

    # ---------------------------------------------------------------- 用例
    def run(self, query: str) -> None:
        print(f"\n=== 采选美妆 AI 冒烟检查 @ {self.base} ===\n")

        print("[元信息]")
        st, body, hdrs = self.http("/healthz")
        self.check("GET /healthz 可用", st == 200 and body.get("ok") is True, f"HTTP {st}")
        self.check("响应带 X-Request-Id", bool(hdrs.get("x-request-id") or hdrs.get("X-Request-Id")),
                   "缺少追踪号响应头")

        st, root, _ = self.http("/")
        self.check("GET / 返回定位与合规声明", st == 200 and root.get("disclaimer"),
                   f"HTTP {st}")
        self.check("渠道枚举为 5 个", len(root.get("channels", [])) == 5,
                   str(root.get("channels")))
        self.check("风险标签为 4 个", len(root.get("risk_tags", [])) == 4,
                   str(root.get("risk_tags")))

        st, ready, _ = self.http("/readyz")
        self.check("GET /readyz 数据库与数据源就绪", st == 200 and ready.get("ok") is True,
                   f"HTTP {st} {json.dumps(ready, ensure_ascii=False)[:200]}")

        print("\n[鉴权与会话]")
        st, ses, _ = self.http("/api/auth/session", method="POST",
                               body={"device_id": "smoke-device-0001"})
        self.check("POST /api/auth/session 签发会话", st == 200 and ses.get("session_id"),
                   f"HTTP {st}")
        sid = ses.get("session_id", "")
        auth = {"X-Session-Id": sid}

        st2, ses2, _ = self.http("/api/auth/session", method="POST",
                                 body={"device_id": "smoke-device-0001"})
        self.check("同设备复用同一会话（幂等）", ses2.get("session_id") == sid,
                   f"{sid} != {ses2.get('session_id')}")

        st, me, _ = self.http("/api/auth/me", headers=auth)
        self.check("GET /api/auth/me 带会话可用", st == 200 and me.get("session_id") == sid,
                   f"HTTP {st}")

        st, forged, _ = self.http("/api/auth/me", headers={"X-Session-Id": "s_forged"})
        self.check("伪造会话被拒（401）", st == 401, f"HTTP {st}")

        print("\n[M1 对话选型]")
        st, chat, _ = self.http("/api/dialogue/chat", method="POST",
                                body={"text": "预算800，混油皮，抗初老，帮我比价"})
        keys = [s.get("key") for s in chat.get("sections", [])]
        self.check("POST /api/dialogue/chat 返回五段结构", st == 200 and keys == [
            "fit", "price", "version", "advice", "risk"], f"HTTP {st} keys={keys}")
        self.check("回复文本包含五段标题",
                   all(f"【{s['title']}】" in chat.get("reply", "") for s in chat.get("sections", [])),
                   "reply 与 sections 不一致")
        self.check("预算未被误取为规格容量", chat.get("intent", {}).get("budget") == 800,
                   f"budget={chat.get('intent', {}).get('budget')}")

        st, off, _ = self.http("/api/dialogue/chat", method="POST",
                               body={"text": "娇韵诗双萃精华帮我比价"})
        self.check("未收录商品不回落（product_key 为空）", off.get("product_key") is None,
                   f"product_key={off.get('product_key')}")

        print("\n[M2 比价看板]")
        q = urllib.parse.quote(query)
        st, cmp_body, _ = self.http(f"/api/compare/result?q={q}")
        offers = cmp_body.get("offers", [])
        self.check("GET /api/compare/result 可用", st == 200 and offers, f"HTTP {st}")
        self.check("返回 5 条渠道报价", len(offers) == 5, f"len={len(offers)}")
        self.check("返回 3 个版本对比", len(cmp_body.get("versions", [])) == 3,
                   f"len={len(cmp_body.get('versions', []))}")
        self.check("数据来源已标注", cmp_body.get("data_basis") in ("live", "seed", "mixed"),
                   str(cmp_body.get("data_basis")))

        self.check("价格与优惠拆解自洽",
                   all(round(o["list_price"] - o["benefit_total"], 2) == o["price"]
                       for o in offers),
                   "存在 list_price - benefit_total != price 的报价")

        bad_link = [o["id"] for o in offers if not o.get("cps_url") or o["cps_url"] == "#"]
        self.check("每条报价都有可用跳转链接（M5 核心）", not bad_link, f"空链接：{bad_link}")

        badges = [o for o in offers if o.get("is_lowest")]
        self.check("最低到手价徽章唯一且非赞助位",
                   len(badges) == 1 and badges[0].get("sponsored") is False,
                   f"badges={[(b['id'], b['sponsored']) for b in badges]}")

        flags = [bool(o.get("sponsored")) for o in offers]
        self.check("赞助位不参与默认排序（不置顶）", flags == sorted(flags), str(flags))

        st, nf, _ = self.http("/api/compare/result?q=" + urllib.parse.quote("娇韵诗双萃"))
        self.check("未收录商品返回 404 + 明确错误码",
                   st == 404 and nf.get("error", {}).get("code") == "PRODUCT_NOT_LISTED",
                   f"HTTP {st}")

        st, src, _ = self.http("/api/compare/sources")
        self.check("GET /api/compare/sources 披露数据源现状",
                   st == 200 and len(src.get("channels", [])) >= 6, f"HTTP {st}")

        print("\n[M3 价格行情]")
        st, tr, _ = self.http(f"/api/trend/series?q={q}")
        pts = tr.get("points", [])
        self.check("GET /api/trend/series 返回 90 天序列", st == 200 and len(pts) == 90,
                   f"HTTP {st} points={len(pts)}")
        self.check("末点等于当前到手价",
                   bool(pts) and abs(pts[-1]["price"] - tr.get("current", -1)) < 0.011,
                   f"last={pts[-1]['price'] if pts else None} current={tr.get('current')}")
        self.check("档位与建议均已判定",
                   tr.get("level") in ("低位", "中位", "高位")
                   and tr.get("advice") in ("立即入手", "观望等待", "低位囤货"),
                   f"level={tr.get('level')} advice={tr.get('advice')}")
        self.check("走势形态为真实识别结果",
                   tr.get("shape") in ("先涨后降", "先降后涨", "持续下行", "持续上行", "区间震荡"),
                   str(tr.get("shape")))

        st, tr2, _ = self.http(f"/api/trend/series?q={q}")
        self.check("同一天同商品价格恒定（不随请求漂移）",
                   tr2.get("points") == pts, "两次请求结果不一致")

        st, bad, _ = self.http(f"/api/trend/series?q={q}&days=45")
        self.check("非法窗口被拒（400）", st == 400, f"HTTP {st}")

        print("\n[M4 降价订阅]")
        st, cap, _ = self.http("/api/alert/capability")
        self.check("GET /api/alert/capability 如实披露推送能力",
                   st == 200 and cap.get("state") in ("ready", "not_configured", "disabled"),
                   f"HTTP {st}")
        if not cap.get("ready"):
            self.check("未接入推送时明确告知用户",
                       "尚未接入" in (cap.get("user_message") or ""),
                       cap.get("user_message"))

        st, add, _ = self.http("/api/alert/add", method="POST", headers=auth,
                               body={"product": query, "target_price": 100})
        sub = add.get("sub", {})
        self.check("POST /api/alert/add 创建订阅", st == 200 and sub.get("id"), f"HTTP {st}")
        self.check("订阅带推送状态（不假称已推送）",
                   sub.get("notify_status") in ("not_configured", "no_recipient", "sent", "failed")
                   and sub.get("notify_status_label"),
                   str(sub.get("notify_status")))
        self.check("触发判定与原因一致",
                   sub.get("triggered") == bool(sub.get("reasons")),
                   f"triggered={sub.get('triggered')} reasons={sub.get('reasons')}")

        st, lst, _ = self.http("/api/alert/list", headers=auth)
        self.check("GET /api/alert/list 返回本人订阅", st == 200 and lst.get("subs"),
                   f"HTTP {st}")

        st, _, _ = self.http("/api/alert/list", headers={"X-Session-Id": "s_forged"})
        self.check("无有效会话不能读订阅（401）", st == 401, f"HTTP {st}")

        # 越权：另一个会话删不掉这个订阅
        st, other, _ = self.http("/api/auth/session", method="POST",
                                 body={"device_id": "smoke-device-other"})
        st, dele, _ = self.http(f"/api/alert/{sub.get('id')}", method="DELETE",
                                headers={"X-Session-Id": other.get("session_id", "")})
        self.check("越权删除他人订阅被拒（404）", st == 404, f"HTTP {st}")

        st, dele, _ = self.http(f"/api/alert/{sub.get('id')}", method="DELETE", headers=auth)
        self.check("本人可删除订阅", st == 200, f"HTTP {st}")

        print("\n[M5 跳转与溯源]")
        st, best, _ = self.http(f"/api/offer/best?q={q}")
        self.check("GET /api/offer/best 返回最低价跳转信息",
                   st == 200 and best.get("cps_url") and best["cps_url"] != "#", f"HTTP {st}")

        st, _, hdrs = self.http(
            f"/api/offer/go?q={q}&offer_id={urllib.parse.quote(best.get('offer_id', ''))}",
            follow=False)
        loc = hdrs.get("Location", hdrs.get("location", ""))
        self.check("GET /api/offer/go 302 跳转到真实渠道",
                   st in (301, 302, 303, 307, 308) and loc.startswith("https://"),
                   f"HTTP {st} loc={loc[:80]}")

        st, _, hdrs2 = self.http(
            f"/api/offer/go?q={q}&offer_id=nope&url=https://evil.example.com", follow=False)
        loc2 = hdrs2.get("Location", hdrs2.get("location", ""))
        self.check("跳转不接受外部 URL（无开放重定向）",
                   "evil.example.com" not in loc2, f"loc={loc2[:120]}")

        st, clk, _ = self.http("/api/offer/click", method="POST", headers=auth,
                              body={"product_key": None, "offer_id": best.get("offer_id"),
                                    "channel": best.get("channel"), "price": best.get("price"),
                                    "sub_id": best.get("sub_id")})
        self.check("POST /api/offer/click 记录点击", st == 200 and clk.get("ok") is True,
                   f"HTTP {st}")

        st, summ, _ = self.http("/api/offer/clicks/summary", headers=auth)
        self.check("GET /api/offer/clicks/summary 可对账",
                   st == 200 and summ.get("total", 0) >= 1, f"HTTP {st} {summ}")

        print("\n[统一错误体与 CORS]")
        st, err, hdrs = self.http("/api/nope")
        self.check("未知路由使用统一错误体",
                   st == 404 and err.get("error", {}).get("code") == "HTTP_404", f"HTTP {st}")
        self.check("错误体带 request_id", bool(err.get("error", {}).get("request_id")),
                   json.dumps(err, ensure_ascii=False)[:120])

        # ---------------------------------------------------------------- 汇总
        total = self.passed + len(self.failed)
        print(f"\n=== 结果：{self.passed}/{total} 通过 ===")
        if self.failed:
            print("\n失败项：")
            for f in self.failed:
                print(f"  · {f}")
            sys.exit(1)
        print("全部通过。")


def main() -> None:
    ap = argparse.ArgumentParser(description="采选美妆 AI 端到端冒烟检查")
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="后端服务地址")
    ap.add_argument("--query", default="小棕瓶", help="用于检查的商品查询词")
    args = ap.parse_args()
    Checker(args.base).run(args.query)


if __name__ == "__main__":
    main()
