"""Pydantic 数据模型层 — 所有结构化数据的类型定义"""

from .enums import (
    PhaseState, IdeaStatus, IdeaCategory,
    ExperienceType, RelationType, PhaseName,
)
from .research_tree import (
    Score, IdeaPhases, Iteration, ExperimentStep,
    Relationship, Idea, ElaborateState, SurveyState,
    ResearchRoot, ResearchTree,
)
from .paper import Author, ExternalIds, Paper, PaperIndexEntry
from .memory import ExperienceEntry
from .config import TopicConfig
from .tool_params import ToolParamsBase
from .fsm import (
    FSMState, AnalysisVerdict, TheoryVerdict, DebugVerdict, SurveyVerdict,
    AnalysisDecision, TheoryDecision, SurveyDecision, DebugDecision,
    TransitionRecord, IdeaFSMState, FSMSnapshot,
)
