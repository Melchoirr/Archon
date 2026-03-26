"""配置加载 + topic 信息提取"""

import os
import re
import yaml

from shared.models.config import GlobalConfig


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config.yaml")


def load_global_config(path: str = None) -> GlobalConfig:
    """加载项目根 config.yaml，返回 GlobalConfig。"""
    path = path or _DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        return GlobalConfig()
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return GlobalConfig.model_validate(raw)


def extract_topic_title(topic_dir: str) -> str:
    """从 context.md 提取 # 标题；fallback 到 topic_spec.md 的 # 标题。"""
    for fname in ["context.md", "topic_spec.md"]:
        fpath = os.path.join(topic_dir, fname)
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("# "):
                        return line[2:].strip()
    # fallback: directory name
    basename = os.path.basename(topic_dir)
    # T001_mean_reversion -> mean_reversion
    parts = basename.split("_", 1)
    return parts[1] if len(parts) > 1 else basename


def extract_topic_spec(topic_dir: str) -> str:
    """读取 topic_spec.md 全文（elaborate 阶段的输入）。"""
    fpath = os.path.join(topic_dir, "topic_spec.md")
    if os.path.exists(fpath):
        with open(fpath, "r", encoding="utf-8") as f:
            return f.read()
    return ""
