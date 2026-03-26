"""FSM 数据模型 — 状态机状态、判定枚举、恢复快照"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class FSMState(StrEnum):
    """所有 FSM 状态"""
    # Topic 级
    elaborate = "elaborate"
    survey = "survey"
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
    derivative = "derivative"


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


class IdeaFSMState(BaseModel):
    """单个 idea 的 FSM 运行时状态（纯恢复数据）"""
    current_state: str = "refine"
    step_id: str = "S01"
    version: int = 1
    retry_counts: dict[str, int] = Field(default_factory=dict)


class FSMSnapshot(BaseModel):
    """持久化 FSM 快照 → {topic_dir}/fsm_state.yaml（纯恢复数据）"""
    schema_version: int = 2
    topic_state: str = "elaborate"
    topic_retry_counts: dict[str, int] = Field(default_factory=dict)
    idea_states: dict[str, IdeaFSMState] = Field(default_factory=dict)
