"""审计日志模型 — 状态转换流转记录（给用户看的一等公民）"""

from __future__ import annotations

from pydantic import BaseModel


class TransitionRecord(BaseModel):
    """一条状态转换记录 — 精简但不重不漏"""
    timestamp: str
    from_state: str
    to_state: str
    trigger: str  # "auto:linear", "eval:tune", "user:override_to_refine"
    idea_id: str = ""
    verdict_summary: str = ""  # 一行人可读摘要，替代旧版 decision_snapshot
