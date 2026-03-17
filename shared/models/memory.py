"""经验日志数据模型"""

from __future__ import annotations

from pydantic import BaseModel

from .enums import ExperienceType


class ExperienceEntry(BaseModel):
    """一条经验日志"""
    timestamp: str
    topic_id: str = ""
    idea_id: str = ""
    phase: str = ""
    type: ExperienceType
    summary: str
    details: str = ""
    tags: list[str] = []
