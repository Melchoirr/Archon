"""评估器决策模型 — 各评估器产出的结构化判定"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .fsm import AnalysisVerdict, TheoryVerdict, DebugVerdict, SurveyVerdict


class AnalysisDecision(BaseModel):
    """ANALYZE 产出的结构化决策"""
    verdict: AnalysisVerdict
    confidence: float = Field(ge=0.0, le=1.0)
    metrics_vs_baseline: dict[str, dict] = Field(default_factory=dict)
    metrics_vs_expectation: dict[str, dict] = Field(default_factory=dict)
    expectations_met_ratio: float = Field(ge=0.0, le=1.0, default=0.0)
    failure_category: str | None = None
    root_cause: str = ""
    iteration_trend: str = "unknown"
    remaining_potential: float = 0.5
    next_action_detail: str = ""
    suggested_changes: list[str] = Field(default_factory=list)

    def to_summary(self) -> str:
        return f"{self.verdict}, confidence={self.confidence}, met_ratio={self.expectations_met_ratio}"


class TheoryDecision(BaseModel):
    """THEORY_CHECK 产出的结构化决策"""
    verdict: TheoryVerdict
    issues: list[str] = Field(default_factory=list)
    supporting_papers: list[str] = Field(default_factory=list)
    contradicting_papers: list[str] = Field(default_factory=list)
    revision_suggestions: list[str] = Field(default_factory=list)
    novelty_assessment: str = ""
    novelty_score: float = Field(ge=0.0, le=1.0, default=0.5)
    differentiation: list[str] = Field(default_factory=list)
    mechanism_reasoning: str = ""
    mechanism_confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    similar_ideas_in_batch: list[str] = Field(default_factory=list)

    def to_summary(self) -> str:
        issues = f", {len(self.issues)} issues" if self.issues else ""
        return f"{self.verdict}, novelty={self.novelty_score}{issues}"


class SurveyDecision(BaseModel):
    """SURVEY 产出的结构化决策"""
    verdict: SurveyVerdict
    coverage_score: float = Field(ge=0.0, le=1.0, default=0.0)
    covered_areas: list[str] = Field(default_factory=list)
    gap_areas: list[str] = Field(default_factory=list)
    recommended_queries: list[str] = Field(default_factory=list)

    def to_summary(self) -> str:
        gaps_preview = ", ".join(self.gap_areas[:3])
        return f"{self.verdict}, coverage={self.coverage_score}, gaps: {gaps_preview}"


class DebugDecision(BaseModel):
    """DEBUG 产出的结构化决策（规则判断，非 LLM）"""
    verdict: DebugVerdict
    tests_total: int = 0
    tests_passed: int = 0
    error_types: list[str] = Field(default_factory=list)
    details: str = ""

    def to_summary(self) -> str:
        return f"{self.verdict}, {self.tests_passed}/{self.tests_total} passed"
