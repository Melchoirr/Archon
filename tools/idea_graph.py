"""Idea 关系图 CRUD：管理 idea 间的关系"""
import os
import yaml

VALID_REL_TYPES = {"builds_on", "alternative_to", "complementary", "combines_with"}


def _graph_path(topic_dir: str) -> str:
    return os.path.join(topic_dir, "ideas", "idea_graph.yaml")


def _load_graph(topic_dir: str) -> dict:
    path = _graph_path(topic_dir)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {"relationships": []}
    return {"relationships": []}


def _save_graph(topic_dir: str, graph: dict):
    path = _graph_path(topic_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(graph, f, allow_unicode=True, default_flow_style=False)


def add_idea_relationship(idea_a: str, idea_b: str, rel_type: str, topic_dir: str = ".") -> str:
    """添加两个 idea 之间的关系。

    Args:
        idea_a: 第一个 idea ID (如 T001-I001)
        idea_b: 第二个 idea ID (如 T001-I002)
        rel_type: 关系类型 - builds_on, alternative_to, complementary, combines_with
        topic_dir: topic 目录路径
    """
    if rel_type not in VALID_REL_TYPES:
        return f"Invalid rel_type '{rel_type}'. Valid: {', '.join(VALID_REL_TYPES)}"

    graph = _load_graph(topic_dir)

    # 检查重复
    for rel in graph["relationships"]:
        if rel["idea_a"] == idea_a and rel["idea_b"] == idea_b and rel["type"] == rel_type:
            return f"Relationship already exists: {idea_a} --{rel_type}--> {idea_b}"

    graph["relationships"].append({
        "idea_a": idea_a,
        "idea_b": idea_b,
        "type": rel_type,
    })
    _save_graph(topic_dir, graph)
    return f"Added relationship: {idea_a} --{rel_type}--> {idea_b}"


def get_idea_graph(topic_dir: str = ".") -> str:
    """返回完整关系图的 markdown 渲染"""
    graph = _load_graph(topic_dir)
    rels = graph.get("relationships", [])
    if not rels:
        return "No idea relationships defined yet."

    lines = ["# Idea 关系图\n"]
    for rel in rels:
        arrow = {"builds_on": "→ (基于)", "alternative_to": "↔ (替代)",
                 "complementary": "⊕ (互补)", "combines_with": "⊗ (组合)"}
        symbol = arrow.get(rel["type"], "→")
        lines.append(f"- **{rel['idea_a']}** {symbol} **{rel['idea_b']}**")

    # 生成建议组合
    complementary = [(r["idea_a"], r["idea_b"]) for r in rels if r["type"] == "complementary"]
    if complementary:
        lines.append("\n## 建议组合")
        for a, b in complementary:
            lines.append(f"- {a} + {b} 可能产生协同效果")

    return "\n".join(lines)


def suggest_combinations(topic_dir: str = ".") -> str:
    """建议可组合的 idea 对"""
    graph = _load_graph(topic_dir)
    rels = graph.get("relationships", [])
    suggestions = []
    for rel in rels:
        if rel["type"] in ("complementary", "combines_with"):
            suggestions.append(f"{rel['idea_a']} + {rel['idea_b']} ({rel['type']})")
    if not suggestions:
        return "No combination suggestions available."
    return "Suggested combinations:\n" + "\n".join(f"- {s}" for s in suggestions)
