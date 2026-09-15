"""M4 · 降价订阅评估与推送编排。

职责：把「订阅条款」与「当前行情」比对，产出**可解释的触发原因**，命中后真正
走一遍推送并落 push_log；未接入推送通道时如实标注，绝不假称已推送。

三个触发条件（与 PRD 一致）：
  1. 跌破心理底价   —— 当前最低到手价 ≤ 用户设定阈值
  2. 创历史新低     —— 当前价低于**此前**（不含今日）90 天最低价
  3. 大额补贴       —— 单渠道补贴金额达到该商品官方价的 15% 以上

设计要点：
  · 触发原因以数组返回，前端逐条展示，不做「黑箱提醒」
  · 推送冷却（默认 12 小时）：价格在阈值附近抖动时不会反复打扰
  · push_log 记录每次投递的通道 / 状态 / 错误码 / 载荷，便于对账与重放
  · 订阅归属 session，读写都带 session_id 过滤（杜绝越权）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from core.catalog import get_product, match_product
from core.domain import CHANNELS, cents_to_yuan, cheapest
from core.errors import DomainError, NotFoundError
from core.models import AlertSubscription, PushLog, UserSession, utcnow
from services import push as push_service
from services.market import get_offers

logger = logging.getLogger("caixuan.alert")

#: 大额补贴判定阈值：补贴 / 官方价 ≥ 15%
BIG_SUBSIDY_RATIO = 0.15

#: 阈值下限保护，避免误填 0 元把「永远触发」变成骚扰
MIN_TARGET_CENTS = 100

STATUS_WATCHING = "监测中"
STATUS_TRIGGERED = "已触发"
STATUS_PAUSED = "已暂停"


@dataclass
class Evaluation:
    reasons: list[str]
    lowest_cents: int | None
    lowest_channel: str | None
    lowest_label: str | None
    jump_url: str | None
    trend_low_cents: int | None


def _prior_low_cents(trend: dict) -> int | None:
    """**此前**（不含当日）90 天最低价。

    为什么要排除当日：种子序列的最后一个点等于当前价，若把它算进最低价，
    「创历史新低」会对任何一天都成立 —— 那就成了假警报。真实语义应是
    「今天的价格低于过去的价格」。
    """
    points = trend.get("points") or []
    if len(points) < 2:
        return None
    prior = [float(p["price"]) for p in points[:-1]]
    if not prior:
        return None
    return int(round(min(prior) * 100))


def evaluate(
    sub: AlertSubscription,
    offers: list[dict],
    trend: dict,
) -> Evaluation:
    """比对订阅条款与当前行情，产出触发原因。"""
    scoped = [o for o in offers if not sub.channel or o.get("channel") == sub.channel]
    scope_note = f"（仅统计「{sub.channel}」渠道）" if sub.channel else ""
    if not scoped:
        return Evaluation([], None, None, None, None, None)

    best = cheapest(scoped)
    lowest_cents = best["price_cents"] if best else None
    reasons: list[str] = []

    # 1) 跌破心理底价
    if lowest_cents is not None and lowest_cents <= sub.target_price_cents:
        reasons.append(
            f"当前最低到手价 ¥{cents_to_yuan(lowest_cents)} 已跌破你设定的 "
            f"¥{cents_to_yuan(sub.target_price_cents)}{scope_note}"
        )

    # 2) 创历史新低（与此前 90 天最低比）
    prior = _prior_low_cents(trend)
    if lowest_cents is not None and prior is not None and lowest_cents < prior:
        reasons.append(
            f"创 90 天新低：当前 ¥{cents_to_yuan(lowest_cents)} 低于此前最低 "
            f"¥{cents_to_yuan(prior)}"
        )

    # 3) 大额补贴
    big = [
        o for o in scoped
        if float(o.get("list_price") or 0) > 0
        and (float((o.get("benefits") or {}).get("subsidy") or 0) / float(o["list_price"]))
        >= BIG_SUBSIDY_RATIO
    ]
    if big:
        top = max(big, key=lambda o: float((o.get("benefits") or {}).get("subsidy") or 0))
        subsidy = float((top.get("benefits") or {}).get("subsidy") or 0)
        pct = round(subsidy / float(top["list_price"]) * 100, 1)
        reasons.append(
            f"{top.get('channel')}出现大额平台补贴 ¥{subsidy:g}（占官方价 {pct}%）"
        )

    return Evaluation(
        reasons=reasons,
        lowest_cents=lowest_cents,
        lowest_channel=str(best.get("channel")) if best else None,
        lowest_label=(
            f"{best.get('channel')}·{best.get('shop_name')}" if best else None
        ),
        jump_url=(best or {}).get("cps_url"),
        trend_low_cents=prior,
    )


def _cooldown_ok(sub: AlertSubscription) -> bool:
    from core.config import settings

    cooldown = settings.push_cooldown_seconds
    if cooldown <= 0 or sub.last_notified_at is None:
        return True
    last = sub.last_notified_at
    if last.tzinfo is None:                       # SQLite 可能回读成 naive
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last).total_seconds() >= cooldown


def refresh_subscription(
    db: OrmSession,
    sub: AlertSubscription,
    *,
    send: bool = True,
) -> dict:
    """拉取当前行情 → 评估 → （可选）推送 → 更新订阅状态与推送日志。"""
    if sub.product_key is None:
        return _snapshot(sub, reasons=[], notify="not_configured",
                         note="该订阅的商品未被收录，无法监测价格")

    market = get_offers(sub.product_key, session_id=sub.session_id)
    from services.trend import get_trend

    best = cheapest(market.offers)
    current = cents_to_yuan(best["price_cents"]) if best else 0.0
    trend = get_trend(market.product, current, db=db)

    ev = evaluate(sub, market.offers, trend)
    sub.last_checked_at = utcnow()
    sub.last_lowest_cents = ev.lowest_cents
    sub.last_reasons = ev.reasons or None
    sub.status = STATUS_TRIGGERED if ev.reasons else STATUS_WATCHING

    outcomes: list[push_service.PushOutcome] = []
    if ev.reasons and send and _cooldown_ok(sub):
        session = db.get(UserSession, sub.session_id)
        outcomes = push_service.send_price_alert(
            product_label=sub.product_label,
            lowest=cents_to_yuan(ev.lowest_cents or 0),
            target=cents_to_yuan(sub.target_price_cents),
            lowest_channel=ev.lowest_channel or "",
            mp_openid=session.mp_openid if session else None,
            mini_openid=session.mini_openid if session else None,
            jump_url=ev.jump_url,
        )
        for o in outcomes:
            fields = o.as_log_fields()
            db.add(PushLog(
                subscription_id=sub.id,
                channel=fields["channel"],
                template_id=(
                    push_service.settings.wechat_mp_template_id
                    if o.channel == "公众号"
                    else push_service.settings.wechat_mini_template_id
                ) or None,
                payload=push_service.encode_payload(fields["payload"]),
                status=fields["status"],
                error_code=fields["error_code"],
                error_message=fields["error_message"],
            ))
        if any(o.status == "sent" for o in outcomes):
            sub.last_notified_at = utcnow()
            notify = "sent"
        elif outcomes and all(o.detail == "not_configured" for o in outcomes):
            notify = "not_configured"
        elif all(o.detail == "no_recipient" for o in outcomes):
            notify = "no_recipient"
        else:
            notify = "failed"
        sub.notify_status = notify
        sub.notify_error = "; ".join(
            f"{o.channel}：{o.error_message}" for o in outcomes if o.error_message
        ) or None
    elif ev.reasons and not _cooldown_ok(sub):
        # 命中但在冷却期：不改写 notify_status，保留上一次真实投递结果
        pass
    elif not ev.reasons:
        # 未命中：不清空历史投递结果，但状态回到「监测中」
        pass

    db.flush()
    return _snapshot(
        sub,
        reasons=ev.reasons,
        notify=sub.notify_status,
        note=None,
        current_lowest=cents_to_yuan(ev.lowest_cents) if ev.lowest_cents else None,
        trend_low=cents_to_yuan(ev.trend_low_cents) if ev.trend_low_cents else None,
        push_results=[
            {"channel": o.channel, "status": o.status,
             "detail": o.detail, "error": o.error_message}
            for o in outcomes
        ],
    )


def _snapshot(
    sub: AlertSubscription,
    *,
    reasons: list[str],
    notify: str,
    note: str | None = None,
    current_lowest: float | None = None,
    trend_low: float | None = None,
    push_results: list[dict] | None = None,
) -> dict:
    from services.push import push_status

    ps = push_status()
    return {
        "id": sub.id,
        "product_input": sub.product_input,
        "product_key": sub.product_key,
        "product_label": sub.product_label,
        "target_price": cents_to_yuan(sub.target_price_cents),
        "channel": sub.channel,
        "status": sub.status,
        "triggered": bool(reasons),
        "reasons": reasons,
        "current_lowest": current_lowest,
        "trend_low": trend_low,
        "notify_status": notify,
        "notify_status_label": _notify_label(notify),
        "notify_error": sub.notify_error,
        "push_ready": ps["ready"],
        "push_channels": ps["channels"],
        "push_user_message": ps["user_message"],
        "push_results": push_results or [],
        "checked_at": sub.last_checked_at.isoformat() if sub.last_checked_at else None,
        "notified_at": sub.last_notified_at.isoformat() if sub.last_notified_at else None,
        "created_at": sub.created_at.isoformat() if sub.created_at else None,
        "note": note,
    }


_NOTIFY_LABELS = {
    "not_configured": "推送通道未接入",
    "no_recipient": "未授权微信接收",
    "pending": "待推送",
    "sent": "已推送",
    "failed": "推送失败",
}


def _notify_label(state: str) -> str:
    return _NOTIFY_LABELS.get(state, state)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_subscriptions(db: OrmSession, session: UserSession) -> list[AlertSubscription]:
    return list(db.scalars(
        select(AlertSubscription)
        .where(AlertSubscription.session_id == session.id)
        .order_by(AlertSubscription.created_at.desc())
    ).all())


def create_subscription(
    db: OrmSession,
    session: UserSession,
    *,
    product: str,
    target_price: float,
    channel: str | None = None,
) -> tuple[AlertSubscription, dict]:
    """新增订阅。商品未收录时**不拒绝**，而是标记为不可监测并如实告知。"""
    raw = (product or "").strip()
    if not raw:
        raise DomainError("INVALID_PARAM", "请先说明要监测的商品。")

    target_cents = int(round(float(target_price) * 100))
    if target_cents < MIN_TARGET_CENTS:
        raise DomainError(
            "TARGET_TOO_LOW",
            f"目标价过低（至少 ¥{cents_to_yuan(MIN_TARGET_CENTS)}），"
            "请填写你愿意出手的价格。",
        )

    if channel and channel not in CHANNELS:
        raise DomainError("INVALID_CHANNEL", f"渠道「{channel}」不在收录范围内。")

    res = match_product(raw)
    product_obj = res.product if res.ok else None
    if product_obj is not None:
        label = f"{product_obj.brand} {product_obj.name} {product_obj.spec}"
        key = product_obj.key
    else:
        label = raw[:160]
        key = None

    # 同一会话重复订阅同一商品同一渠道时，只更新阈值（幂等，避免列表堆积）
    existing = db.scalar(
        select(AlertSubscription).where(
            AlertSubscription.session_id == session.id,
            AlertSubscription.product_label == label,
            AlertSubscription.channel == channel,
        )
    )
    if existing is not None:
        existing.target_price_cents = target_cents
        existing.status = STATUS_WATCHING
        db.flush()
        snap = refresh_subscription(db, existing)
        snap["note"] = "该商品原本已在监测中，已为你更新目标价。"
        return existing, snap

    row = AlertSubscription(
        session_id=session.id,
        product_input=raw[:128],
        product_key=key,
        product_label=label,
        target_price_cents=target_cents,
        channel=channel,
        status=STATUS_WATCHING,
        notify_status="not_configured",
    )
    db.add(row)
    db.flush()

    snap = _snapshot(row, reasons=[], notify="not_configured",
                     note=("订阅已创建；该商品暂未收录，"
                           "收录后自动开始价格监测。" if key is None else None))
    if key is not None:
        snap = refresh_subscription(db, row)
    return row, snap


def delete_subscription(db: OrmSession, session: UserSession, sub_id: str) -> dict:
    row = db.get(AlertSubscription, sub_id)
    if row is None or row.session_id != session.id:
        # 不区分「不存在」与「不属于你」，避免探测他人订阅 id
        raise NotFoundError("SUBSCRIPTION_NOT_FOUND", "该订阅不存在或已删除。")
    db.delete(row)
    db.flush()
    return {"ok": True, "id": sub_id}


# ---------------------------------------------------------------------------
# 定时轮询（供 scheduler 调用）
# ---------------------------------------------------------------------------

def poll_active_subscriptions(db: OrmSession, limit: int = 200) -> dict:
    """遍历所有「监测中 / 已触发」的订阅，刷新行情并在命中时推送。"""
    rows = list(db.scalars(
        select(AlertSubscription)
        .where(AlertSubscription.status.in_([STATUS_WATCHING, STATUS_TRIGGERED]))
        .where(AlertSubscription.product_key.is_not(None))
        .order_by(AlertSubscription.last_checked_at.is_(None).desc(),
                  AlertSubscription.last_checked_at.asc())
        .limit(limit)
    ).all())

    checked = triggered = sent = 0
    for sub in rows:
        try:
            snap = refresh_subscription(db, sub)
        except Exception as exc:               # 单个订阅失败不影响整批
            logger.warning("订阅 %s 刷新失败：%s", sub.id, exc)
            db.rollback()
            continue
        checked += 1
        if snap["triggered"]:
            triggered += 1
        if snap["notify_status"] == "sent":
            sent += 1
    return {"checked": checked, "triggered": triggered, "pushed": sent}


__all__ = [
    "BIG_SUBSIDY_RATIO", "Evaluation", "STATUS_PAUSED", "STATUS_TRIGGERED",
    "STATUS_WATCHING", "create_subscription", "delete_subscription", "evaluate",
    "list_subscriptions", "poll_active_subscriptions", "refresh_subscription",
]
