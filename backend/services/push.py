"""M4 · 微信推送通道（公众号模板消息 + 小程序订阅消息）。

修复的问题：旧实现界面上写着「已通过公众号 + 小程序推送」，但**后端根本没有发送代码**，
属于对用户撒谎。本模块把推送真正实现出来，并且做到「没配就是没配」——

状态语义（前后端共用）：
  not_configured  凭据未接入（appid / secret / template_id 任一缺失，或 push_enabled=false）
  no_recipient    会话未绑定 openid（用户没授权接收，无从发送）
  sent            微信接口返回 errcode=0
  failed          微信接口返回非 0 errcode，或网络异常

实现要点：
  · access_token 进程内缓存 + 提前 5 分钟刷新（微信 token 有效期 7200s）
  · 40001 / 42001（token 失效）自动清缓存并**重试一次**
  · 45009（频率超限）、43101（用户拒收）等业务错误不重试，如实回报错误码
  · 发送结果一律落 push_log 表，可审计、可排查、可重放
  · 任何情况下本模块都**不会**声称「已推送」而实际没发
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

from core.config import settings

logger = logging.getLogger("caixuan.push")

_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
_MP_SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/template/send"
_MINI_SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/subscribe/send"

#: 需要清 token 重试的 errcode（凭据/token 失效类）
_RETRYABLE = {40001, 42001, 40014}

#: 常见错误码 -> 人话（便于运营排查，非穷举）
_ERROR_HINT = {
    40001: "access_token 无效（凭据错误或已被刷新）",
    40003: "openid 无效或用户未关注该公众号",
    40037: "template_id 无效（模板未申请或不属于该账号）",
    41002: "缺少 appid",
    41004: "缺少 APP secret",
    42001: "access_token 已过期",
    43004: "用户未关注该公众号，无法下发模板消息",
    43101: "用户拒绝接收该模板消息（需重新授权订阅）",
    45009: "接口调用频率超限，请降低推送频率",
    47003: "模板参数不合法（字段名或取值不符合模板要求）",
}


@dataclass
class PushOutcome:
    """一次推送的投递结果。"""

    channel: str                     # 公众号 / 小程序
    status: str                      # sent / failed / skipped
    detail: str                      # not_configured / no_recipient / sent / failed
    error_code: str | None = None
    error_message: str | None = None
    payload: dict | None = field(default=None)

    def as_log_fields(self) -> dict:
        return {
            "channel": self.channel,
            "status": "sent" if self.status == "sent" else ("skipped" if self.status == "skipped" else "failed"),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "payload": self.payload,
        }


# ---------------------------------------------------------------------------
# access_token 缓存
# ---------------------------------------------------------------------------

class _TokenCache:
    """进程内 access_token 缓存（线程安全）。

    多实例部署时应换成 Redis 或集中式缓存，避免各实例互相顶掉 token
    （微信同一 appid 的 token 是全局唯一，并发刷新会导致旧 token 失效）。
    一期单实例 + 单后台任务，进程内缓存足够；这里把限制写清楚。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tokens: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> str | None:
        with self._lock:
            hit = self._tokens.get(key)
        if not hit:
            return None
        token, expire_at = hit
        if expire_at <= time.time():
            with self._lock:
                self._tokens.pop(key, None)
            return None
        return token

    def set(self, key: str, token: str, expires_in: int) -> None:
        # 提前 300 秒过期，规避边界失效
        ttl = max(60, int(expires_in) - 300)
        with self._lock:
            self._tokens[key] = (token, time.time() + ttl)

    def drop(self, key: str) -> None:
        with self._lock:
            self._tokens.pop(key, None)


_tokens = _TokenCache()


def _fetch_access_token(app_id: str, app_secret: str) -> tuple[str | None, str | None]:
    """取 access_token。返回 (token, 错误说明)。"""
    try:
        with httpx.Client(timeout=settings.outbound_timeout_seconds) as c:
            r = c.get(_TOKEN_URL, params={
                "grant_type": "client_credential",
                "appid": app_id,
                "secret": app_secret,
            })
        data = r.json()
    except Exception as exc:                      # 网络层
        logger.warning("获取 access_token 失败：%s", exc)
        return None, "微信接口不可达"
    if data.get("access_token"):
        return str(data["access_token"]), None
    code = data.get("errcode")
    return None, f"获取 access_token 失败（errcode={code}：{_ERROR_HINT.get(code, '未收录错误码')}）"


def _access_token(app_id: str, app_secret: str) -> tuple[str | None, str | None]:
    cached = _tokens.get(app_id)
    if cached:
        return cached, None
    token, err = _fetch_access_token(app_id, app_secret)
    if token:
        # expires_in 未随错误返回，此处按微信默认 7200s 记
        _tokens.set(app_id, token, 7200)
    return token, err


# ---------------------------------------------------------------------------
# 模板数据
# ---------------------------------------------------------------------------

def build_template_data(
    *,
    product_label: str,
    lowest: float,
    target: float,
    lowest_channel: str,
    when: datetime | None = None,
) -> dict:
    """按配置的字段映射拼模板数据。

    微信对字段类型有硬约束：thing ≤ 20 字符、amount 为数字、date 为
    "YYYY-MM-DD HH:MM" 或 "YYYY年MM月DD日"。这里统一裁剪与格式化，
    避免因超长被 47003 拒掉。
    """
    f = settings.template_fields
    ts = (when or datetime.now(timezone.utc)).astimezone(
        timezone(timedelta(hours=8))
    ).strftime("%Y-%m-%d %H:%M")

    return {
        f["product"]: {"value": product_label[:20]},
        f["price"]: {"value": round(float(lowest), 2)},
        f["target"]: {"value": round(float(target), 2)},
        f["time"]: {"value": ts},
        f["channel"]: {"value": (lowest_channel or "全渠道最低")[:20]},
    }


# ---------------------------------------------------------------------------
# 发送
# ---------------------------------------------------------------------------

def _post_send(url: str, token: str, body: dict) -> tuple[dict | None, str | None]:
    try:
        with httpx.Client(timeout=settings.outbound_timeout_seconds) as c:
            r = c.post(url, params={"access_token": token}, json=body)
        return r.json(), None
    except Exception as exc:
        logger.warning("微信推送请求失败：%s", exc)
        return None, "微信接口不可达"


def _send_once(
    *,
    channel: str,
    app_id: str,
    app_secret: str,
    template_id: str,
    openid: str,
    data: dict,
    page: str | None = None,
    url: str | None = None,
) -> PushOutcome:
    token, err = _access_token(app_id, app_secret)
    if not token:
        return PushOutcome(channel, "failed", "failed",
                           error_code="TOKEN_ERROR", error_message=err)

    if channel == "小程序":
        endpoint = _MINI_SEND_URL
        body: dict = {
            "touser": openid,
            "template_id": template_id,
            "data": data,
        }
        if page:
            body["page"] = page
    else:
        endpoint = _MP_SEND_URL
        body = {
            "touser": openid,
            "template_id": template_id,
            "data": data,
        }
        if url:
            body["url"] = url

    resp, net_err = _post_send(endpoint, token, body)
    if resp is None:
        return PushOutcome(channel, "failed", "failed",
                           error_code="NETWORK", error_message=net_err, payload=body)

    errcode = int(resp.get("errcode", -1))
    if errcode == 0:
        return PushOutcome(channel, "sent", "sent", payload=body)

    # token 失效类：清缓存重试一次
    if errcode in _RETRYABLE:
        _tokens.drop(app_id)
        token, err = _access_token(app_id, app_secret)
        if token:
            body["access_token_retry"] = True
            resp2, _ = _post_send(endpoint, token, body)
            if resp2 is not None and int(resp2.get("errcode", -1)) == 0:
                return PushOutcome(channel, "sent", "sent", payload=body)
            if resp2 is not None:
                resp = resp2
                errcode = int(resp.get("errcode", -1))

    hint = _ERROR_HINT.get(errcode, str(resp.get("errmsg") or "未知错误"))
    return PushOutcome(
        channel, "failed", "failed",
        error_code=f"WX_{errcode}",
        error_message=f"[{errcode}] {hint}",
        payload=body,
    )


def push_status() -> dict:
    """推送能力现状，供 /api/alert 与 /api/health 如实告知前端。"""
    configured_channels = []
    if settings.wechat_ready:
        configured_channels.append("公众号")
    if settings.wechat_mini_ready:
        configured_channels.append("小程序")
    if not settings.push_enabled:
        state, note = "disabled", "推送总开关未开启（PUSH_ENABLED=false）"
    elif not configured_channels:
        state, note = "not_configured", (
            "推送凭据未接入：需配置 WECHAT_MP_APP_ID / SECRET / TEMPLATE_ID，"
            "或小程序 WECHAT_MINI_*，并置 PUSH_ENABLED=true"
        )
    else:
        state, note = "ready", f"已接入推送通道：{' + '.join(configured_channels)}"
    return {
        "state": state,
        "ready": settings.push_ready,
        "channels": configured_channels,
        "interval_minutes": settings.push_interval_minutes,
        "cooldown_hours": settings.push_cooldown_hours,
        "note": note,
        # 前端据此展示「订阅已记录，推送通道未接入」而不是「已推送」
        "user_message": (
            "价格监测已生效；降价命中后会通过公众号 / 小程序推送提醒。"
            if settings.push_ready
            else "价格监测已生效，命中条件后会在站内提示；"
                 "微信推送通道尚未接入，暂不会收到微信消息。"
        ),
    }


def send_price_alert(
    *,
    product_label: str,
    lowest: float,
    target: float,
    lowest_channel: str,
    mp_openid: str | None,
    mini_openid: str | None,
    jump_url: str | None = None,
) -> list[PushOutcome]:
    """向该会话可达的微信通道发送降价提醒。

    返回每个通道的结果；调用方（services.alert）据此写 push_log 与 notify_status。
    """
    if not settings.push_enabled:
        return [PushOutcome("公众号", "skipped", "not_configured",
                            error_message="PUSH_ENABLED=false"),
                PushOutcome("小程序", "skipped", "not_configured",
                            error_message="PUSH_ENABLED=false")]

    data = build_template_data(
        product_label=product_label, lowest=lowest,
        target=target, lowest_channel=lowest_channel,
    )
    outcomes: list[PushOutcome] = []

    # ---- 公众号 ----
    if not settings.wechat_ready:
        outcomes.append(PushOutcome("公众号", "skipped", "not_configured",
                                    error_message="公众号模板凭据未配置"))
    elif not mp_openid:
        outcomes.append(PushOutcome("公众号", "skipped", "no_recipient",
                                    error_message="该会话未绑定公众号 openid（用户未授权）"))
    else:
        outcomes.append(_send_once(
            channel="公众号",
            app_id=settings.wechat_mp_app_id,
            app_secret=settings.wechat_mp_app_secret,
            template_id=settings.wechat_mp_template_id,
            openid=mp_openid,
            data=data,
            url=jump_url,
        ))

    # ---- 小程序 ----
    if not settings.wechat_mini_ready:
        outcomes.append(PushOutcome("小程序", "skipped", "not_configured",
                                    error_message="小程序订阅消息凭据未配置"))
    elif not mini_openid:
        outcomes.append(PushOutcome("小程序", "skipped", "no_recipient",
                                    error_message="该会话未绑定小程序 openid（用户未授权）"))
    else:
        outcomes.append(_send_once(
            channel="小程序",
            app_id=settings.wechat_mini_app_id,
            app_secret=settings.wechat_mini_app_secret,
            template_id=settings.wechat_mini_template_id,
            openid=mini_openid,
            data=data,
            page=jump_url,
        ))

    return outcomes


def encode_payload(payload: dict | None) -> dict | None:
    """push_log.payload 落库前的整形（保证可 JSON 序列化）。"""
    if not payload:
        return None
    try:
        return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    except (TypeError, ValueError):      # pragma: no cover - 防御性
        return {"raw": str(payload)[:500]}


__all__ = [
    "PushOutcome", "build_template_data", "encode_payload", "push_status",
    "send_price_alert",
]
