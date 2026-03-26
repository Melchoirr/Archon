"""阶段前后文档快照：记录每阶段执行前后的状态"""
import os
import re
import logging
from datetime import datetime

from shared.paths import PathManager

logger = logging.getLogger(__name__)


def log_phase_start(phase: str, topic_dir: str, idea_id: str = "",
                    paths: PathManager = None) -> str:
    """记录阶段开始时的状态快照。"""
    log_name = f"{phase}_{idea_id}" if idea_id else phase
    if paths:
        log_dir = str(paths.phase_log_dir(phase, idea_id))
    else:
        log_dir = os.path.join(topic_dir, "phase_logs", log_name)
    os.makedirs(log_dir, exist_ok=True)

    # 收集当前 registry 状态
    if paths:
        registry_path = str(paths.idea_registry_yaml)
    else:
        registry_path = os.path.join(topic_dir, "idea_registry.yaml")
    registry_content = ""
    if os.path.exists(registry_path):
        with open(registry_path, "r", encoding="utf-8") as f:
            registry_content = f.read()

    # 收集 idea 状态
    idea_status = ""
    if idea_id:
        idea_dir = paths.idea_dir(idea_id) if paths else None
        if idea_dir and idea_dir.exists():
            files = [f.name for f in idea_dir.iterdir()]
            idea_status = f"Idea directory: {idea_dir.name}\nFiles: {', '.join(files)}"
        elif not paths:
            ideas_dir = os.path.join(topic_dir, "ideas")
            if os.path.exists(ideas_dir):
                for d in os.listdir(ideas_dir):
                    if idea_id in d:
                        idea_path = os.path.join(ideas_dir, d)
                        files = os.listdir(idea_path)
                        idea_status = f"Idea directory: {d}\nFiles: {', '.join(files)}"
                        break

    content = f"""# Phase Start: {phase}
Time: {datetime.now().isoformat()}
Idea: {idea_id or 'N/A'}

## Idea Registry State
```yaml
{registry_content}
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
                  summary: str = "", kb_mgr=None, paths: PathManager = None) -> str:
    """记录阶段结束时的状态和摘要。"""
    log_name = f"{phase}_{idea_id}" if idea_id else phase
    if paths:
        log_dir = str(paths.phase_log_dir(phase, idea_id))
    else:
        log_dir = os.path.join(topic_dir, "phase_logs", log_name)
    os.makedirs(log_dir, exist_ok=True)

    new_artifacts = _collect_new_artifacts(phase, topic_dir, idea_id, paths)

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

    if kb_mgr and kb_mgr.enabled and new_artifacts:
        _upload_artifacts(kb_mgr, new_artifacts, topic_dir, idea_id, phase)

    logger.info(f"Phase end logged: {log_name}")
    return f"Logged phase end: {after_path}"


def _collect_new_artifacts(phase: str, topic_dir: str, idea_id: str,
                           paths: PathManager = None) -> list:
    """收集该阶段可能产生的新文件"""
    artifacts = []

    if paths:
        phase_outputs = {
            "elaborate": [str(paths.context_md)],
            "survey": [
                str(paths.survey_md),
                str(paths.survey_dir / "index.md"),
                str(paths.leaderboard_md),
                str(paths.baselines_md),
                str(paths.datasets_md),
                str(paths.metrics_md),
            ],
        }

        if idea_id:
            idea_dir = paths.idea_dir(idea_id)
            if idea_dir:
                idea_outputs = {
                    "ideation": [str(idea_dir / "proposal.md")],
                    "refine": [
                        str(idea_dir / "refinement" / "theory.md"),
                        str(idea_dir / "refinement" / "model_modular.md"),
                        str(idea_dir / "refinement" / "model_complete.md"),
                        str(idea_dir / "experiment_plan.md"),
                    ],
                    "code_reference": [str(idea_dir / "code_reference.md")],
                    "code": [str(idea_dir / "src" / "structure.md")],
                    "experiment": [str(idea_dir / "experiment_results.md")],
                    "analyze": [str(idea_dir / "analysis.md")],
                    "conclude": [str(idea_dir / "conclusion.md")],
                }
                phase_outputs.update(idea_outputs)

        # survey 阶段额外收集
        if phase == "survey":
            sd = paths.summaries_dir
            if sd.exists():
                for f in sd.iterdir():
                    if f.suffix == ".md":
                        artifacts.append(str(f))
            dc = paths.dataset_cards_dir
            if dc.exists():
                for f in dc.iterdir():
                    if f.suffix == ".md":
                        artifacts.append(str(f))
    else:
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

        if idea_id:
            ideas_dir = os.path.join(topic_dir, "ideas")
            idea_dir = ""
            if os.path.exists(ideas_dir):
                for d in os.listdir(ideas_dir):
                    if idea_id in d:
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
                    "code_reference": [os.path.join(idea_dir, "code_reference.md")],
                    "code": [os.path.join(idea_dir, "src", "structure.md")],
                    "experiment": [os.path.join(idea_dir, "experiment_results.md")],
                    "analyze": [os.path.join(idea_dir, "analysis.md")],
                    "conclude": [os.path.join(idea_dir, "conclusion.md")],
                }
                phase_outputs.update(idea_outputs)

        if phase == "survey":
            summaries_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "knowledge", "papers", "summaries"
            )
            if os.path.exists(summaries_dir):
                for f in os.listdir(summaries_dir):
                    if f.endswith(".md"):
                        artifacts.append(os.path.join(summaries_dir, f))
            dc_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "knowledge", "dataset_cards"
            )
            if os.path.exists(dc_dir):
                for f in os.listdir(dc_dir):
                    if f.endswith(".md"):
                        artifacts.append(os.path.join(dc_dir, f))

    for path in phase_outputs.get(phase, []):
        if os.path.exists(path):
            artifacts.append(path)

    return artifacts


_uploaded_artifact_set = set()
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def derive_display_name(file_path: str) -> str:
    """从本地路径推导知识库上传文件名"""
    abs_path = os.path.abspath(file_path)
    rel = os.path.relpath(abs_path, _PROJECT_ROOT)
    parts = rel.replace(os.sep, "/").split("/")

    if parts[0] == "topics" and len(parts) >= 3:
        topic_dir_name = parts[1]
        topic_id_match = re.match(r"(T\d+)", topic_dir_name)
        topic_id = topic_id_match.group(1) if topic_id_match else topic_dir_name
        rest = parts[2:]

        if rest[0] == "ideas" and len(rest) >= 3:
            idea_dir_name = rest[1]
            idea_id_match = re.match(r"(I\d+)", idea_dir_name)
            idea_id = idea_id_match.group(1) if idea_id_match else idea_dir_name
            inner = rest[2:]
            name_no_ext = os.path.splitext("_".join(inner))[0]
            return f"{topic_id}_{idea_id}_{name_no_ext}"
        else:
            name_no_ext = os.path.splitext("_".join(rest))[0]
            return f"{topic_id}_{name_no_ext}"

    elif parts[0] == "knowledge" and len(parts) >= 3:
        rest = parts[1:]
        name_no_ext = os.path.splitext("_".join(rest))[0]
        return name_no_ext

    else:
        name_no_ext = os.path.splitext("_".join(parts))[0]
        return name_no_ext


def _upload_artifacts(kb_mgr, artifacts: list, topic_dir: str, idea_id: str, phase: str = ""):
    """上传产出文件到单一全局知识库"""
    from tools.knowledge_base import SINGLE_KB_NAME

    kb_id = kb_mgr.get_or_create_kb(SINGLE_KB_NAME, "全局研究知识库")
    if not kb_id:
        logger.warning("Failed to get/create global knowledge base")
        return

    for file_path in artifacts:
        if file_path in _uploaded_artifact_set:
            continue
        try:
            display_name = derive_display_name(file_path)
            doc_id = kb_mgr.upload_document(kb_id, file_path, display_name=display_name)
            _uploaded_artifact_set.add(file_path)
            if doc_id:
                logger.info(f"Uploaded to {SINGLE_KB_NAME}: {display_name}")
        except Exception as e:
            logger.warning(f"Failed to upload {file_path}: {e}")
