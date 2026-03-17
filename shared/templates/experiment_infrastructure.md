# 实验基础设施规范

本文档定义了 Archon 系统生成实验代码时必须遵循的标准化基础设施规范。所有 idea 的实验代码都应按此规范组织。

---

## 1. 目录结构规范

```
src/
├── configs/
│   ├── default.yaml              # 全量默认配置（所有超参数的唯一真相源）
│   ├── stages/                   # 实验阶段覆盖配置
│   │   ├── S01_quick_test.yaml   # 快速验证（小数据、少 epoch）
│   │   ├── S02_small_scale.yaml  # 小规模实验
│   │   ├── S03_large_scale.yaml  # 大规模正式实验
│   │   ├── S04_ablation.yaml     # 消融实验
│   │   ├── S05_long_term.yaml    # 长序列/长期预测
│   │   ├── S06_efficiency.yaml   # 效率测试
│   │   └── S07_sensitivity.yaml  # 超参数敏感度分析
│   └── ablations/                # 消融变体配置
│       └── *.yaml                # 每个消融变体一个文件
├── model/                        # 核心模型实现
├── data/                         # 数据加载与预处理
├── experiment/
│   ├── trainer.py                # 训练器
│   └── evaluator.py              # 独立评估器
├── utils/
│   ├── logger.py                 # 日志工具
│   ├── helpers.py                # 辅助函数
│   └── config.py                 # 配置加载逻辑
├── visualize/                    # 可视化模块（5 个标准模块）
│   ├── training_curves.py
│   ├── trajectory_plots.py
│   ├── variance_analysis.py
│   ├── ablation_table.py
│   └── sensitivity_heatmap.py
├── run.py                        # 统一实验入口
└── scripts/                      # Bash 批量运行脚本
    ├── run_stage.sh
    ├── run_all.sh
    ├── run_ablation.sh
    └── run_sensitivity.sh
```

---

## 2. YAML 配置系统

### 2.1 default.yaml 结构

`configs/default.yaml` 是所有超参数的**唯一真相源**，包含完整的默认值。分为 6 个顶级 section：

```yaml
experiment:
  name: "experiment_name"
  seed: 42
  device: "cuda"
  num_workers: 4

data:
  dataset: "dataset_name"
  train_ratio: 0.7
  val_ratio: 0.1
  test_ratio: 0.2
  # ... 数据相关参数

model:
  # 模型架构参数
  # enable_* 开关用于消融实验
  enable_component_a: true
  enable_component_b: true
  enable_component_c: true

train:
  epochs: 100
  batch_size: 32
  lr: 1e-3
  weight_decay: 1e-5
  early_stopping:
    patience: 15
    min_delta: 1e-6
  scheduler:
    type: "cosine"
    # ...

eval:
  num_samples: 100
  metrics: ["mse", "mae"]
  # ... 评估相关参数

output:
  save_model: true
  save_predictions: true
  plot_format: "png"
  plot_dpi: 150
```

### 2.2 层叠覆盖机制

Stage 和 ablation YAML 文件**只包含需要覆盖的字段**，不重复 default.yaml 中的值：

```yaml
# configs/stages/S01_quick_test.yaml
experiment:
  name: "quick_test"
data:
  # 可覆盖为更小的数据子集
train:
  epochs: 5
  batch_size: 64
```

**配置加载优先级**（后者覆盖前者）：
```
default.yaml  <-  stage yaml  <-  ablation yaml  <-  CLI --override
```

---

## 3. 配置加载逻辑（utils/config.py）

### 3.1 Pydantic 验证

为每个 section 定义 Pydantic BaseModel，提供类型安全和验证：

```python
from pydantic import BaseModel
from typing import Optional, List

class ExperimentConfig(BaseModel):
    name: str
    seed: int = 42
    device: str = "cuda"
    num_workers: int = 4

class DataConfig(BaseModel):
    dataset: str
    train_ratio: float = 0.7
    val_ratio: float = 0.1
    test_ratio: float = 0.2

class ModelConfig(BaseModel):
    # enable_* 开关
    enable_component_a: bool = True
    enable_component_b: bool = True
    # ... 具体由 idea 决定

class TrainConfig(BaseModel):
    epochs: int = 100
    batch_size: int = 32
    lr: float = 1e-3
    # ...

class EvalConfig(BaseModel):
    num_samples: int = 100
    metrics: List[str] = ["mse", "mae"]

class OutputConfig(BaseModel):
    save_model: bool = True
    save_predictions: bool = True

class Config(BaseModel):
    experiment: ExperimentConfig
    data: DataConfig
    model: ModelConfig
    train: TrainConfig
    eval: EvalConfig
    output: OutputConfig
```

### 3.2 deep_merge + 加载链

```python
import yaml
from copy import deepcopy

def deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典，override 覆盖 base"""
    result = deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result

def load_config(config_dir: str, stage: str = None,
                ablation: str = None, overrides: list = None) -> Config:
    """加载配置：default <- stage <- ablation <- CLI overrides"""
    with open(f"{config_dir}/default.yaml") as f:
        cfg = yaml.safe_load(f)

    if stage:
        with open(f"{config_dir}/stages/{stage}.yaml") as f:
            cfg = deep_merge(cfg, yaml.safe_load(f))

    if ablation:
        with open(f"{config_dir}/ablations/{ablation}.yaml") as f:
            cfg = deep_merge(cfg, yaml.safe_load(f))

    if overrides:
        for ov in overrides:
            key, val = ov.split("=", 1)
            keys = key.split(".")
            d = cfg
            for k in keys[:-1]:
                d = d.setdefault(k, {})
            # 自动类型转换
            d[keys[-1]] = yaml.safe_load(val)

    return Config(**cfg)
```

---

## 4. 统一实验入口（run.py）

```python
import argparse

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=str, default=None,
                        help="实验阶段配置 (e.g., S01_quick_test)")
    parser.add_argument("--ablation", type=str, default=None,
                        help="消融配置 (e.g., no_component_a)")
    parser.add_argument("--dataset", type=str, default=None,
                        help="覆盖数据集")
    parser.add_argument("--override", nargs="*", default=[],
                        help="覆盖参数 key=value")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--tag", type=str, default="",
                        help="实验标签（用于输出目录命名）")
    return parser.parse_args()

def main():
    args = parse_args()
    cfg = load_config("configs", stage=args.stage,
                      ablation=args.ablation, overrides=args.override)
    if args.dataset:
        cfg.data.dataset = args.dataset
    if args.seed is not None:
        cfg.experiment.seed = args.seed

    # 构建输出目录
    output_dir = build_output_dir(cfg, args.stage, args.tag)

    # 保存配置快照
    save_config_snapshot(cfg, output_dir)

    # 执行训练 + 评估
    trainer = Trainer(cfg, output_dir)
    trainer.train()

    evaluator = Evaluator(cfg, output_dir)
    evaluator.evaluate()
```

---

## 5. 输出目录命名规范

```
results/{stage}_{dataset}_{tag}_{YYYYMMDD_HHMMSS}/
├── config.yaml          # 配置快照（完整合并后的配置）
├── train.log            # 训练日志
├── checkpoints/
│   ├── best.pt          # 最佳模型
│   └── last.pt          # 最后一个 epoch
├── metrics/
│   ├── train_history.json   # 每 epoch 的训练指标
│   └── test_results.json    # 测试集评估结果
├── predictions/
│   └── test_samples.npz     # 测试集预测样本
└── plots/                   # 可视化图表
```

命名示例：`results/S03_large_scale_ETTh1_baseline_20250317_143022/`

---

## 6. Trainer 规范（experiment/trainer.py）

### 必须包含的功能：

1. **tqdm 进度条**：外层 epoch 进度 + 内层 batch 进度
2. **时间戳日志**：每 epoch 输出所有 sub-loss 和指标
   ```
   [2025-03-17 14:30:22] Epoch 10/100 | loss=0.0234 | sub_loss_a=0.012 | sub_loss_b=0.011 | val_mse=0.045 | lr=8.2e-4
   ```
3. **JSON 历史**：每 epoch append 到 `metrics/train_history.json`
   ```json
   [
     {"epoch": 1, "loss": 0.15, "val_mse": 0.12, "lr": 0.001, "time": 23.4},
     {"epoch": 2, "loss": 0.10, "val_mse": 0.09, "lr": 0.001, "time": 22.8}
   ]
   ```
4. **Early Stopping**：基于验证集指标，patience + min_delta 可配置
5. **Checkpoint 保存**：best.pt（最佳验证指标）+ last.pt（每 epoch 覆盖）

---

## 7. Evaluator 规范（experiment/evaluator.py）

独立于 Trainer 的评估器，支持单独运行：

1. **加载最佳模型**：从 `checkpoints/best.pt` 加载
2. **采样生成**：在测试集上生成 N 个样本（N 由 eval.num_samples 控制）
3. **全指标计算**：计算所有配置中定义的指标
4. **输出**：
   - `metrics/test_results.json`：指标字典
   - `predictions/test_samples.npz`：预测样本数组

---

## 8. 消融实验编码

### 8.1 模型 enable_* 开关

模型定义中使用 `enable_*` 布尔开关控制组件：

```python
class MyModel(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.enable_component_a = cfg.enable_component_a
        self.enable_component_b = cfg.enable_component_b
        # ...

    def forward(self, x):
        if self.enable_component_a:
            x = self.component_a(x)
        else:
            x = self.fallback_a(x)  # 消融时的替代行为
        # ...
```

### 8.2 消融配置矩阵

每个消融变体一个 YAML 文件，只覆盖 enable_* 开关：

```yaml
# configs/ablations/no_component_a.yaml
model:
  enable_component_a: false
```

典型的消融矩阵：
| 变体 | component_a | component_b | component_c |
|------|:-----------:|:-----------:|:-----------:|
| full_model (baseline) | ✓ | ✓ | ✓ |
| no_component_a | ✗ | ✓ | ✓ |
| no_component_b | ✓ | ✗ | ✓ |
| no_component_c | ✓ | ✓ | ✗ |

---

## 9. Bash 脚本模板

### 9.1 run_stage.sh — 核心单次运行

```bash
#!/bin/bash
# 用法: bash scripts/run_stage.sh <stage> [dataset] [tag]
STAGE=${1:?"Usage: run_stage.sh <stage> [dataset] [tag]"}
DATASET=${2:-""}
TAG=${3:-""}

ARGS="--stage $STAGE"
[ -n "$DATASET" ] && ARGS="$ARGS --dataset $DATASET"
[ -n "$TAG" ] && ARGS="$ARGS --tag $TAG"

echo "=== Running: python run.py $ARGS ==="
python run.py $ARGS 2>&1 | tee "logs/${STAGE}_$(date +%Y%m%d_%H%M%S).log"
```

### 9.2 run_ablation.sh — 消融实验批量运行

```bash
#!/bin/bash
# 在所有数据集上运行所有消融变体
DATASETS=("dataset1" "dataset2" "dataset3")
ABLATIONS=($(ls configs/ablations/*.yaml | xargs -I{} basename {} .yaml))

# 先运行 baseline（无消融）
for ds in "${DATASETS[@]}"; do
    echo "=== Baseline on $ds ==="
    python run.py --stage S04_ablation --dataset "$ds" --tag baseline
done

# 运行各消融变体
for abl in "${ABLATIONS[@]}"; do
    for ds in "${DATASETS[@]}"; do
        echo "=== Ablation $abl on $ds ==="
        python run.py --stage S04_ablation --ablation "$abl" --dataset "$ds" --tag "abl_${abl}"
    done
done
```

### 9.3 run_sensitivity.sh — 超参数敏感度分析

```bash
#!/bin/bash
# 超参数敏感度扫描
PARAM_NAME=${1:?"Usage: run_sensitivity.sh <param> <values...>"}
shift
VALUES=("$@")

DATASET="default_dataset"

for val in "${VALUES[@]}"; do
    echo "=== Sensitivity: $PARAM_NAME=$val ==="
    python run.py --stage S07_sensitivity --dataset "$DATASET" \
        --override "$PARAM_NAME=$val" \
        --tag "sens_${PARAM_NAME}_${val}"
done
```

### 9.4 run_all.sh — 完整实验流程

```bash
#!/bin/bash
# 完整实验流程: S01 -> S07
set -e

echo "=== S01: Quick Test ==="
bash scripts/run_stage.sh S01_quick_test

echo "=== S02: Small Scale ==="
bash scripts/run_stage.sh S02_small_scale

echo "=== S03: Large Scale (all datasets) ==="
for ds in dataset1 dataset2 dataset3; do
    bash scripts/run_stage.sh S03_large_scale "$ds"
done

echo "=== S04: Ablation ==="
bash scripts/run_ablation.sh

echo "=== S05: Long Term ==="
bash scripts/run_stage.sh S05_long_term

echo "=== S06: Efficiency ==="
bash scripts/run_stage.sh S06_efficiency

echo "=== S07: Sensitivity ==="
bash scripts/run_sensitivity.sh model.param_name 0.1 0.2 0.5 1.0 2.0 5.0

echo "=== All stages complete ==="
```

---

## 10. 可视化模块（visualize/）

### 5 个标准可视化模块：

1. **training_curves.py** — 训练曲线
   - 总 loss 曲线 + 各 sub-loss 分解
   - 训练/验证指标对比
   - 学习率变化曲线

2. **trajectory_plots.py** — 轨迹/预测图
   - 生成样本 vs 真实值
   - 置信区间带（50%、90%）
   - 多步预测展示

3. **variance_analysis.py** — 方差分析
   - 指标 vs 预测步长（Horizon）变化
   - 不同模型/配置的方差对比

4. **ablation_table.py** — 消融结果
   - LaTeX 格式表格（适合论文）
   - 柱状图对比各变体 vs baseline 的指标差异（delta）
   - 自动标注最佳值

5. **sensitivity_heatmap.py** — 敏感度热力图
   - 指标 vs 超参数值的热力图
   - 支持多指标并排展示

### 通用要求：
- 所有图表使用 matplotlib，统一风格
- 支持从命令行独立运行：`python -m visualize.training_curves --results_dir <path>`
- 输出保存到对应的 `plots/` 目录
