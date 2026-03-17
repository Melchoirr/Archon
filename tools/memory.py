"""经验记忆系统：记录和查询研究过程中的经验"""
import json
import os
import yaml
from datetime import datetime


def _load_experiences(memory_dir: str = "memory") -> list:
    experience_log = os.path.join(memory_dir, "experience_log.yaml")
    if not os.path.exists(experience_log):
        return []
    with open(experience_log, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    return data


def _save_experiences(experiences: list, memory_dir: str = "memory"):
    os.makedirs(memory_dir, exist_ok=True)
    experience_log = os.path.join(memory_dir, "experience_log.yaml")
    with open(experience_log, "w", encoding="utf-8") as f:
        yaml.dump(experiences, f, allow_unicode=True, default_flow_style=False)


def query_memory(tags: str = "", phase: str = "", idea_id: str = "",
                  topic_id: str = "", memory_dir: str = "memory") -> str:
    """查询经验记忆。可按 tags、phase、idea_id、topic_id 过滤。"""
    experiences = _load_experiences(memory_dir)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    results = []
    for exp in experiences:
        if phase and exp.get("phase") != phase:
            continue
        if idea_id and exp.get("idea_id") != idea_id:
            continue
        if topic_id and exp.get("topic_id") != topic_id:
            continue
        if tag_list and not set(tag_list).intersection(set(exp.get("tags", []))):
            continue
        results.append(exp)

    if not results:
        return "No matching experiences found."
    return json.dumps(results, indent=2, ensure_ascii=False)


def add_experience(
    idea_id: str = "",
    phase: str = "",
    type: str = "insight",
    summary: str = "",
    details: str = "",
    tags: str = "",
    topic_id: str = "",
    memory_dir: str = "memory",
) -> str:
    """添加经验记录。
    type: insight/success/failure/observation
    tags: 逗号分隔的标签
    """
    experiences = _load_experiences(memory_dir)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    entry = {
        "timestamp": datetime.now().isoformat(),
        "topic_id": topic_id,
        "idea_id": idea_id,
        "phase": phase,
        "type": type,
        "summary": summary,
        "details": details,
        "tags": tag_list,
    }
    # 去重：同 phase + topic_id + type + idea_id 更新已有记录
    for i, exp in enumerate(experiences):
        if (exp.get("phase") == phase and exp.get("topic_id") == topic_id
                and exp.get("type") == type and exp.get("idea_id") == idea_id):
            experiences[i] = entry
            _save_experiences(experiences, memory_dir)
            return f"Experience updated: [{type}] {summary[:80]}"
    experiences.append(entry)
    _save_experiences(experiences, memory_dir)
    return f"Experience added: [{type}] {summary[:80]}"
