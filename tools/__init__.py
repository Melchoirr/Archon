"""工具层 — 函数导出 + Pydantic schema 导出"""

# ── 工具函数 ──────────────────────────────────────────────────
from .web_search import web_search
from .openalex import search_papers, get_paper_references, get_paper_citations
from .file_ops import read_file, write_file, append_file, edit_file, list_directory
from .bash_exec import run_command
from .idea_registry import IdeaRegistryService
from .memory import query_memory, add_experience
from .paper_manager import download_paper, read_paper_section, list_papers, check_local_knowledge
from .claude_code import claude_write_module, claude_fix_error, claude_review
from .knowledge_base import KnowledgeBaseManager, search_knowledge_base
from .context_manager import ContextManager
from .github_repo import clone_repo, summarize_repo, list_repos
from .idea_graph import add_idea_relationship as graph_add_relationship, get_idea_graph, suggest_combinations
from .vlm_analysis import analyze_image, analyze_plots_dir
from .phase_logger import log_phase_start, log_phase_end
from .venv_manager import setup_idea_venv
# idea_scorer 不在此导出，避免与 agents 循环 import
# 使用时直接: from tools.idea_scorer import score_all_ideas

# ── Pydantic 参数模型（schema 由 .to_schema() 生成）────────────
from shared.models.tool_params import (
    # file_ops
    ReadFileParams, WriteFileParams, AppendFileParams, EditFileParams, ListDirectoryParams,
    # web_search
    WebSearchParams,
    # openalex
    SearchPapersParams, GetPaperReferencesParams, GetPaperCitationsParams,
    # bash_exec
    RunCommandParams,
    # idea_registry
    ReadResearchStatusParams, AddIdeaParams,
    # memory
    QueryMemoryParams, AddExperienceParams,
    # paper_manager
    CheckLocalKnowledgeParams, DownloadPaperParams, ReadPaperSectionParams, ListPapersParams,
    # claude_code
    ClaudeWriteModuleParams, ClaudeFixErrorParams, ClaudeReviewParams,
    # knowledge_base
    SearchKBParams,
    # github_repo
    CloneRepoParams, SummarizeRepoParams, ListReposParams,
    # idea_graph
    AddRelationshipParams, GetGraphParams, SuggestCombinationsParams,
    # vlm_analysis
    AnalyzeImageParams, AnalyzePlotsParams,
    # phase_logger
    LogPhaseStartParams, LogPhaseEndParams,
    # idea_scorer
    ScoreIdeasParams,
    # venv_manager
    SetupVenvParams,
)

# ── 路径和服务 ────────────────────────────────────────────────
from shared.paths import PathManager
