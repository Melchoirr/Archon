"""上下文组装器：每阶段自动注入必需上下文 + 支持跨引用"""
import os
import logging

logger = logging.getLogger(__name__)

# 每阶段注入规则：phase -> 需要注入的文件列表（相对于 topic_dir）
PHASE_CONTEXT_RULES = {
    "elaborate": [],  # 只需 topic title/description
    "survey": ["context.md"],
    "ideation": ["context.md", "survey/survey.md", "baselines.md"],
    "refine": ["survey/survey.md"],  # + proposal.md (idea-specific)
    "code_reference": [],  # + refinement/*.md (idea-specific)
    "code": [],  # + refinement/*.md, experiment_plan.md (idea-specific)
    "experiment": [],  # + experiment_plan.md, src/structure.md (idea-specific)
    "analyze": [],  # + results, expectations (idea-specific)
    "conclude": [],  # + 全链路摘要 (idea-specific)
}

# Idea-specific 注入规则
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
}

MAX_FILE_SIZE = 4000  # 单文件最大注入字符数，超过则截断


class ContextManager:
    def __init__(self, topic_dir: str, project_root: str = None, kb_mgr=None):
        self.topic_dir = topic_dir
        self.project_root = project_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.kb_mgr = kb_mgr

    def _read_file_safe(self, path: str, max_chars: int = MAX_FILE_SIZE) -> str:
        """安全读取文件，截断过长内容"""
        if not os.path.exists(path):
            return ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) > max_chars:
                content = content[:max_chars] + f"\n\n... [截断，共 {len(content)} 字符]"
            return content
        except Exception as e:
            logger.warning(f"Failed to read {path}: {e}")
            return ""

    def _idea_dir(self, idea_id: str) -> str:
        """获取 idea 目录路径"""
        ideas_dir = os.path.join(self.topic_dir, "ideas")
        if not os.path.exists(ideas_dir):
            return ""
        for d in os.listdir(ideas_dir):
            if d.startswith(idea_id):
                return os.path.join(ideas_dir, d)
        return ""

    def _collect_topic_files(self, phase: str) -> list:
        """收集 topic 级别的上下文文件"""
        sections = []
        for rel_path in PHASE_CONTEXT_RULES.get(phase, []):
            full_path = os.path.join(self.topic_dir, rel_path)
            content = self._read_file_safe(full_path)
            if content:
                sections.append(f"## {rel_path}\n{content}")
        return sections

    def _collect_idea_files(self, phase: str, idea_id: str) -> list:
        """收集 idea 级别的上下文文件"""
        sections = []
        idea_dir = self._idea_dir(idea_id)
        if not idea_dir:
            return sections
        for rel_path in IDEA_CONTEXT_RULES.get(phase, []):
            full_path = os.path.join(idea_dir, rel_path)
            content = self._read_file_safe(full_path)
            if content:
                sections.append(f"## {os.path.basename(rel_path)}\n{content}")
        return sections

    def _collect_global_files(self, phase: str) -> list:
        """收集全局文件"""
        sections = []
        for rel_path in GLOBAL_CONTEXT_RULES.get(phase, []):
            full_path = os.path.join(self.project_root, rel_path)
            content = self._read_file_safe(full_path)
            if content:
                sections.append(f"## {rel_path}\n{content}")
        return sections

    def _find_topic_path(self, topics_dir: str, topic_id: str) -> str:
        """按 topic_id 前缀匹配目录"""
        if not os.path.exists(topics_dir):
            return ""
        for d in os.listdir(topics_dir):
            if d.startswith(topic_id):
                return os.path.join(topics_dir, d)
        return ""

    def _collect_idea_from_topic(self, sections: list, topic_path: str, idea_id: str, label: str):
        """从指定 topic 读取 idea 文档（conclusion 或 analysis）"""
        ideas_path = os.path.join(topic_path, "ideas")
        if not os.path.exists(ideas_path):
            return
        for idea_d in os.listdir(ideas_path):
            if idea_d.startswith(idea_id):
                idea_path = os.path.join(ideas_path, idea_d)
                for fname in ["conclusion.md", "analysis.md"]:
                    content = self._read_file_safe(os.path.join(idea_path, fname))
                    if content:
                        sections.append(f"## 参考 Idea {label} - {fname}\n{content}")
                        break

    def _collect_ref_ideas(self, ref_ideas: list) -> list:
        """收集引用 idea 的结论和经验。支持格式：T001-I001（精确）、T001（该 topic 下全部）、I001（当前 topic）"""
        sections = []
        if not ref_ideas:
            return sections
        topics_dir = os.path.dirname(self.topic_dir)

        for ref in ref_ideas:
            if "-I" in ref:
                # T001-I001 格式：精确引用
                topic_id, idea_id = ref.split("-", 1)
                topic_path = self._find_topic_path(topics_dir, topic_id)
                if topic_path:
                    self._collect_idea_from_topic(sections, topic_path, idea_id, ref)
            elif ref.startswith("T"):
                # T001 格式：引用该 topic 下所有 idea
                topic_path = self._find_topic_path(topics_dir, ref)
                if topic_path:
                    ideas_path = os.path.join(topic_path, "ideas")
                    if os.path.exists(ideas_path):
                        for idea_d in sorted(os.listdir(ideas_path)):
                            if idea_d.startswith("I") and os.path.isdir(os.path.join(ideas_path, idea_d)):
                                idea_id = idea_d.split("_")[0]
                                self._collect_idea_from_topic(sections, topic_path, idea_id, f"{ref}-{idea_id}")
            else:
                # I001 格式：当前 topic 内引用（向后兼容）
                self._collect_idea_from_topic(sections, self.topic_dir, ref, ref)
        return sections

    def _collect_ref_topics(self, ref_topics: list) -> list:
        """收集引用 topic 的上下文"""
        sections = []
        if not ref_topics:
            return sections
        topics_dir = os.path.dirname(self.topic_dir)
        if not os.path.exists(topics_dir):
            return sections
        for topic_d in os.listdir(topics_dir):
            for ref_id in ref_topics:
                if topic_d.startswith(ref_id):
                    topic_path = os.path.join(topics_dir, topic_d)
                    for fname in ["context.md", "survey/index.md"]:
                        content = self._read_file_safe(os.path.join(topic_path, fname))
                        if content:
                            sections.append(f"## 参考 Topic {ref_id} - {fname}\n{content}")
        return sections

    def build_context(
        self,
        phase: str,
        idea_id: str = None,
        ref_ideas: list = None,
        ref_topics: list = None,
        max_tokens: int = 8000,
    ) -> str:
        """根据阶段和参数，组装上下文字符串"""
        sections = []

        # 1. Topic 级别文件
        sections.extend(self._collect_topic_files(phase))

        # 2. Idea 级别文件
        if idea_id:
            sections.extend(self._collect_idea_files(phase, idea_id))

        # 3. 全局文件
        sections.extend(self._collect_global_files(phase))

        # 4. 跨 idea 引用
        if ref_ideas:
            sections.extend(self._collect_ref_ideas(ref_ideas))

        # 5. 跨 topic 引用
        if ref_topics:
            sections.extend(self._collect_ref_topics(ref_topics))

        if not sections:
            return ""

        context = "# 上下文参考\n\n" + "\n\n---\n\n".join(sections)

        # 截断到最大 token 估算
        max_chars = max_tokens * 2  # 粗略估算
        if len(context) > max_chars:
            context = context[:max_chars] + "\n\n... [上下文截断]"

        return context
