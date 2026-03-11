"""配置加载与模板变量导出，供所有 Agent __init__ 使用"""
import os
import yaml


def load_topic_config(path="config.yaml") -> dict:
    """加载配置并导出模板变量

    Returns:
        {
            "topic_title": str,
            "topic_domain": str,
            "search_keywords": list,
            "dataset_names": str,       # 逗号分隔的数据集名，如 "etth1, etth2"
            "datasets": dict,           # 完整 datasets 配置
            "metric_names": str,        # 逗号分隔的指标名
            "metrics": dict,            # 完整 metrics 配置
            "quick_test_desc": str,     # quick test 描述
            "experiment": dict,         # 完整 experiment 配置
            "config": dict,             # 完整配置
        }
    """
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    topic = config.get("topic", {})
    datasets = config.get("datasets", {}) or {}
    metrics = config.get("metrics", {}) or {}
    experiment = config.get("experiment", {}) or {}

    # 数据集名称列表
    dataset_names = ", ".join(datasets.keys()) if datasets else ""

    # 指标名称列表
    all_metrics = list(metrics.get("primary", []) or []) + list(metrics.get("topic_specific", []) or [])
    metric_names = ", ".join(all_metrics) if all_metrics else ""

    # quick test 描述
    qt = experiment.get("quick_test", {}) or {}
    quick_test_desc = ", ".join(f"{k}={v}" for k, v in qt.items()) if qt else ""

    return {
        "topic_title": topic.get("title", "(未设置课题)"),
        "topic_domain": topic.get("domain", ""),
        "search_keywords": topic.get("keywords", []) or [],
        "dataset_names": dataset_names,
        "datasets": datasets,
        "metric_names": metric_names,
        "metrics": metrics,
        "quick_test_desc": quick_test_desc,
        "experiment": experiment,
        "config": config,
    }
