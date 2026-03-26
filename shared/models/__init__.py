"""Pydantic 数据模型层 — 所有结构化数据的类型定义"""

from .enums import (
    PhaseState, IdeaStatus, IdeaCategory,
    ExperienceType, RelationType,
)
from .paper import Author, ExternalIds, Paper, PaperIndexEntry
from .memory import ExperienceEntry
from .config import GlobalConfig
from .tool_params import ToolParamsBase
from .fsm import (
    FSMState, AnalysisVerdict, TheoryVerdict, DebugVerdict, SurveyVerdict,
    IdeaFSMState, FSMSnapshot,
)
from .decisions import (
    AnalysisDecision, TheoryDecision, SurveyDecision, DebugDecision,
)
from .audit import TransitionRecord
from .idea_registry import (
    Score, Relationship, TopicMeta, IdeaEntry, IdeaRegistry,
)
