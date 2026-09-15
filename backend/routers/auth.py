"""会话路由。

一期是 H5 优先：用户**不需要注册**就能对话 / 比价 / 看行情；只有「写操作」
（降价订阅）需要会话。为了既保护隐私又让订阅在刷新后不丢，采用设备会话：

    POST /api/auth/session  {device_id?}  ->  {session_id, ...}

· 首次访问：前端生成 device_id 存 localStorage 后调本接口换 sid
· 再次访问：同一 device_id 复用同一 sid（订阅不会「换个人」）
· 微信登录（预留）：凭据到位后走 /api/auth/wechat，把 openid 绑到同一会话
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.config import settings
from core.db import get_session
from core.errors import DomainError
from core.models import UserSession
from core.security import get_or_create_device_session, require_session

router = APIRouter()


class SessionIn(BaseModel):
    device_id: str | None = Field(
        default=None, max_length=64,
        description="设备指纹（前端生成并持久化）。省略则每次都是新会话。",
    )


def _public(row: UserSession) -> dict:
    return {
        "session_id": row.id,
        "device_id": row.device_id,
        "is_member": row.is_member,
        "member_expire_at": (
            row.member_expire_at.isoformat() if row.member_expire_at else None
        ),
        "logged_in": bool(row.openid or row.mp_openid or row.mini_openid),
        "wechat_bound": bool(row.mp_openid or row.mini_openid),
        # 推送可达性：未绑定 openid 时前端要如实说「收不到微信提醒」
        "push_reachable": bool(row.mp_openid or row.mini_openid) and settings.push_ready,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("/session")
def create_session(body: SessionIn, db: Session = Depends(get_session)):
    """换取（或复用）会话。幂等：同 device_id 永远返回同一 sid。"""
    device_id = (body.device_id or "").strip() or None
    if device_id and len(device_id) < 8:
        raise DomainError("INVALID_PARAM", "device_id 过短，至少 8 个字符。")
    row = get_or_create_device_session(db, device_id)
    return {
        **_public(row),
        "transport": {
            "header": "Authorization: Bearer <session_id>",
            "alternative": "X-Session-Id: <session_id>",
        },
    }


@router.get("/me")
def me(row: UserSession = Depends(require_session)):
    """当前会话信息（前端「我的」页用它判断登录 / 推送可达状态）。"""
    return _public(row)


@router.post("/wechat")
def wechat_login():
    """微信登录（预留）。

    真实 OAuth 需要公众号 / 小程序的 AppID 与 AppSecret 调
    ``sns/oauth2/access_token`` 或小程序 ``jscode2session`` 换 openid。
    凭据未接入时不伪造登录态，直接返回 501 并说明所需配置。
    """
    from core.errors import DomainError as _E

    raise _E(
        "WECHAT_NOT_CONFIGURED",
        "微信登录尚未接入：需配置公众号 / 小程序的 AppID 与 AppSecret 后启用。"
        "当前可使用匿名设备会话（对话、比价、行情、订阅均可正常使用）。",
        http_status=501,
    )
