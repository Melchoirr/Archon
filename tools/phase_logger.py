"""阶段前后文档快照：记录每阶段执行前后的状态"""
import os
import yaml
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def log_phase_start(phase: str, topic_dir: str, idea_id: str = "") -> str:
    """记录阶段开始时的状态快照。

    Args:
        phase: 阶段名称
        topic_dir: topic 目录路径
        idea_id: idea ID（可选）
    """
    log_name = f"{phase}_{idea_id}" if idea_id else phase
    log_dir = os.path.join(topic_dir, "phase_logs", log_name)
    os.makedirs(log_dir, exist_ok=True)

    # 收集当前状态
    tree_path = os.path.join(topic_dir, "research_tree.yaml")
    tree_content = ""
    if os.path.exists(tree_path):
        with open(tree_path, "r", encoding="utf-8") as f:
            tree_content = f.read()

    # 收集 idea 状态
    idea_status = ""
    if idea_id:
        ideas_dir = os.path.join(topic_dir, "ideas")
        if os.path.exists(ideas_dir):
            for d in os.listdir(ideas_dir):
                if d.startswith(idea_id):
                    idea_path = os.path.join(ideas_dir, d)
                    files = os.listdir(idea_path)
                    idea_status = f"Idea directory: {d}\nFiles: {', '.join(files)}"
                    break

    content = f"""# Phase Start: {phase}
Time: {datetime.now().isoformat()}
Idea: {idea_id or 'N/A'}

## Research Tree State
```yaml
{tree_content}
```

## Idea Status
{idea_status or 'N/A'}
"""

    before_path = os.path.join(log_dir, "before.md")
    with open(before_path, "w", encoding="utf-8") as f:
        f.write(content)

    logger.info(f"Phase start logged: {log_name}")
    return f"Logged phase start: {before_path}"


def log_phase_end(phase: str, topic_dir: str, idea_id: str = "",
                  summary: str = "", kb_mgr=None) -> str:
    """记录阶段结束时的状态和摘要。

    Args:
        phase: 阶段名称
        topic_dir: topic 目录路径
        idea_id: idea ID（可选）
        summary: 阶段执行摘要
        kb_mgr: KnowledgeBaseManager 实例（可选，用于上传文档到知识库）
    """
    log_name = f"{phase}_{idea_id}" if idea_id else phase
    log_dir = os.path.join(topic_dir, "phase_logs", log_name)
    os.makedirs(log_dir, exist_ok=True)

    # 收集新生成的文件
    new_artifacts = _collect_new_artifacts(phase, topic_dir, idea_id)

    content = f"""# Phase End: {phase}
Time: {datetime.now().isoformat()}
Idea: {idea_id or 'N/A'}

## Summary
{summary}

## New/Modified Artifacts
{chr(10).join(f'- {a}' for a in new_artifacts) if new_artifacts else 'None'}
"""

    after_path = os.path.join(log_dir, "after.md")
    with open(after_path, "w", encoding="utf-8") as f:
        f.write(content)

    # 自动上传到知识库
    if kb_mgr and kb_mgr.enabled and new_artifacts:
        _upload_artifacts(kb_mgr, new_artifacts, topic_dir, idea_id)

    logger.info(f"Phase end logged: {log_name}")
    return f"Logged phase end: {after_path}"


def _collect_new_artifacts(phase: str, topic_dir: str, idea_id: str) -> list:
    """收集该阶段可能产生的新文件"""
    artifacts = []

    # 按阶段确定可能的产出路径
    phase_outputs = {
        "elaborate": [os.path.join(topic_dir, "context.md")],
        "survey": [
            os.path.join(topic_dir, "survey", "survey.md"),
            os.path.join(topic_dir, "survey", "index.md"),
            os.path.join(topic_dir, "survey", "leaderboard.md"),
            os.path.join(topic_dir, "baselines.md"),
            os.path.join(topic_dir, "datasets.md"),
            os.path.join(topic_dir, "metrics.md"),
        ],
    }

    # Idea-specific outputs
    if idea_id:
        ideas_dir = os.path.join(topic_dir, "ideas")
        idea_dir = ""
        if os.path.exists(ideas_dir):
            for d in os.listdir(ideas_dir):
                if d.startswith(idea_id):
                    idea_dir = os.path.join(ideas_dir, d)
                    break

        if idea_dir:
            idea_outputs = {
                "ideation": [os.path.join(idea_dir, "proposal.md")],
                "refine": [
                    os.path.join(idea_dir, "refinement", "theory.md"),
                    os.path.join(idea_dir, "refinement", "model_modular.md"),
                    os.path.join(idea_dir, "refinement", "model_complete.md"),
                    os.path.join(idea_dir, "experiment_plan.md"),
                ],
                "code": [os.path.join(idea_dir, "src", "structure.md")],
                "analyze": [os.path.join(idea_dir, "analysis.md")],
                "conclude": [os.path.join(idea_dir, "conclusion.md")],
            }
            phase_outputs.update(idea_outputs)

    # 检查哪些文件存在
    for path in phase_outputs.get(phase, []):
        if os.path.exists(path):
            artifacts.append(path)

    # 收集全局 summaries（survey 阶段）
    if phase == "survey":
        summaries_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "knowledge", "papers", "summaries"
        )
        if os.path.exists(summaries_dir):
            for f in os.listdir(summaries_dir):
                if f.endswith(".md"):
                    artifacts.append(os.path.join(summaries_dir, f))

        # 也收集 survey/papers/（兼容旧结构）
        papers_dir = os.path.join(topic_dir, "survey", "papers")
        if os.path.exists(papers_dir):
            for f in os.listdir(papers_dir):
                if f.endswith(".md"):
                    artifacts.append(os.path.join(papers_dir, f))

    # 收集 dataset cards
    if phase == "survey":
        dc_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "knowledge", "dataset_cards"
        )
        if os.path.exists(dc_dir):
            for f in os.listdir(dc_dir):
                if f.endswith(".md"):
                    artifacts.append(os.path.join(dc_dir, f))

    return artifacts


def _upload_artifacts(kb_mgr, artifacts: list, topic_dir: str, idea_id: str):
    """上传产出文件到单一全局知识库，标题携带元信息"""
    import re
    from tools.knowledge_base import SINGLE_KB_NAME

    topic_name = os.path.basename(topic_dir)
    topic_id_match = re.match(r"(T\d+)", topic_name)
    topic_id = topic_id_match.group(1) if topic_id_match else topic_name

    kb_id = kb_mgr.get_or_create_kb(SINGLE_KB_NAME, "全局研究知识库")
    if not kb_id:
        logger.warning("Failed to get/create global knowledge base")
        return

    for file_path in artifacts:
        try:
            basename = os.path.basename(file_path)
            # 构建带元信息的标题
            if "knowledge/papers/summaries" in file_path:
                title = f"[{topic_id}] [survey] {basename}"
            elif "knowledge/dataset_cards" in file_path:
                title = f"[dataset] {basename}"
            elif "knowledge/papers" in file_path or "knowledge/repos" in file_path:
                title = f"[global] {basename}"
            elif idea_id:
                title = f"[{topic_id}-{idea_id}] {basename}"
            else:
                title = f"[{topic_id}] [survey] {basename}"

            # 上传时用重命名的方式：创建临时符号链接或直接上传
            # 智谱 API 用 file basename 作为文档名，我们直接上传原文件
            kb_mgr.upload_document(kb_id, file_path)
            logger.info(f"Uploaded to {SINGLE_KB_NAME}: {title}")
        except Exception as e:
            logger.warning(f"Failed to upload {file_path}: {e}")


LOG_PHASE_START_SCHEMA = {
    "description": "记录阶段开始时的状态快照",
    "parameters": {
        "type": "object",
        "properties": {
            "phase": {"type": "string", "description": "阶段名称"},
            "topic_dir": {"type": "string", "description": "topic 目录路径"},
            "idea_id": {"type": "string", "description": "idea ID", "default": ""},
        },
        "required": ["phase", "topic_dir"],
    },
}

LOG_PHASE_END_SCHEMA = {
    "description": "记录阶段结束时的状态和摘要",
    "parameters": {
        "type": "object",
        "properties": {
            "phase": {"type": "string", "description": "阶段名称"},
            "topic_dir": {"type": "string", "description": "topic 目录路径"},
            "idea_id": {"type": "string", "description": "idea ID", "default": ""},
            "summary": {"type": "string", "description": "阶段执行摘要", "default": ""},
        },
        "required": ["phase", "topic_dir"],
    },
}
