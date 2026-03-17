"""FSM 数据模型 — 状态机状态、判定、转换记录、快照"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class FSMState(StrEnum):
    """所有 FSM 状态"""
    # Topic 级
    elaborate = "elaborate"
    survey = "survey"
    deep_survey = "deep_survey"
    ideation = "ideation"
    # Idea 级
    refine = "refine"
    theory_check = "theory_check"
    code_reference = "code_reference"
    code = "code"
    debug = "debug"
    experiment = "experiment"
    analyze = "analyze"
    conclude = "conclude"
    abandoned = "abandoned"
    completed = "completed"


class AnalysisVerdict(StrEnum):
    """ANALYZE 状态的结构化判定"""
    success = "success"
    tune = "tune"
    enrich = "enrich"
    restructure = "restructure"
    code_bug = "code_bug"
    need_literature = "need_literature"
    abandon = "abandon"


class TheoryVerdict(StrEnum):
    """THEORY_CHECK 判定"""
    sound = "sound"
    weak = "weak"
    flawed = "flawed"


class DebugVerdict(StrEnum):
    """DEBUG 判定"""
    tests_pass = "tests_pass"
    fixable = "fixable"
    needs_rewrite = "needs_rewrite"
    design_issue = "design_issue"


class SurveyVerdict(StrEnum):
    """SURVEY 评估判定"""
    sufficient = "sufficient"
    need_more = "need_more"


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


class TheoryDecision(BaseModel):
    """THEORY_CHECK 产出的结构化决策"""
    verdict: TheoryVerdict
    issues: list[str] = Field(default_factory=list)
    supporting_papers: list[str] = Field(default_factory=list)
    contradicting_papers: list[str] = Field(default_factory=list)
    revision_suggestions: list[str] = Field(default_factory=list)


class SurveyDecision(BaseModel):
    """SURVEY 产出的结构化决策"""
    verdict: SurveyVerdict
    coverage_score: float = Field(ge=0.0, le=1.0, default=0.0)
    covered_areas: list[str] = Field(default_factory=list)
    gap_areas: list[str] = Field(default_factory=list)
    recommended_queries: list[str] = Field(default_factory=list)


class DebugDecision(BaseModel):
    """DEBUG 产出的结构化决策（规则判断，非 LLM）"""
    verdict: DebugVerdict
    tests_total: int = 0
    tests_passed: int = 0
    error_types: list[str] = Field(default_factory=list)
    details: str = ""


class TransitionRecord(BaseModel):
    """状态转换记录"""
    timestamp: str
    from_state: str
    to_state: str
    trigger: str  # "auto:linear", "eval:tune", "user:override_to_refine"
    idea_id: str = ""
    feedback: str = ""
    decision_snapshot: dict | None = None


class IdeaFSMState(BaseModel):
    """单个 idea 的 FSM 运行时状态"""
    current_state: str = "refine"
    step_id: str = "S01"
    version: int = 1
    retry_counts: dict[str, int] = Field(default_factory=dict)
    feedback: str = ""


class FSMSnapshot(BaseModel):
    """持久化 FSM 快照 → {topic_dir}/fsm_state.yaml"""
    topic_state: str = "elaborate"
    idea_states: dict[str, IdeaFSMState] = Field(default_factory=dict)
    transition_history: list[TransitionRecord] = Field(default_factory=list)
