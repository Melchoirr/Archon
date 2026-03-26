#!/usr/bin/env python
"""迁移脚本：research_tree.yaml + fsm_state.yaml → idea_registry.yaml + 精简 fsm_state.yaml + audit_log.yaml

用法：
    python scripts/migrate_tree_to_registry.py                    # 迁移所有 topics/T*/
    python scripts/migrate_tree_to_registry.py topics/T001_xxx    # 迁移指定 topic
"""

import os
import sys
import re
import yaml
from pathlib import Path
from datetime import datetime

# 项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.models.idea_registry import (
    IdeaRegistry, IdeaEntry, TopicMeta, Score, Relationship,
)
from shared.models.enums import IdeaCategory, IdeaStatus, RelationType
from shared.models.fsm import FSMSnapshot, IdeaFSMState
from shared.models.audit import TransitionRecord


def migrate_topic(topic_dir: Path):
    """迁移单个 topic 目录"""
    tree_path = topic_dir / "research_tree.yaml"
    fsm_path = topic_dir / "fsm_state.yaml"
    registry_path = topic_dir / "idea_registry.yaml"
    audit_path = topic_dir / "audit_log.yaml"

    print(f"\n{'='*60}")
    print(f"  Migrating: {topic_dir.name}")
    print(f"{'='*60}")

    # ── 1. research_tree.yaml → idea_registry.yaml ──────────

    if tree_path.exists():
        raw_tree = yaml.safe_load(tree_path.read_text(encoding="utf-8")) or {}
        root = raw_tree.get("root", raw_tree)

        topic_meta = TopicMeta(
            topic_id=root.get("topic_id", ""),
            topic_brief=root.get("topic_brief", ""),
            topic=root.get("topic", ""),
            description=root.get("description", ""),
        )

        ideas = []
        for idea_raw in root.get("ideas", []):
            # 迁移 scores
            scores = None
            if idea_raw.get("scores"):
                s = idea_raw["scores"]
                scores = Score(
                    novelty=s.get("novelty", 3),
                    significance=s.get("significance", 3),
                    feasibility=s.get("feasibility", 3),
                    alignment=s.get("alignment", 3),
                    rank=s.get("rank"),
                )

            # 迁移 relationships
            rels = []
            for r in idea_raw.get("relationships", []):
                try:
                    rels.append(Relationship(
                        target=r["target"],
                        type=RelationType(r["type"]),
                    ))
                except (KeyError, ValueError):
                    pass

            # 迁移 category
            cat_str = idea_raw.get("category", "architecture")
            try:
                cat = IdeaCategory(cat_str)
            except ValueError:
                cat = IdeaCategory.architecture

            # 迁移 status
            status_str = idea_raw.get("status", "proposed")
            try:
                status = IdeaStatus(status_str)
            except ValueError:
                status = IdeaStatus.proposed

            ideas.append(IdeaEntry(
                id=idea_raw.get("id", ""),
                title=idea_raw.get("title", ""),
                brief=idea_raw.get("brief", ""),
                category=cat,
                status=status,
                created_at=idea_raw.get("created_at", ""),
                scores=scores,
                relationships=rels,
            ))

        registry = IdeaRegistry(topic=topic_meta, ideas=ideas)
        registry_data = registry.model_dump(mode="json")
        registry_path.write_text(
            yaml.dump(registry_data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        print(f"  [OK] idea_registry.yaml — {len(ideas)} ideas")
    else:
        # 无 research_tree.yaml 时，从文件系统重建
        print(f"  [INFO] No research_tree.yaml — rebuilding from filesystem")
        _rebuild_registry_from_fs(topic_dir, registry_path)

    # ── 2. fsm_state.yaml → 精简 fsm_state.yaml + audit_log.yaml ──

    if fsm_path.exists():
        fsm_text = fsm_path.read_text(encoding="utf-8")
        # 清除 !!python/object/apply:... 标签（旧版序列化 bug 遗留）
        fsm_text = re.sub(r'!!python/object/apply:\S+\s*\n\s*-\s*', '', fsm_text)
        raw_fsm = yaml.safe_load(fsm_text) or {}

        # 提取 transition_history → audit_log.yaml
        history = raw_fsm.pop("transition_history", [])
        audit_records = []
        for rec in history:
            # 从 decision_snapshot 生成 verdict_summary
            summary = ""
            ds = rec.get("decision_snapshot")
            if ds and isinstance(ds, dict):
                verdict = ds.get("verdict", "")
                if isinstance(verdict, str):
                    parts = [verdict]
                else:
                    parts = [str(verdict)]
                if "coverage_score" in ds:
                    parts.append(f"coverage={ds['coverage_score']}")
                    gaps = ds.get("gap_areas", [])
                    if gaps:
                        parts.append(f"gaps: {', '.join(str(g) for g in gaps[:3])}")
                elif "confidence" in ds:
                    parts.append(f"confidence={ds['confidence']}")
                    if "expectations_met_ratio" in ds:
                        parts.append(f"met_ratio={ds['expectations_met_ratio']}")
                elif "tests_passed" in ds:
                    parts.append(f"{ds['tests_passed']}/{ds.get('tests_total', '?')} passed")
                elif "novelty_score" in ds:
                    parts.append(f"novelty={ds['novelty_score']}")
                summary = ", ".join(parts)

            audit_records.append(TransitionRecord(
                timestamp=rec.get("timestamp", ""),
                from_state=rec.get("from_state", ""),
                to_state=rec.get("to_state", ""),
                trigger=rec.get("trigger", ""),
                idea_id=rec.get("idea_id", ""),
                verdict_summary=summary,
            ))

        if audit_records:
            audit_data = {"records": [r.model_dump(mode="json") for r in audit_records]}
            audit_path.write_text(
                yaml.dump(audit_data, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )
            print(f"  [OK] audit_log.yaml — {len(audit_records)} records")

        # 精简 fsm_state.yaml：删除 feedback 和 transition_history
        idea_states = raw_fsm.get("idea_states", {})
        for idea_id, state in idea_states.items():
            if isinstance(state, dict):
                state.pop("feedback", None)

        clean_snapshot = FSMSnapshot(
            schema_version=2,
            topic_state=raw_fsm.get("topic_state", "elaborate"),
            idea_states={
                k: IdeaFSMState(**v) if isinstance(v, dict) else IdeaFSMState()
                for k, v in idea_states.items()
            },
        )
        clean_data = clean_snapshot.model_dump(mode="json")
        fsm_path.write_text(
            yaml.dump(clean_data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )
        lines = len(fsm_path.read_text().splitlines())
        print(f"  [OK] fsm_state.yaml — cleaned to {lines} lines")
    else:
        print(f"  [SKIP] No fsm_state.yaml found")


def _rebuild_registry_from_fs(topic_dir: Path, registry_path: Path):
    """从文件系统和 config 重建 idea_registry.yaml"""
    # 推断 topic 元信息
    topic_id = ""
    topic_brief = ""
    m = re.match(r"(T\d+)_?(.*)", topic_dir.name)
    if m:
        topic_id = m.group(1)
        topic_brief = m.group(2)

    topic_title = topic_brief.replace("_", " ").title()
    # 尝试从 topic_spec.md 获取标题
    spec_path = topic_dir / "topic_spec.md"
    if spec_path.exists():
        for line in spec_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                topic_title = line[2:].strip()
                break

    topic_meta = TopicMeta(
        topic_id=topic_id,
        topic_brief=topic_brief,
        topic=topic_title,
    )

    # 扫描 ideas 目录
    ideas_dir = topic_dir / "ideas"
    ideas = []
    if ideas_dir.exists():
        for d in sorted(ideas_dir.iterdir()):
            if not d.is_dir():
                continue
            m = re.match(r"(I\d+)_?(.*)", d.name)
            if not m:
                continue
            idea_id = m.group(1)
            brief = m.group(2)

            # 从 proposal.md 提取标题
            title = brief.replace("_", " ").title()
            proposal_path = d / "proposal.md"
            if proposal_path.exists():
                lines = proposal_path.read_text(encoding="utf-8").splitlines()
                for line in lines:
                    if line.startswith("**") and "**" in line[2:]:
                        # 提取 **Title** 格式
                        title = line.strip("*").strip()
                        break

            ideas.append(IdeaEntry(
                id=idea_id,
                title=title,
                brief=brief,
                category=IdeaCategory.architecture,
                status=IdeaStatus.active,
            ))

    registry = IdeaRegistry(topic=topic_meta, ideas=ideas)
    registry_data = registry.model_dump(mode="json")
    registry_path.write_text(
        yaml.dump(registry_data, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"  [OK] idea_registry.yaml (rebuilt) — {len(ideas)} ideas")


def main():
    if len(sys.argv) > 1:
        topic_dir = Path(sys.argv[1])
        if not topic_dir.is_absolute():
            topic_dir = PROJECT_ROOT / topic_dir
        if not topic_dir.is_dir():
            print(f"Error: {topic_dir} is not a directory")
            sys.exit(1)
        migrate_topic(topic_dir)
    else:
        topics_dir = PROJECT_ROOT / "topics"
        if not topics_dir.exists():
            print("No topics/ directory found")
            sys.exit(1)
        for d in sorted(topics_dir.iterdir()):
            if d.is_dir() and re.match(r"T\d+", d.name):
                migrate_topic(d)

    print(f"\n{'='*60}")
    print("  Migration complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
