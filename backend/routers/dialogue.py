"""M1 · AI 智能对话选型。

契约要点（前端按此渲染，不再需要正则切块）：
  · ``sections`` —— 固定五段结构化输出：适配推荐 / 全网比价 / 版本差异 / 入手建议 / 风险提示
  · ``reply``    —— 同样内容的纯文本版（复制粘贴、非结构化消费方用）
  · ``data_basis`` —— live / seed / mixed，前端据此如实标注数据来源
  · ``unmatched`` —— 商品未收录时如实告知并给候选，**不回落**到默认商品

合规：不承诺正品、不做真伪鉴定；价格为行情参考价；只做版本差异科普与风险筛查。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.config import settings
from core.db import get_session
from core.models import UserSession
from core.security import optional_session
from services import dialogue as dialogue_service

router = APIRouter()


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=500, description="用户自然语言输入")


@router.post("/chat")
def chat(
    body: ChatIn,
    db: Session = Depends(get_session),
    session: UserSession | None = Depends(optional_session),
):
    """一次对话：意图解析 → 行情聚合 → 五段结论。"""
    result = dialogue_service.chat(
        body.text, session_id=session.id if session else None, db=db
    )
    result["session_id"] = session.id if session else None
    result["disclaimer"] = settings.disclaimer
    return result


@router.get("/suggestions")
def suggestions():
    """可点选的热门问法 + 已收录商品（首页引导用，避免用户不知道能问什么）。"""
    from core.catalog import suggest_products

    return {
        "products": suggest_products(),
        "examples": [
            "预算800，混油皮，抗初老，推荐一款大牌精华，帮我全网比价",
            "兰蔻小黑瓶50ml，看近3个月降价记录，对比天猫和保税仓价格",
            "想买SK-II神仙水，怎么区分国行和免税版，哪个性价比更高",
            "迪奥999，哪家渠道最便宜，有没有临期风险",
        ],
        "modules": [
            {"key": k, "title": t}
            for k, t in dialogue_service.SECTION_ORDER
        ],
    }
