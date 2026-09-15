"""ORM 模型。

四张表覆盖一期全部需要持久化的状态：
  user_session      —— 设备/登录会话（鉴权）
  alert_subscription —— 降价订阅（M4，替换原内存态 dict）
  push_log          —— 推送发送记录（可审计、可重试、防重复推送）
  offer_click       —— CPS 跳转点击上报（M5，佣金对账的数据基础）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


def utcnow() -> datetime:
    """时区感知的当前时间（UTC）。全站统一使用，避免本地时区歧义。"""
    return datetime.now(timezone.utc)


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class UserSession(Base):
    """会话。

    一期策略：H5 匿名设备会话（首次访问由 /api/auth/session 签发），
    登录（微信 OAuth）后把 openid 绑定到同一会话，订阅跟随会话迁移。
    """

    __tablename__ = "user_session"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("s_"))
    #: 匿名设备指纹（前端 localStorage 持久化）；登录后作为历史订阅的归并键
    device_id: Mapped[str | None] = mapped_column(String(64), index=True)
    #: 微信 openid / unionid（接入后写入）
    openid: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    unionid: Mapped[str | None] = mapped_column(String(64), index=True)
    nickname: Mapped[str | None] = mapped_column(String(64))
    #: 公众号 / 小程序订阅消息所需的 openid 分开存（两者 openid 体系不同）
    mp_openid: Mapped[str | None] = mapped_column(String(64))
    mini_openid: Mapped[str | None] = mapped_column(String(64))
    is_member: Mapped[bool] = mapped_column(Boolean, default=False)
    member_expire_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    subs: Mapped[list["AlertSubscription"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class AlertSubscription(Base):
    """降价订阅（M4）。

    相对旧实现的修复：
      · 持久化 —— 进程重启/多 worker 不再丢订阅
      · 归属会话 —— 读写都带 session_id 过滤，杜绝越权
      · 时区感知时间戳 —— created_at 带 UTC tzinfo
      · 推送状态机 —— notify_status 记录真实投递结果，UI 不再假称「已推送」
    """

    __tablename__ = "alert_subscription"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("al_"))
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("user_session.id", ondelete="CASCADE"), index=True
    )
    #: 用户原始输入（展示用）
    product_input: Mapped[str] = mapped_column(String(128))
    #: 对齐后的商品主数据 key；未收录时为 None，并以 unmatched 标记
    product_key: Mapped[str | None] = mapped_column(String(64), index=True)
    product_label: Mapped[str] = mapped_column(String(160))
    target_price_cents: Mapped[int] = mapped_column(Integer)
    #: 只盯某个渠道（可空 = 全渠道最低）
    channel: Mapped[str | None] = mapped_column(String(32))
    #: 监测中 / 已触发 / 已暂停
    status: Mapped[str] = mapped_column(String(16), default="监测中")
    #: 推送通道状态：not_configured（凭据未接入）/ pending / sent / failed
    notify_status: Mapped[str] = mapped_column(String(20), default="not_configured")
    notify_error: Mapped[str | None] = mapped_column(Text)
    #: 最近一次命中说明（触发原因列表）
    last_reasons: Mapped[list | None] = mapped_column(JSON)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: 触发时的最低到手价（分）
    last_lowest_cents: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    session: Mapped[UserSession] = relationship(back_populates="subs")

    __table_args__ = (
        Index("ix_alert_session_status", "session_id", "status"),
    )


class PushLog(Base):
    """推送投递记录（幂等与审计）。"""

    __tablename__ = "push_log"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("pg_"))
    subscription_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("alert_subscription.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(16))      # 公众号 / 小程序
    template_id: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))       # sent / failed / skipped
    error_code: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_push_sub_created", "subscription_id", "created_at"),)


class OfferClick(Base):
    """CPS 跳转点击（M5 溯源与佣金对账）。"""

    __tablename__ = "offer_click"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("ck_"))
    session_id: Mapped[str | None] = mapped_column(String(32), index=True)
    product_key: Mapped[str | None] = mapped_column(String(64), index=True)
    offer_id: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(32))
    shop_name: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[str | None] = mapped_column(String(16))
    price_cents: Mapped[int | None] = mapped_column(Integer)
    #: 写入联盟链接里的 sub_id，用于对账归因
    sub_id: Mapped[str | None] = mapped_column(String(64), index=True)
    cps_url: Mapped[str | None] = mapped_column(Text)
    referer: Mapped[str | None] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriceSnapshot(Base):
    """历史到手价快照（M3 真实行情的落库基础）。

    定时任务每次轮询写入一条；行情曲线优先读真实快照，快照不足 90 天才用
    内置种子数据集补齐（并在响应里标注 data_basis）。
    """

    __tablename__ = "price_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_key: Mapped[str] = mapped_column(String(64), index=True)
    offer_id: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(32))
    version: Mapped[str | None] = mapped_column(String(16))
    price_cents: Mapped[int] = mapped_column(Integer)
    list_price_cents: Mapped[int | None] = mapped_column(Integer)
    lowest_price_cents: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (
        Index("ix_snapshot_product_time", "product_key", "captured_at"),
    )
