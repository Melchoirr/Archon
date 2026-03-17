"""研究树服务 — 基于 Pydantic 模型的类型安全 CRUD"""

import re
import threading
import yaml
from datetime import datetime

from shared.models.research_tree import (
    ResearchTree, Idea, Score, IdeaPhases,
    ExperimentStep, Iteration, Relationship,
    ElaborateState, SurveyState,
)
from shared.models.enums import IdeaCategory, PhaseState, RelationType
from shared.paths import PathManager


class ResearchTreeService:
    """线程安全的研究树 CRUD 服务，所有读写通过 Pydantic 模型校验。"""

    def __init__(self, paths: PathManager):
        self._paths = paths
        self._lock = threading.Lock()

    # ── 核心读写 ──────────────────────────────────────────────

    def _load_unlocked(self) -> ResearchTree:
        """内部加载，调用方需持有 self._lock。"""
        path = self._paths.tree_yaml
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return ResearchTree.model_validate(raw)

    def _save_unlocked(self, tree: ResearchTree):
        """内部保存，调用方需持有 self._lock。"""
        # mode="json" 确保 StrEnum 序列化为纯字符串而非 Python 对象
        data = tree.model_dump(mode="json")
        path = self._paths.tree_yaml
        self._paths.ensure_parent(path)
        path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def load(self) -> ResearchTree:
        """加载并校验研究树。文件不存在或格式错误时抛异常。"""
        with self._lock:
            return self._load_unlocked()

    def save(self, tree: ResearchTree):
        """校验并保存研究树。"""
        with self._lock:
            self._save_unlocked(tree)

    # ── 工具函数（供 agent 调用）─────────────────────────────

    def read_tree(self) -> str:
        """读取完整研究树（JSON 字符串）"""
        return self.load().model_dump_json(indent=2)

    def update_idea_phase(self, idea_id: str, phase: str, status: str) -> str:
        """更新指定 idea 的某个阶段状态（立即校验）"""
        validated_status = PhaseState(status)  # 非法值立即报 ValueError
        with self._lock:
            tree = self._load_unlocked()
            for idea in tree.root.ideas:
                if idea.id == idea_id:
                    if not hasattr(idea.phases, phase):
                        return f"Unknown phase '{phase}'. Valid: refinement/code_reference/coding/experiment/analysis/conclusion"
                    setattr(idea.phases, phase, validated_status)
                    self._save_unlocked(tree)
                    return f"Updated {idea_id}.phases.{phase} = {status}"
        return f"Idea {idea_id} not found"

    def update_idea_status(self, idea_id: str, status: str) -> str:
        """更新指定 idea 的整体状态"""
        from shared.models.enums import IdeaStatus
        validated = IdeaStatus(status)  # 非法值立即报 ValueError
        with self._lock:
            tree = self._load_unlocked()
            for idea in tree.root.ideas:
                if idea.id == idea_id:
                    idea.status = validated
                    self._save_unlocked(tree)
                    return f"Updated {idea_id}.status = {status}"
        return f"Idea {idea_id} not found"

    def update_survey_status(self, status: str, rounds: int = None) -> str:
        """更新 survey 阶段状态"""
        validated = PhaseState(status)
        with self._lock:
            tree = self._load_unlocked()
            tree.root.survey.status = validated
            if rounds is not None:
                tree.root.survey.rounds = rounds
            self._save_unlocked(tree)
        return f"Updated survey.status = {status}"

    def update_elaborate_status(self, status: str) -> str:
        """更新 elaborate 阶段状态"""
        validated = PhaseState(status)
        with self._lock:
            tree = self._load_unlocked()
            tree.root.elaborate.status = validated
            self._save_unlocked(tree)
        return f"Updated elaborate.status = {status}"

    def add_idea(self, idea_id: str, title: str, category: str,
                 brief: str = "") -> str:
        """向研究树添加一个新 idea"""
        with self._lock:
            tree = self._load_unlocked()
            idea = Idea(
                id=idea_id,
                title=title,
                category=IdeaCategory(category),
                brief=brief or _make_brief(title),
                created_at=datetime.now().isoformat(),
            )
            tree.root.ideas.append(idea)
            self._save_unlocked(tree)
        return f"Added idea {idea_id}: {title}"

    def update_idea_scores(self, idea_id: str, scores: dict) -> str:
        """更新指定 idea 的评分（Score 模型自动校验范围并计算 composite）"""
        validated = Score.model_validate(scores)
        with self._lock:
            tree = self._load_unlocked()
            for idea in tree.root.ideas:
                if idea.id == idea_id:
                    idea.scores = validated
                    self._save_unlocked(tree)
                    return f"Updated scores for {idea_id}: composite={validated.composite}"
        return f"Idea {idea_id} not found"

    def add_experiment_step(self, idea_id: str, step_name: str,
                            max_iter: int = 3) -> str:
        """注册一个实验步骤到 idea"""
        with self._lock:
            tree = self._load_unlocked()
            for idea in tree.root.ideas:
                if idea.id == idea_id:
                    step_id = self._next_step_id(idea)
                    iterations = [
                        Iteration(version=v + 1)
                        for v in range(max_iter)
                    ]
                    step = ExperimentStep(
                        step_id=step_id,
                        name=step_name,
                        max_iter=max_iter,
                        iterations=iterations,
                    )
                    idea.experiment_steps.append(step)
                    self._save_unlocked(tree)
                    return f"Added step {step_id} ({step_name}) to {idea_id} with {max_iter} iterations"
        return f"Idea {idea_id} not found"

    def update_iteration(self, idea_id: str, step_id: str, version: int,
                         status: str, config_diff: str = None) -> str:
        """更新实验迭代状态"""
        with self._lock:
            tree = self._load_unlocked()
            for idea in tree.root.ideas:
                if idea.id == idea_id:
                    for step in idea.experiment_steps:
                        if step.step_id == step_id:
                            for it in step.iterations:
                                if it.version == version:
                                    it.status = PhaseState(status)
                                    if config_diff:
                                        it.config_diff = config_diff
                                    all_done = all(
                                        i.status in (PhaseState.completed, PhaseState.skipped)
                                        for i in step.iterations
                                    )
                                    if all_done:
                                        step.status = PhaseState.completed
                                    elif any(i.status == PhaseState.running for i in step.iterations):
                                        step.status = PhaseState.running
                                    self._save_unlocked(tree)
                                    return f"Updated {idea_id}/{step_id}/V{version} -> {status}"
                            return f"Version {version} not found in {step_id}"
                    return f"Step {step_id} not found in {idea_id}"
        return f"Idea {idea_id} not found"

    def add_relationship(self, idea_a: str, idea_b: str, rel_type: str) -> str:
        """在研究树中记录 idea 关系"""
        with self._lock:
            tree = self._load_unlocked()
            for idea in tree.root.ideas:
                if idea.id == idea_a:
                    idea.relationships.append(
                        Relationship(target=idea_b, type=RelationType(rel_type))
                    )
                    self._save_unlocked(tree)
                    return f"Added relationship: {idea_a} --{rel_type}--> {idea_b}"
        return f"Idea {idea_a} not found"

    # ── ID 生成 ───────────────────────────────────────────────

    def next_topic_id(self) -> str:
        """生成下一个 topic 编号 (T001, T002, ...)"""
        topics_dir = self._paths.topics_dir
        if not topics_dir.exists():
            return "T001"
        nums = []
        for d in topics_dir.iterdir():
            if d.is_dir():
                match = re.match(r"T(\d+)", d.name)
                if match:
                    nums.append(int(match.group(1)))
        return f"T{max(nums) + 1:03d}" if nums else "T001"

    def next_idea_id(self) -> str:
        """生成下一个 idea 编号（原子操作）"""
        with self._lock:
            path = self._paths.tree_yaml
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            tree = ResearchTree.model_validate(raw)
            nums = []
            for idea in tree.root.ideas:
                match = re.search(r"I(\d+)", idea.id)
                if match:
                    nums.append(int(match.group(1)))
            return f"I{max(nums) + 1:03d}" if nums else "I001"

    def _next_step_id(self, idea: Idea) -> str:
        """生成下一个实验步骤编号"""
        nums = []
        for s in idea.experiment_steps:
            match = re.match(r"S(\d+)", s.step_id)
            if match:
                nums.append(int(match.group(1)))
        return f"S{max(nums) + 1:02d}" if nums else "S01"


def _make_brief(title: str) -> str:
    """从标题生成简短标识"""
    words = re.findall(r'[A-Z][a-z]*|[a-z]+', title)
    if len(words) <= 3:
        return "_".join(w.lower() for w in words)
    caps = [w[0] for w in title.split() if w[0].isupper()]
    if caps:
        return "".join(caps).lower()
    return "_".join(words[:3]).lower()


# ── 模块级工具函数（供 agent register_tool 使用）──────────────
# 这些函数通过惰性创建的默认 service 实例委托到 ResearchTreeService。
# Agent 注册它们为 LLM 可调用的工具。

_default_service: ResearchTreeService | None = None


def _get_default_service() -> ResearchTreeService:
    """惰性创建默认 service，自动查找最新 topic"""
    global _default_service
    if _default_service is None:
        import os
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        paths = PathManager(project_root)
        topic = paths.find_latest_topic()
        if topic:
            paths = PathManager(project_root, topic)
        _default_service = ResearchTreeService(paths)
    return _default_service


def reset_default_service(paths: PathManager = None):
    """重置默认 service（orchestrator 设置 topic 后调用）"""
    global _default_service
    if paths:
        _default_service = ResearchTreeService(paths)
    else:
        _default_service = None


def read_tree(**kwargs) -> str:
    return _get_default_service().read_tree()


def update_idea_phase(idea_id: str, phase: str, status: str, **kwargs) -> str:
    return _get_default_service().update_idea_phase(idea_id, phase, status)


def update_idea_status(idea_id: str, status: str, **kwargs) -> str:
    return _get_default_service().update_idea_status(idea_id, status)


def update_survey_status(status: str, rounds: int = None, **kwargs) -> str:
    return _get_default_service().update_survey_status(status, rounds)


def update_elaborate_status(status: str, **kwargs) -> str:
    return _get_default_service().update_elaborate_status(status)


def add_idea_to_tree(idea_id: str, title: str, category: str,
                     brief: str = "", **kwargs) -> str:
    return _get_default_service().add_idea(idea_id, title, category, brief)


def add_experiment_step(idea_id: str, step_name: str,
                        max_iter: int = 3, **kwargs) -> str:
    return _get_default_service().add_experiment_step(idea_id, step_name, max_iter)


def update_iteration(idea_id: str, step_id: str, version: int,
                     status: str, config_diff: str = None, **kwargs) -> str:
    return _get_default_service().update_iteration(idea_id, step_id, version, status, config_diff)


def add_idea_relationship(idea_a: str, idea_b: str, rel_type: str, **kwargs) -> str:
    return _get_default_service().add_relationship(idea_a, idea_b, rel_type)


def next_topic_id(**kwargs) -> str:
    return _get_default_service().next_topic_id()


def next_idea_id(**kwargs) -> str:
    return _get_default_service().next_idea_id()
