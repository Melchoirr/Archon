"""研究树数据模型 — 对应 research_tree.yaml 结构"""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from .enums import PhaseState, IdeaStatus, IdeaCategory, RelationType


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


class IdeaPhases(BaseModel):
    """Idea 各阶段的状态"""
    refinement: PhaseState = PhaseState.pending
    theory_check: PhaseState = PhaseState.pending
    code_reference: PhaseState = PhaseState.pending
    coding: PhaseState = PhaseState.pending
    debug: PhaseState = PhaseState.pending
    experiment: PhaseState = PhaseState.pending
    analysis: PhaseState = PhaseState.pending
    conclusion: PhaseState = PhaseState.pending


class Iteration(BaseModel):
    """实验迭代"""
    version: int
    status: PhaseState = PhaseState.pending
    config_diff: str | None = None


class ExperimentStep(BaseModel):
    """实验步骤"""
    step_id: str
    name: str
    status: PhaseState = PhaseState.pending
    max_iter: int = 3
    iterations: list[Iteration] = []


class Relationship(BaseModel):
    """Idea 间关系"""
    target: str
    type: RelationType


class Idea(BaseModel):
    """一个研究想法的完整状态"""
    id: str
    brief: str
    title: str
    category: IdeaCategory
    status: IdeaStatus = IdeaStatus.proposed
    created_at: str = ""
    scores: Score | None = None
    phases: IdeaPhases = Field(default_factory=IdeaPhases)
    relationships: list[Relationship] = []
    experiment_steps: list[ExperimentStep] = []


class ElaborateState(BaseModel):
    """elaborate 阶段状态"""
    status: PhaseState = PhaseState.pending


class SurveyState(BaseModel):
    """survey 阶段状态"""
    rounds: int = 0
    current_round: int = 0
    status: PhaseState = PhaseState.pending


class ResearchRoot(BaseModel):
    """研究树根节点"""
    topic_id: str
    topic_brief: str
    topic: str
    description: str = ""
    status: str = "initialized"
    elaborate: ElaborateState = Field(default_factory=ElaborateState)
    survey: SurveyState = Field(default_factory=SurveyState)
    ideas: list[Idea] = []


class ResearchTree(BaseModel):
    """研究树顶层结构，对应 research_tree.yaml"""
    root: ResearchRoot
