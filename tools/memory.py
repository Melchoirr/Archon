"""经验记忆系统：记录和查询研究过程中的经验"""
import json
import os
import yaml
from datetime import datetime

MEMORY_DIR = "memory"
EXPERIENCE_LOG = os.path.join(MEMORY_DIR, "experience_log.yaml")


def _load_experiences() -> list:
    if not os.path.exists(EXPERIENCE_LOG):
        return []
    with open(EXPERIENCE_LOG, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    return data


def _save_experiences(experiences: list):
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(EXPERIENCE_LOG, "w", encoding="utf-8") as f:
        yaml.dump(experiences, f, allow_unicode=True, default_flow_style=False)


def query_memory(tags: str = "", phase: str = "", idea_id: str = "",
                  topic_id: str = "") -> str:
    """查询经验记忆。可按 tags、phase、idea_id、topic_id 过滤。"""
    experiences = _load_experiences()
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
) -> str:
    """添加经验记录。
    type: insight/success/failure/observation
    tags: 逗号分隔的标签
    """
    experiences = _load_experiences()
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
    experiences.append(entry)
    _save_experiences(experiences)
    return f"Experience added: [{type}] {summary[:80]}"


QUERY_MEMORY_SCHEMA = {
    "description": "查询研究经验记忆，可按标签、阶段、idea ID 过滤",
    "parameters": {
        "type": "object",
        "properties": {
            "tags": {"type": "string", "description": "逗号分隔的标签过滤"},
            "phase": {"type": "string", "description": "阶段过滤: elaborate/survey/ideation/refine/code/experiment/analyze/conclude"},
            "idea_id": {"type": "string", "description": "Idea ID 过滤"},
            "topic_id": {"type": "string", "description": "Topic ID 过滤（如 T001）"},
        },
        "required": [],
    },
}

ADD_EXPERIENCE_SCHEMA = {
    "description": "添加一条研究经验记录",
    "parameters": {
        "type": "object",
        "properties": {
            "idea_id": {"type": "string", "description": "关联的 Idea ID"},
            "phase": {"type": "string", "description": "所属阶段"},
            "type": {"type": "string", "description": "类型: insight/success/failure/observation"},
            "summary": {"type": "string", "description": "经验摘要"},
            "details": {"type": "string", "description": "详细描述"},
            "tags": {"type": "string", "description": "逗号分隔的标签"},
            "topic_id": {"type": "string", "description": "关联的 Topic ID（如 T001）"},
        },
        "required": ["summary"],
    },
}
