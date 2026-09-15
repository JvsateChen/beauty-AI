"""会话鉴权。

一期设计（与 PRD 的「H5 先行、小程序同构预留」一致）：
  · 未登录也能用（对话/比价/行情是公开只读能力）—— 但**写操作必须带会话**
  · 会话来源两种：
      1) 前端持 device_id 调 POST /api/auth/session 换 sid（匿名设备会话）
      2) 微信 OAuth 登录后把 openid 绑到会话（预留，凭据到位即生效）
  · 所有订阅读写都以 session_id 为过滤条件 —— 这是修复「匿名可读写他人订阅」的关键。

约定：客户端通过 `Authorization: Bearer <sid>` 或 `X-Session-Id: <sid>` 传会话。
"""
from __future__ import annotations

import logging

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import settings
from core.db import get_session
from core.errors import ForbiddenError, UnauthorizedError
from core.models import UserSession, utcnow

logger = logging.getLogger("caixuan.auth")


def _extract_token(
    authorization: str | None,
    x_session_id: str | None,
) -> str | None:
    if x_session_id:
        return x_session_id.strip() or None
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip() or None
    return None


def resolve_session(
    db: Session,
    token: str | None,
) -> UserSession | None:
    if not token:
        return None
    row = db.get(UserSession, token)
    if row is not None:
        row.last_seen_at = utcnow()
    return row


def require_session(
    authorization: str | None = Header(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    db: Session = Depends(get_session),
) -> UserSession:
    """写操作守卫：没有合法会话直接 401。

    注意：这里**不**接受 DB 中不存在的 sid —— 伪造 sid 会被拒，
    因此「知道别人 id 就能删别人订阅」的越权路径被切断。
    """
    if not settings.allow_anonymous_session:
        # 关闭匿名会话时，必须登录（openid 绑定）才可用写能力
        row = resolve_session(db, _extract_token(authorization, x_session_id))
        if row is None or not (row.openid or row.mp_openid or row.mini_openid):
            raise UnauthorizedError("LOGIN_REQUIRED", "该能力需登录后使用。")
        return row

    row = resolve_session(db, _extract_token(authorization, x_session_id))
    if row is None:
        raise UnauthorizedError(
            "SESSION_REQUIRED",
            "缺少有效会话。请先调用 POST /api/auth/session 获取会话后再操作。",
        )
    return row


def optional_session(
    authorization: str | None = Header(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
    db: Session = Depends(get_session),
) -> UserSession | None:
    """只读接口用：有会话就带上（用于个性化），没有也不报错。"""
    return resolve_session(db, _extract_token(authorization, x_session_id))


def assert_owns(row_session_id: str, current: UserSession) -> None:
    """归属校验：资源不属于当前会话即 403（不泄露资源是否存在）。"""
    if row_session_id != current.id:
        logger.warning(
            "越权访问被拒绝：资源归属 %s，当前会话 %s", row_session_id, current.id
        )
        raise ForbiddenError("NOT_OWNER", "该资源不属于当前会话。")


def get_or_create_device_session(db: Session, device_id: str | None) -> UserSession:
    """按 device_id 复用会话，避免用户每次刷新产生新会话导致订阅「换个人」。"""
    if device_id:
        row = db.scalar(
            select(UserSession)
            .where(UserSession.device_id == device_id)
            .order_by(UserSession.created_at.desc())
            .limit(1)
        )
        if row is not None:
            row.last_seen_at = utcnow()
            db.commit()
            return row

    row = UserSession(device_id=device_id)
    db.add(row)
    db.commit()
    return row
