"""评估指标：注册式架构，支持动态选取"""
import numpy as np

METRIC_REGISTRY = {}


def register_metric(name: str):
    """装饰器：将函数注册到 METRIC_REGISTRY"""
    def decorator(fn):
        METRIC_REGISTRY[name] = fn
        return fn
    return decorator


def evaluate_by_config(pred: np.ndarray, true: np.ndarray,
                       metric_names: list, **kwargs) -> dict:
    """按配置中指定的指标名称列表计算指标

    Args:
        pred: 预测值
        true: 真实值
        metric_names: 指标名称列表

    Returns:
        {metric_name: value}
    """
    results = {}
    for name in metric_names:
        if name not in METRIC_REGISTRY:
            results[name] = f"unknown metric: {name}"
            continue
        results[name] = METRIC_REGISTRY[name](pred=pred, true=true, **kwargs)
    return results
