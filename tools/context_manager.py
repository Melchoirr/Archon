"""上下文组装器：每阶段自动注入必需上下文 + 支持跨引用"""
import os
import logging
from pathlib import Path

from shared.paths import PathManager

logger = logging.getLogger(__name__)

# 每阶段注入规则：phase -> 需要注入的文件列表（相对于 topic_dir）
PHASE_CONTEXT_RULES = {
    "elaborate": [],
    "survey": ["context.md"],
    "ideation": ["context.md", "survey/survey.md", "baselines.md",
                 "datasets.md", "metrics.md", "eda/eda_report.md"],
    "refine": ["survey/survey.md", "repos_summary.md", "datasets.md", "metrics.md",
               "eda/eda_report.md"],
    "code_reference": ["repos_summary.md"],
    "code": ["datasets.md"],
    "experiment": ["datasets.md"],
    "analyze": ["baselines.md", "survey/leaderboard.md"],
    "conclude": [],
}

# Idea-specific 注入规则（相对于 idea_dir）
IDEA_CONTEXT_RULES = {
    "refine": ["proposal.md"],
    "code_reference": ["refinement/theory.md", "refinement/model_modular.md", "refinement/model_complete.md"],
    "code": ["refinement/theory.md", "refinement/model_modular.md", "refinement/model_complete.md", "experiment_plan.md"],
    "experiment": ["experiment_plan.md", "src/structure.md"],
    "analyze": ["experiment_plan.md"],
    "conclude": ["proposal.md", "experiment_plan.md", "analysis.md"],
}

# 全局文件注入（相对于项目根目录）
GLOBAL_CONTEXT_RULES = {
    "ideation": ["memory/failed_ideas.md"],
    "code": ["shared/templates/experiment_infrastructure.md"],
    "experiment": ["shared/templates/experiment_infrastructure.md"],
}

MAX_FILE_SIZE = 40000


class ContextManager:
    def __init__(self, paths: PathManager, kb_mgr=None):
        self.paths = paths
        self.kb_mgr = kb_mgr

    def _read_file_safe(self, path, max_chars: int = MAX_FILE_SIZE) -> str:
        """安全读取文件，截断过长内容"""
        p = str(path)
        if not os.path.exists(p):
            return ""
        try:
            with open(p, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n\n... [截断，共 {len(content)} 字符]"
            return content
        except Exception as e:
            logger.warning(f"Failed to read {p}: {e}")
            return ""

    def _collect_topic_files(self, phase: str) -> list:
        """收集 topic 级别的上下文文件"""
        sections = []
        for rel_path in PHASE_CONTEXT_RULES.get(phase, []):
            full_path = self.paths.topic_dir / rel_path
            content = self._read_file_safe(full_path)
            if content:
                sections.append(f"## {rel_path}\n{content}")
        return sections

    def _collect_idea_files(self, phase: str, idea_id: str) -> list:
        """收集 idea 级别的上下文文件"""
        sections = []
        idea_dir = self.paths.idea_dir(idea_id)
        if not idea_dir:
            return sections
        for rel_path in IDEA_CONTEXT_RULES.get(phase, []):
            full_path = idea_dir / rel_path
            content = self._read_file_safe(full_path)
            if content:
                sections.append(f"## {os.path.basename(rel_path)}\n{content}")
        return sections

    def _collect_global_files(self, phase: str) -> list:
        """收集全局文件"""
        sections = []
        for rel_path in GLOBAL_CONTEXT_RULES.get(phase, []):
            full_path = self.paths.root / rel_path
            content = self._read_file_safe(full_path)
            if content:
                sections.append(f"## {rel_path}\n{content}")
        return sections

    def _find_topic_path(self, topic_id: str) -> str:
        """按 topic_id 前缀匹配目录"""
        topics_dir = self.paths.topics_dir
        if not topics_dir.exists():
            return ""
        for d in topics_dir.iterdir():
            if d.is_dir() and d.name.startswith(topic_id):
                return str(d)
        return ""

    def _collect_idea_from_topic(self, sections: list, topic_path: str | Path, idea_id: str, label: str):
        """从指定 topic 读取 idea 文档（conclusion 或 analysis）"""
        ideas_path = Path(topic_path) / "ideas"
        if not ideas_path.exists():
            return
        for idea_d in sorted(ideas_path.iterdir()):
            if idea_d.is_dir() and idea_d.name.startswith(idea_id):
                for fname in ["conclusion.md", "analysis.md"]:
                    content = self._read_file_safe(idea_d / fname)
                    if content:
                        sections.append(f"## 参考 Idea {label} - {fname}\n{content}")
                        break

    def _collect_ref_ideas(self, ref_ideas: list) -> list:
        """收集引用 idea 的结论和经验"""
        sections = []
        if not ref_ideas:
            return sections

        for ref in ref_ideas:
            if "-I" in ref:
                topic_id, idea_id = ref.split("-", 1)
                topic_path = self._find_topic_path(topic_id)
                if topic_path:
                    self._collect_idea_from_topic(sections, topic_path, idea_id, ref)
            elif ref.startswith("T"):
                topic_path = self._find_topic_path(ref)
                if topic_path:
                    ideas_path = Path(topic_path) / "ideas"
                    if ideas_path.exists():
                        for idea_d in sorted(ideas_path.iterdir()):
                            if idea_d.is_dir() and idea_d.name.startswith("I"):
                                idea_id = idea_d.name.split("_")[0]
                                self._collect_idea_from_topic(sections, topic_path, idea_id, f"{ref}-{idea_id}")
            else:
                self._collect_idea_from_topic(sections, str(self.paths.topic_dir), ref, ref)
        return sections

    def _collect_ref_topics(self, ref_topics: list) -> list:
        """收集引用 topic 的上下文"""
        sections = []
        if not ref_topics:
            return sections
        topics_dir = self.paths.topics_dir
        if not topics_dir.exists():
            return sections
        for topic_d in topics_dir.iterdir():
            if not topic_d.is_dir():
                continue
            for ref_id in ref_topics:
                if topic_d.name.startswith(ref_id):
                    for fname in ["context.md", "survey/index.md"]:
                        content = self._read_file_safe(topic_d / fname)
                        if content:
                            sections.append(f"## 参考 Topic {ref_id} - {fname}\n{content}")
        return sections

    def build_context(
        self,
        phase: str,
        idea_id: str = None,
        ref_ideas: list = None,
        ref_topics: list = None,
        max_tokens: int = 30000,
    ) -> str:
        """根据阶段和参数，组装上下文字符串"""
        sections = []

        sections.extend(self._collect_topic_files(phase))

        if idea_id:
            sections.extend(self._collect_idea_files(phase, idea_id))

        sections.extend(self._collect_global_files(phase))

        if ref_ideas:
            sections.extend(self._collect_ref_ideas(ref_ideas))

        if ref_topics:
            sections.extend(self._collect_ref_topics(ref_topics))

        if not sections:
            return ""

        context = "# 上下文参考\n\n" + "\n\n---\n\n".join(sections)

        max_chars = max_tokens * 2
        if len(context) > max_chars:
            context = context[:max_chars] + "\n\n... [上下文截断]"

        return context
