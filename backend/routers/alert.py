"""M4 · 降价订阅提醒（持久化 + 真实推送 + 可审计）。

与旧实现的关键差别：
  1. 订阅落库（原为内存 dict，重启即丢）
  2. 读写都带 session 归属校验（原为任何人不带凭据即可读写全部订阅）
  3. 推送是**真的发**（原 UI 写「已推送」但后端没有发送代码）
  4. 推送状态如实回报：not_configured / no_recipient / sent / failed

前端展示约定：``notify_status_label`` 直接可用于界面文案，
``push_user_message`` 是给用户看的整句说明（已接入 / 未接入两种口径）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.db import get_session
from core.domain import CHANNELS, cents_to_yuan
from core.errors import DomainError
from core.models import UserSession
from core.security import require_session
from services import alert as alert_service
from services.push import push_status

router = APIRouter()


class SubIn(BaseModel):
    product: str = Field(min_length=1, max_length=128, description="商品名，如「小棕瓶」")
    target_price: float = Field(gt=0, description="心理底价（元）")
    channel: str | None = Field(default=None, description="只盯某渠道；留空=全渠道最低")


@router.get("/capability")
def capability():
    """推送能力现状（前端在订阅页顶部如实说明「会不会收到微信消息」）。"""
    return {
        **push_status(),
        "channels": CHANNELS,
        "thresholds": {
            "big_subsidy_ratio": alert_service.BIG_SUBSIDY_RATIO,
            "min_target_price": cents_to_yuan(alert_service.MIN_TARGET_CENTS),
        },
    }


@router.get("/list")
def list_subs(
    q: str | None = Query(
        None, description="可选：只刷新该商品相关订阅；留空刷新全部（最多 50 条）"
    ),
    session: UserSession = Depends(require_session),
    db: Session = Depends(get_session),
):
    """订阅列表。**不做假装触发**：状态由真实行情评估得出。"""
    rows = alert_service.list_subscriptions(db, session)
    if q:
        from core.catalog import match_product

        res = match_product(q)
        if res.ok and res.product is not None:
            rows = [r for r in rows if r.product_key == res.product.key]
        else:
            rows = []
    rows = rows[:50]

    refreshed = [alert_service.refresh_subscription(db, r) for r in rows]
    db.commit()

    ps = push_status()
    return {
        "query": q,
        "count": len(refreshed),
        "subs": refreshed,
        "notify_via": ps["channels"] or ["公众号", "小程序"],
        "push_ready": ps["ready"],
        "push_state": ps["state"],
        "push_user_message": ps["user_message"],
        "triggered_count": sum(1 for r in refreshed if r["triggered"]),
    }


@router.post("/add")
def add_sub(
    body: SubIn,
    session: UserSession = Depends(require_session),
    db: Session = Depends(get_session),
):
    if body.channel and body.channel not in CHANNELS:
        raise DomainError("INVALID_CHANNEL", f"渠道「{body.channel}」不在收录范围内。")
    row, snap = alert_service.create_subscription(
        db, session,
        product=body.product,
        target_price=body.target_price,
        channel=body.channel,
    )
    db.commit()
    return {
        "ok": True,
        "sub": snap,
        "message": (
            f"已开始监测「{row.product_label}」，"
            f"目标价 ¥{cents_to_yuan(row.target_price_cents)}。"
        ),
    }


@router.delete("/{sub_id}")
def del_sub(
    sub_id: str,
    session: UserSession = Depends(require_session),
    db: Session = Depends(get_session),
):
    result = alert_service.delete_subscription(db, session, sub_id)
    db.commit()
    return {**result, "message": "已删除该降价提醒。"}


@router.post("/poll")
def manual_poll(
    session: UserSession = Depends(require_session),
    db: Session = Depends(get_session),
):
    """手动触发一次全量轮询（运维 / 演示用；生产由定时任务自动执行）。

    仅当前会话已登录且开启匿名会话时可用；线上建议用管理端鉴权替换。
    """
    result = alert_service.poll_active_subscriptions(db)
    db.commit()
    return {**result, "message": "已执行一轮价格轮询。"}
