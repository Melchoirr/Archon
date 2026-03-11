"""可视化工具：通用结果对比图表"""
import os
import numpy as np
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "DejaVu Sans"
plt.rcParams["figure.dpi"] = 150


def plot_metrics_table(results: dict, save_path: str = None):
    """绘制结果对比表格
    results: {method: {metric: value}}
    """
    methods = list(results.keys())
    metrics = list(results[methods[0]].keys())

    fig, ax = plt.subplots(figsize=(10, 2 + 0.4 * len(methods)))
    ax.axis("off")

    cell_text = []
    for m in methods:
        cell_text.append([f"{results[m][metric]:.4f}" for metric in metrics])

    table = ax.table(cellText=cell_text, rowLabels=methods, colLabels=metrics,
                     loc="center", cellLoc="center")
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.5)

    ax.set_title("Experiment Results Comparison", pad=20)
    plt.tight_layout()

    if save_path:
        os.makedirs(os.path.dirname(save_path) if os.path.dirname(save_path) else ".", exist_ok=True)
        plt.savefig(save_path, bbox_inches="tight")
        plt.close()
    else:
        plt.show()
