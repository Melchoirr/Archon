"""Idea 注册表模型 — 替代 research_tree 的元数据管理职责"""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from .enums import IdeaStatus, IdeaCategory, RelationType


class Score(BaseModel):
    """Idea 评分，含自动计算的 composite"""
    novelty: int = Field(ge=1, le=5)
    significance: int = Field(ge=1, le=5)
    feasibility: int = Field(ge=1, le=5)
    alignment: int = Field(ge=1, le=5)
    rank: int | None = None

    @computed_field
    @property
    def composite(self) -> float:
        return round(
            0.35 * self.novelty + 0.35 * self.significance
            + 0.20 * self.feasibility + 0.10 * self.alignment, 2
        )


class Relationship(BaseModel):
    """Idea 间关系"""
    target: str
    type: RelationType


class TopicMeta(BaseModel):
    """Topic 元信息"""
    topic_id: str
    topic_brief: str
    topic: str
    description: str = ""


class IdeaEntry(BaseModel):
    """一个研究 idea 的元数据（不含阶段状态，由 FSM 管理）"""
    id: str
    title: str
    brief: str
    category: IdeaCategory
    status: IdeaStatus = IdeaStatus.proposed
    created_at: str = ""
    scores: Score | None = None
    relationships: list[Relationship] = Field(default_factory=list)


class IdeaRegistry(BaseModel):
    """Idea 注册表，持久化到 {topic_dir}/idea_registry.yaml"""
    topic: TopicMeta
    ideas: list[IdeaEntry] = Field(default_factory=list)
