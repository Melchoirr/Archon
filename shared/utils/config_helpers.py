"""配置加载 — 返回 TopicConfig Pydantic 模型"""

import yaml

from shared.models.config import TopicConfig


def load_topic_config(path: str = "config.yaml") -> TopicConfig:
    """加载并校验 config.yaml，返回 TopicConfig 模型。

    属性访问方式：
        cfg.topic.title        # 课题标题
        cfg.topic.domain       # 领域
        cfg.search_keywords    # 搜索关键词列表
        cfg.dataset_names      # 逗号分隔的数据集名
        cfg.metric_names       # 逗号分隔的指标名
        cfg.quick_test_desc    # quick test 描述
        cfg.datasets           # 完整 datasets 配置
        cfg.metrics            # 完整 metrics 配置
        cfg.experiment         # 完整 experiment 配置
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return TopicConfig.model_validate(raw)
