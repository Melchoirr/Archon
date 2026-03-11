"""研究树 CRUD 操作工具 - 增强版：支持 topic 编号、实验迭代追踪"""
import json
import os
import re
import yaml
from datetime import datetime

# 默认路径（兼容旧代码），新代码应传入 topic_dir 下的路径
TREE_PATH = "research_tree.yaml"


def _resolve_tree_path(topic_dir: str = None) -> str:
    """获取 research_tree.yaml 路径"""
    if topic_dir:
        return os.path.join(topic_dir, "research_tree.yaml")
    return TREE_PATH


def read_tree(topic_dir: str = None) -> str:
    """读取完整研究树"""
    path = _resolve_tree_path(topic_dir)
    if not os.path.exists(path):
        return json.dumps({"error": f"Tree not found: {path}"}, ensure_ascii=False)
    with open(path, "r", encoding="utf-8") as f:
        tree = yaml.safe_load(f)
    return json.dumps(tree, indent=2, ensure_ascii=False)


def _load_tree(topic_dir: str = None) -> dict:
    path = _resolve_tree_path(topic_dir)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _save_tree(tree: dict, topic_dir: str = None):
    path = _resolve_tree_path(topic_dir)
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(tree, f, allow_unicode=True, default_flow_style=False)


def update_tree(path: str, value: str, topic_dir: str = None) -> str:
    """更新研究树中的字段。
    path: 点分隔路径，如 'root.literature.status'
    value: 新值（字符串，会尝试解析为 YAML 类型）
    """
    tree = _load_tree(topic_dir)
    if not tree:
        return f"Tree not found"

    keys = path.split(".")
    obj = tree
    for key in keys[:-1]:
        if key.isdigit():
            obj = obj[int(key)]
        else:
            obj = obj[key]

    last_key = keys[-1]
    if last_key.isdigit():
        obj[int(last_key)] = yaml.safe_load(value)
    else:
        obj[last_key] = yaml.safe_load(value)

    _save_tree(tree, topic_dir)
    return f"Updated {path} = {value}"


def add_idea_to_tree(idea_id: str, title: str, category: str,
                     brief: str = "", topic_dir: str = None) -> str:
    """向研究树添加一个新 idea（新格式）"""
    tree = _load_tree(topic_dir)
    if not tree:
        # 如果还没有 tree，也尝试旧路径
        tree = _load_tree()

    idea = {
        "id": idea_id,
        "brief": brief or _make_brief(title),
        "title": title,
        "category": category,
        "status": "proposed",
        "created_at": datetime.now().isoformat(),
        "phases": {
            "refinement": "pending",
            "code_reference": "pending",
            "coding": "pending",
            "experiment": "pending",
            "analysis": "pending",
            "conclusion": "pending",
        },
        "relationships": [],
        "experiment_steps": [],
    }
    tree["root"]["ideas"].append(idea)
    _save_tree(tree, topic_dir)
    return f"Added idea {idea_id}: {title}"


def _make_brief(title: str) -> str:
    """从标题生成简短标识"""
    # 取首字母缩写或前几个词
    words = re.findall(r'[A-Z][a-z]*|[a-z]+', title)
    if len(words) <= 3:
        return "_".join(w.lower() for w in words)
    # 取大写首字母组成的缩写
    caps = [w[0] for w in title.split() if w[0].isupper()]
    if caps:
        return "".join(caps).lower()
    return "_".join(words[:3]).lower()


# === 新增编号函数 ===

def next_topic_id(topics_dir: str = "topics") -> str:
    """生成下一个 topic 编号 (T001, T002, ...)"""
    if not os.path.exists(topics_dir):
        return "T001"
    existing = [d for d in os.listdir(topics_dir) if d.startswith("T") and os.path.isdir(os.path.join(topics_dir, d))]
    if not existing:
        return "T001"
    nums = []
    for d in existing:
        match = re.match(r"T(\d+)", d)
        if match:
            nums.append(int(match.group(1)))
    return f"T{max(nums) + 1:03d}" if nums else "T001"


def next_idea_id(topic_dir: str) -> str:
    """生成下一个 idea 编号 (I001, I002, ...)"""
    tree = _load_tree(topic_dir)
    if not tree:
        return "I001"
    ideas = tree.get("root", {}).get("ideas", [])
    if not ideas:
        return "I001"
    nums = []
    for idea in ideas:
        match = re.match(r"I(\d+)", idea.get("id", ""))
        if match:
            nums.append(int(match.group(1)))
    return f"I{max(nums) + 1:03d}" if nums else "I001"


def next_step_id(idea_id: str, topic_dir: str = None) -> str:
    """生成下一个实验步骤编号 (S01, S02, ...)"""
    tree = _load_tree(topic_dir)
    if not tree:
        return "S01"
    for idea in tree.get("root", {}).get("ideas", []):
        if idea["id"] == idea_id:
            steps = idea.get("experiment_steps", [])
            if not steps:
                return "S01"
            nums = []
            for s in steps:
                match = re.match(r"S(\d+)", s.get("step_id", ""))
                if match:
                    nums.append(int(match.group(1)))
            return f"S{max(nums) + 1:02d}" if nums else "S01"
    return "S01"


# === 实验迭代追踪 ===

def add_experiment_step(idea_id: str, step_name: str, max_iter: int = 3,
                        topic_dir: str = None) -> str:
    """注册一个实验步骤到 idea"""
    tree = _load_tree(topic_dir)
    if not tree:
        return "Tree not found"

    for idea in tree["root"]["ideas"]:
        if idea["id"] == idea_id:
            step_id = next_step_id(idea_id, topic_dir)
            iterations = [
                {"version": v + 1, "status": "pending", "config_diff": None}
                for v in range(max_iter)
            ]
            step = {
                "step_id": step_id,
                "name": step_name,
                "status": "pending",
                "max_iter": max_iter,
                "iterations": iterations,
            }
            if "experiment_steps" not in idea:
                idea["experiment_steps"] = []
            idea["experiment_steps"].append(step)
            _save_tree(tree, topic_dir)
            return f"Added step {step_id} ({step_name}) to {idea_id} with {max_iter} iterations"

    return f"Idea {idea_id} not found"


def update_iteration(idea_id: str, step_id: str, version: int,
                     status: str, config_diff: str = None,
                     topic_dir: str = None) -> str:
    """更新实验迭代状态"""
    tree = _load_tree(topic_dir)
    if not tree:
        return "Tree not found"

    for idea in tree["root"]["ideas"]:
        if idea["id"] == idea_id:
            for step in idea.get("experiment_steps", []):
                if step["step_id"] == step_id:
                    for it in step["iterations"]:
                        if it["version"] == version:
                            it["status"] = status
                            if config_diff:
                                it["config_diff"] = config_diff
                            # 如果所有迭代完成，更新步骤状态
                            all_done = all(i["status"] in ("completed", "skipped") for i in step["iterations"])
                            if all_done:
                                step["status"] = "completed"
                            elif any(i["status"] == "running" for i in step["iterations"]):
                                step["status"] = "running"
                            _save_tree(tree, topic_dir)
                            return f"Updated {idea_id}/{step_id}/V{version} -> {status}"
                    return f"Version {version} not found in {step_id}"
            return f"Step {step_id} not found in {idea_id}"
    return f"Idea {idea_id} not found"


def add_idea_relationship(idea_a: str, idea_b: str, rel_type: str,
                          topic_dir: str = None) -> str:
    """在研究树中记录 idea 关系"""
    tree = _load_tree(topic_dir)
    if not tree:
        return "Tree not found"

    for idea in tree["root"]["ideas"]:
        if idea["id"] == idea_a:
            if "relationships" not in idea:
                idea["relationships"] = []
            idea["relationships"].append({"target": idea_b, "type": rel_type})
            _save_tree(tree, topic_dir)
            return f"Added relationship: {idea_a} --{rel_type}--> {idea_b}"

    return f"Idea {idea_a} not found"


# === 兼容旧代码的 schema ===

READ_TREE_SCHEMA = {
    "description": "读取完整的研究树状态",
    "parameters": {
        "type": "object",
        "properties": {
            "topic_dir": {"type": "string", "description": "topic 目录路径（可选）"},
        },
        "required": [],
    },
}

UPDATE_TREE_SCHEMA = {
    "description": "更新研究树中指定路径的值",
    "parameters": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "点分隔路径，如 'root.literature.status'"},
            "value": {"type": "string", "description": "新值"},
            "topic_dir": {"type": "string", "description": "topic 目录路径（可选）"},
        },
        "required": ["path", "value"],
    },
}

ADD_IDEA_SCHEMA = {
    "description": "向研究树中添加一个新的研究 idea",
    "parameters": {
        "type": "object",
        "properties": {
            "idea_id": {"type": "string", "description": "Idea ID，如 'I001'"},
            "title": {"type": "string", "description": "Idea 标题"},
            "category": {"type": "string", "description": "类别: loss/architecture/training/inference"},
            "brief": {"type": "string", "description": "简短标识（用于目录名）"},
            "topic_dir": {"type": "string", "description": "topic 目录路径（可选）"},
        },
        "required": ["idea_id", "title", "category"],
    },
}

ADD_EXPERIMENT_STEP_SCHEMA = {
    "description": "注册一个实验步骤到指定 idea，含可配置的迭代次数",
    "parameters": {
        "type": "object",
        "properties": {
            "idea_id": {"type": "string", "description": "Idea ID"},
            "step_name": {"type": "string", "description": "步骤名称（如 quick_test, full_test）"},
            "max_iter": {"type": "integer", "description": "最大迭代次数", "default": 3},
            "topic_dir": {"type": "string", "description": "topic 目录路径（可选）"},
        },
        "required": ["idea_id", "step_name"],
    },
}

UPDATE_ITERATION_SCHEMA = {
    "description": "更新实验迭代状态",
    "parameters": {
        "type": "object",
        "properties": {
            "idea_id": {"type": "string", "description": "Idea ID"},
            "step_id": {"type": "string", "description": "步骤 ID（如 S01）"},
            "version": {"type": "integer", "description": "版本号（如 1, 2, 3）"},
            "status": {"type": "string", "description": "状态: pending/running/completed/failed/skipped"},
            "config_diff": {"type": "string", "description": "相对 V1 的配置差异"},
            "topic_dir": {"type": "string", "description": "topic 目录路径（可选）"},
        },
        "required": ["idea_id", "step_id", "version", "status"],
    },
}
