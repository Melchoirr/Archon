"""Idea 注册表服务 — 替代 research_tree 的元数据管理 + 合并 FSM 状态视图"""

import json
import os
import re
import threading

import yaml
from datetime import datetime

from shared.models.idea_registry import (
    IdeaRegistry, IdeaEntry, TopicMeta, Score, Relationship,
)
from shared.models.fsm import FSMSnapshot, IdeaFSMState
from shared.models.enums import IdeaCategory, IdeaStatus, RelationType
from shared.paths import PathManager


class IdeaRegistryService:
    """线程安全的 Idea 注册表 CRUD 服务"""

    def __init__(self, paths: PathManager):
        self._paths = paths
        self._lock = threading.Lock()

    # ── 核心读写 ──────────────────────────────────────────────

    def _load_unlocked(self) -> IdeaRegistry:
        path = self._paths.idea_registry_yaml
        if not path.exists():
            raise FileNotFoundError(f"idea_registry.yaml not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return IdeaRegistry.model_validate(raw)

    def _save_unlocked(self, registry: IdeaRegistry):
        data = registry.model_dump(mode="json")
        path = self._paths.idea_registry_yaml
        self._paths.ensure_parent(path)
        path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

    def load(self) -> IdeaRegistry:
        with self._lock:
            return self._load_unlocked()

    def save(self, registry: IdeaRegistry):
        with self._lock:
            self._save_unlocked(registry)

    def create(self, topic_meta: TopicMeta) -> IdeaRegistry:
        """创建新的空注册表"""
        registry = IdeaRegistry(topic=topic_meta)
        self.save(registry)
        return registry

    # ── 合并视图（替代 read_tree）────────────────────────────

    def read_research_status(self) -> str:
        """合并 idea_registry.yaml + fsm_state.yaml → 统一 JSON 视图"""
        with self._lock:
            registry = self._load_unlocked()

        # 加载 FSM 状态
        fsm_path = self._paths.fsm_state_yaml
        if fsm_path.exists():
            try:
                raw = yaml.safe_load(fsm_path.read_text(encoding="utf-8")) or {}
                snapshot = FSMSnapshot(**raw)
            except Exception:
                snapshot = FSMSnapshot()
        else:
            snapshot = FSMSnapshot()

        # 构建合并视图
        ideas_view = []
        for idea in registry.ideas:
            fsm_state = snapshot.idea_states.get(idea.id, IdeaFSMState())
            entry = {
                "id": idea.id,
                "title": idea.title,
                "brief": idea.brief,
                "category": idea.category,
                "status": idea.status,
                "created_at": idea.created_at,
                "current_phase": fsm_state.current_state,
                "step_id": fsm_state.step_id,
                "version": fsm_state.version,
            }
            if idea.scores:
                entry["scores"] = {
                    "novelty": idea.scores.novelty,
                    "significance": idea.scores.significance,
                    "feasibility": idea.scores.feasibility,
                    "alignment": idea.scores.alignment,
                    "composite": idea.scores.composite,
                    "rank": idea.scores.rank,
                }
            if idea.relationships:
                entry["relationships"] = [
                    {"target": r.target, "type": r.type}
                    for r in idea.relationships
                ]
            ideas_view.append(entry)

        result = {
            "topic": {
                "topic_id": registry.topic.topic_id,
                "topic": registry.topic.topic,
                "topic_brief": registry.topic.topic_brief,
                "status": snapshot.topic_state,
            },
            "ideas": ideas_view,
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    # ── CRUD 工具函数 ────────────────────────────────────────

    def add_idea(self, idea_id: str, title: str, category: str,
                 brief: str = "") -> str:
        with self._lock:
            registry = self._load_unlocked()
            entry = IdeaEntry(
                id=idea_id,
                title=title,
                category=IdeaCategory(category),
                brief=brief or _make_brief(title),
                created_at=datetime.now().isoformat(),
            )
            registry.ideas.append(entry)
            self._save_unlocked(registry)
        return f"Added idea {idea_id}: {title}"

    def update_idea_status(self, idea_id: str, status: str) -> str:
        validated = IdeaStatus(status)
        with self._lock:
            registry = self._load_unlocked()
            for idea in registry.ideas:
                if idea.id == idea_id:
                    idea.status = validated
                    self._save_unlocked(registry)
                    return f"Updated {idea_id}.status = {status}"
        return f"Idea {idea_id} not found"

    def update_idea_scores(self, idea_id: str, scores: dict) -> str:
        validated = Score.model_validate(scores)
        with self._lock:
            registry = self._load_unlocked()
            for idea in registry.ideas:
                if idea.id == idea_id:
                    idea.scores = validated
                    self._save_unlocked(registry)
                    return f"Updated scores for {idea_id}: composite={validated.composite}"
        return f"Idea {idea_id} not found"

    def add_relationship(self, idea_a: str, idea_b: str, rel_type: str) -> str:
        with self._lock:
            registry = self._load_unlocked()
            for idea in registry.ideas:
                if idea.id == idea_a:
                    idea.relationships.append(
                        Relationship(target=idea_b, type=RelationType(rel_type))
                    )
                    self._save_unlocked(registry)
                    return f"Added relationship: {idea_a} --{rel_type}--> {idea_b}"
        return f"Idea {idea_a} not found"

    # ── ID 生成 ───────────────────────────────────────────────

    def next_topic_id(self) -> str:
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
        with self._lock:
            registry = self._load_unlocked()
            nums = []
            for idea in registry.ideas:
                match = re.search(r"I(\d+)", idea.id)
                if match:
                    nums.append(int(match.group(1)))
            return f"I{max(nums) + 1:03d}" if nums else "I001"


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

_default_service: IdeaRegistryService | None = None


def _get_default_service() -> IdeaRegistryService:
    global _default_service
    if _default_service is None:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        paths = PathManager(project_root)
        topic = paths.find_latest_topic()
        if topic:
            paths = PathManager(project_root, topic)
        _default_service = IdeaRegistryService(paths)
    return _default_service


def reset_default_service(paths: PathManager = None):
    global _default_service
    if paths:
        _default_service = IdeaRegistryService(paths)
    else:
        _default_service = None


def read_research_status(**kwargs) -> str:
    return _get_default_service().read_research_status()


def add_idea(idea_id: str, title: str, category: str,
             brief: str = "", **kwargs) -> str:
    return _get_default_service().add_idea(idea_id, title, category, brief)


def update_idea_status(idea_id: str, status: str, **kwargs) -> str:
    return _get_default_service().update_idea_status(idea_id, status)


def update_idea_scores(idea_id: str, scores: dict, **kwargs) -> str:
    return _get_default_service().update_idea_scores(idea_id, scores)


def add_idea_relationship(idea_a: str, idea_b: str, rel_type: str,
                          **kwargs) -> str:
    return _get_default_service().add_relationship(idea_a, idea_b, rel_type)


def next_topic_id(**kwargs) -> str:
    return _get_default_service().next_topic_id()


def next_idea_id(**kwargs) -> str:
    return _get_default_service().next_idea_id()
