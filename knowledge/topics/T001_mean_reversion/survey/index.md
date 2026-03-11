# 论文索引

## 核心论文

| 序号 | 论文标题 | 作者 | 年份 | 会议/期刊 | 引用数 | 论文ID |
|------|----------|------|------|------------|--------|--------|
| 1 | Sundial: A Family of Highly Capable Time Series Foundation Models | Liu et al. | 2025 | ICML | - | 280c58271770030e5d4d15ca5531f75ba2a5aba0 |
| 2 | Timer-S1: A Billion-Scale Time Series Foundation Model with Serial Scaling | - | 2025 | - | - | - |
| 3 | The Rise of Diffusion Models in Time-Series Forecasting | - | 2023 | arXiv | - | - |
| 4 | MMPD: Diverse Time Series Forecasting via Multi-Mode Patch Diffusion | - | 2024 | - | - | - |
| 5 | Flow Matching with Gaussian Process Priors for Probabilistic Time Series Forecasting | - | 2024 | - | - | - |
| 6 | Conditional Guided Flow Modeling | - | 2024 | - | - | - |
| 7 | Lag-Llama: Towards Foundation Models for Probabilistic Time Series Forecasting | - | 2023 | - | - | - |

## 评估基准论文

| 序号 | 论文标题 | 作者 | 年份 | 论文ID |
|------|----------|------|------|--------|
| 8 | GIFT-Eval: A Benchmark for General Time Series Forecasting Model Evaluation | - | 2024 | 2410.10393 |
| 9 | Unified Long-Term Time-Series Forecasting Benchmark | - | 2023 | 2309.15946 |
| 10 | TimeBench | - | 2024 | - |

## 详细论文总结

### 核心论文总结

#### 1. Sundial

- **概述**: 时间序列基础模型家族，使用 TimeFlow Loss 进行概率预测
- **关键创新**: Flow Matching + Patch-level 处理
- **解决的问题**: Mode collapse，分布塌缩
- **相关链接**: 
  - [arXiv](https://arxiv.org/abs/2502.00816)
  - [GitHub](https://github.com/thuml/Sundial)
  - [HuggingFace](https://huggingface.co/thuml/sundial-base-128m)

#### 2. Timer-S1

- **概述**: 十亿级时间序列基础模型
- **关键创新**: 后训练阶段，长上下文扩展
- **数据集**: TimeBench

#### 3. Diffusion Models Survey

- **概述**: 扩散模型在时间序列预测中的综述
- **内容**: 条件生成机制、当前 SOTA、未来方向

#### 4. MMPD

- **概述**: 多模态 patch 扩散模型
- **关键创新**: Patchified forecaster + Patch-Consistent MLP

#### 5. TSFlow

- **概述**: 高斯过程先验的流匹配模型
- **关键创新**: 领域特定先验

## 引用关系

### Sundial 引用

- TimeFlow Loss (核心创新)
- Patch-level processing
- TimeBench dataset

### 重要引用链

```
Sundial (2025)
├── Flow Matching
│   ├── TimeFlow Loss
│   └── Patch-level Processing
├── TimeBench Dataset
└── Zero-shot Forecasting

Diffusion Models (2023)
├── Conditional Generation
├── DDPM/DDIM
└── Time Series Applications

GIFT-Eval (2024)
├── 28 Datasets
├── 7 Domains
└── Zero-shot Evaluation
```

## 后续调研计划

1. 深入阅读 Sundial 论文细节
2. 搜索更多关于 mode collapse 的论文
3. 探索 Decoder-only vs Encoder-Decoder 架构对比
4. 查找更多关于评估指标的论文
