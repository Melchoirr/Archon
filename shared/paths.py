"""统一路径管理器 — 所有文件路径的单一真相源"""

from __future__ import annotations

import re
from pathlib import Path


class PathManager:
    """项目路径管理器。一个实例对应一个 topic（或仅全局）。"""

    def __init__(self, project_root: str | Path, topic_dir: str | Path | None = None):
        self.root = Path(project_root)
        self._topic = Path(topic_dir) if topic_dir else None

    # ── 全局路径 ──────────────────────────────────────────────

    @property
    def knowledge_dir(self) -> Path:
        return self.root / "knowledge"

    @property
    def papers_dir(self) -> Path:
        return self.knowledge_dir / "papers"

    @property
    def pdf_dir(self) -> Path:
        return self.papers_dir / "pdf"

    @property
    def parsed_dir(self) -> Path:
        return self.papers_dir / "parsed"

    @property
    def summaries_dir(self) -> Path:
        return self.papers_dir / "summaries"

    @property
    def paper_index(self) -> Path:
        return self.papers_dir / "index.yaml"

    @property
    def repos_dir(self) -> Path:
        return self.knowledge_dir / "repos"

    @property
    def repo_index(self) -> Path:
        return self.repos_dir / "index.yaml"

    @property
    def dataset_cards_dir(self) -> Path:
        return self.knowledge_dir / "dataset_cards"

    @property
    def dataset_index(self) -> Path:
        return self.dataset_cards_dir / "index.yaml"

    @property
    def memory_dir(self) -> Path:
        return self.root / "memory"

    @property
    def experience_log(self) -> Path:
        return self.memory_dir / "experience_log.yaml"

    @property
    def failed_ideas(self) -> Path:
        return self.memory_dir / "failed_ideas.md"

    @property
    def insights(self) -> Path:
        return self.memory_dir / "insights.md"

    @property
    def topics_dir(self) -> Path:
        return self.root / "topics"

    # ── Topic 路径 ─────────────────────────────────────────────

    @property
    def topic_dir(self) -> Path:
        if not self._topic:
            raise ValueError("PathManager: topic_dir 未设置")
        return self._topic

    @property
    def config_yaml(self) -> Path:
        return self.topic_dir / "config.yaml"

    @property
    def fsm_state_yaml(self) -> Path:
        return self.topic_dir / "fsm_state.yaml"

    @property
    def idea_registry_yaml(self) -> Path:
        return self.topic_dir / "idea_registry.yaml"

    @property
    def audit_log_yaml(self) -> Path:
        return self.topic_dir / "audit_log.yaml"

    @property
    def context_md(self) -> Path:
        return self.topic_dir / "context.md"

    @property
    def topic_spec(self) -> Path:
        return self.topic_dir / "topic_spec.md"

    @property
    def baselines_md(self) -> Path:
        return self.topic_dir / "baselines.md"

    @property
    def datasets_md(self) -> Path:
        return self.topic_dir / "datasets.md"

    @property
    def metrics_md(self) -> Path:
        return self.topic_dir / "metrics.md"

    @property
    def survey_dir(self) -> Path:
        return self.topic_dir / "survey"

    @property
    def survey_md(self) -> Path:
        return self.survey_dir / "survey.md"

    @property
    def survey_progress(self) -> Path:
        return self.survey_dir / "progress.yaml"

    @property
    def paper_list_yaml(self) -> Path:
        return self.survey_dir / "paper_list.yaml"

    @property
    def leaderboard_md(self) -> Path:
        return self.survey_dir / "leaderboard.md"

    @property
    def repos_summary_md(self) -> Path:
        return self.survey_dir / "repos_summary.md"

    @property
    def survey_index_yaml(self) -> Path:
        return self.survey_dir / "index.yaml"

    @property
    def eda_dir(self) -> Path:
        return self.topic_dir / "eda"

    @property
    def eda_venv_dir(self) -> Path:
        return self.eda_dir / ".venv"

    @property
    def eda_plots_dir(self) -> Path:
        return self.eda_dir / "plots"

    @property
    def eda_scripts_dir(self) -> Path:
        return self.eda_dir / "scripts"

    @property
    def eda_guide_md(self) -> Path:
        return self.eda_dir / "eda_guide.md"

    @property
    def eda_report_md(self) -> Path:
        return self.eda_dir / "eda_report.md"

    @property
    def data_dir(self) -> Path:
        return self.root / "shared" / "data"

    @property
    def ideas_dir(self) -> Path:
        return self.topic_dir / "ideas"

    @property
    def phase_logs_dir(self) -> Path:
        return self.topic_dir / "phase_logs"

    @property
    def idea_graph_yaml(self) -> Path:
        return self.ideas_dir / "idea_graph.yaml"

    # ── 参数化路径 ─────────────────────────────────────────────

    def idea_dir(self, idea_id: str) -> Path | None:
        if not self.ideas_dir.exists():
            return None
        # idea_id 可能是 "T001-I001"（tree 格式）或 "I001"
        # 目录名可能是 "T001_I001_xxx" 或 "I001_xxx"
        normalized = idea_id.replace("-", "_")
        for d in sorted(self.ideas_dir.iterdir()):
            if d.is_dir() and (
                d.name.startswith(idea_id)
                or d.name.startswith(normalized)
                or f"_{idea_id}_" in d.name
                or f"_{normalized}_" in d.name
                or d.name.endswith(f"_{idea_id}")
                or d.name.endswith(f"_{normalized}")
            ):
                return d
        return None

    def idea_proposal(self, idea_id: str) -> Path | None:
        d = self.idea_dir(idea_id)
        return d / "proposal.md" if d else None

    def idea_refinement_dir(self, idea_id: str) -> Path | None:
        d = self.idea_dir(idea_id)
        return d / "refinement" if d else None

    def idea_experiment_plan(self, idea_id: str) -> Path | None:
        d = self.idea_dir(idea_id)
        return d / "experiment_plan.md" if d else None

    def idea_code_reference(self, idea_id: str) -> Path | None:
        d = self.idea_dir(idea_id)
        return d / "code_reference.md" if d else None

    def idea_src_dir(self, idea_id: str) -> Path | None:
        d = self.idea_dir(idea_id)
        return d / "src" if d else None

    def idea_venv_dir(self, idea_id: str) -> Path | None:
        src = self.idea_src_dir(idea_id)
        return src / ".venv" if src else None

    def idea_results_dir(self, idea_id: str) -> Path | None:
        d = self.idea_dir(idea_id)
        return d / "results" if d else None

    def idea_analysis(self, idea_id: str) -> Path | None:
        d = self.idea_dir(idea_id)
        return d / "analysis.md" if d else None

    def idea_conclusion(self, idea_id: str) -> Path | None:
        d = self.idea_dir(idea_id)
        return d / "conclusion.md" if d else None

    def idea_experiment_results(self, idea_id: str) -> Path | None:
        d = self.idea_dir(idea_id)
        return d / "experiment_results.md" if d else None

    def step_dir(self, idea_id: str, step_id: str) -> Path | None:
        results = self.idea_results_dir(idea_id)
        if results and results.exists():
            for d in sorted(results.iterdir()):
                if d.is_dir() and d.name.startswith(step_id):
                    return d
        return None

    def version_dir(self, idea_id: str, step_id: str, version: int) -> Path | None:
        sd = self.step_dir(idea_id, step_id)
        return sd / f"V{version}" if sd else None

    def phase_log_dir(self, phase: str, idea_id: str = "") -> Path:
        name = f"{phase}_{idea_id}" if idea_id else phase
        return self.phase_logs_dir / name

    # ── 发现方法（从 orchestrator 移来）───────────────────────

    def find_latest_topic(self) -> Path | None:
        if not self.topics_dir.exists():
            return None
        topic_dirs = sorted(
            d for d in self.topics_dir.iterdir()
            if d.is_dir() and d.name.startswith("T")
        )
        return topic_dirs[-1] if topic_dirs else None

    def list_idea_ids(self) -> list[str]:
        if not self.ideas_dir.exists():
            return []
        ids = []
        for d in sorted(self.ideas_dir.iterdir()):
            if not d.is_dir():
                continue
            match = re.search(r"(I\d+)", d.name)
            if match:
                ids.append(match.group(1))
        return ids

    # ── 工具方法 ───────────────────────────────────────────────

    def ensure_dir(self, path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_parent(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def is_within_project(self, path: str | Path) -> bool:
        return Path(path).resolve().is_relative_to(self.root.resolve())
