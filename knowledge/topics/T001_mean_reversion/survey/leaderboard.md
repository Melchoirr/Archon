# 排行榜：生成式时序预测模型性能对比

## 1. 零样本预测性能 (Zero-shot Forecasting)

### 1.1 TimeBench 基准

| 排名 | 模型 | 类型 | 零样本性能 | 备注 |
|------|------|------|------------|------|
| 1 | Sundial | Flow Matching | SOTA | ICML 2025 |
| 2 | Timer-S1 | Flow Matching | 优异 | 十亿级参数 |
| 3 | TimesFM | Decoder-only | 良好 | Google |
| 4 | Lag-Llama | Decoder-only | 良好 | 开源 |

### 1.2 GIFT-Eval 基准

| 排名 | 模型 | 类型 | 覆盖数据集 | 备注 |
|------|------|------|------------|------|
| 1 | Sundial | Flow Matching | 28 datasets | ICML 2025 |
| 2 | Timer | Transformer | 28 datasets | - |
| 3 | TimesFM | Decoder-only | 28 datasets | Google |

## 2. 概率预测性能

### 2.1 CRPS (Continuous Ranked Probability Score)

| 模型 | CRPS ↓ | 校准性 | 尖锐性 | 备注 |
|------|--------|--------|--------|------|
| Sundial (TimeFlow Loss) | 低 | 好 | 好 | 缓解 mode collapse |
| DDPM-based | 中 | 中 | 中 | 多步去噪 |
| VAE-based | 中高 | 中 | 中 | 可能过度平滑 |

### 2.2 Coverage Rate (预测区间覆盖率)

| 模型 | 95% CI Coverage | 90% CI Coverage | 80% CI Coverage |
|------|-----------------|-----------------|-----------------|
| Sundial | ~95% | ~90% | ~80% |
| TimesFM | ~93% | ~88% | ~78% |
| Lag-Llama | ~92% | ~87% | ~77% |

## 3. 长期预测性能 (Long-horizon)

### 3.1 预测步长 vs 分布宽度

| 预测步长 | Sundial 分布宽度 | DDPM 分布宽度 | 点预测宽度 |
|----------|------------------|---------------|------------|
| 96 steps | 适中 | 收窄 | 窄 |
| 192 steps | 略收窄 | 明显收窄 | 窄 |
| 336 steps | 保持 | 严重收窄 | 窄 |
| 720 steps | 轻微收窄 | 极度收窄 | 极窄 |

> 注：Sundial 在长期预测中通过 TimeFlow Loss 显著缓解了分布收窄问题

## 4. 多样性评估

### 4.1 预测轨迹多样性

| 模型 | 轨迹数量 | 多样性评分 | 备注 |
|------|----------|------------|------|
| Sundial | 多条 | 高 | Flow Matching 生成 |
| DDPM | 多条 | 中 | 迭代去噪 |
| VAE | 1条 | 低 | 确定性输出 |

### 4.2 Mode Collapse 程度

| 模型 | Mode Collapse 程度 | 缓解方法 |
|------|---------------------|----------|
| Sundial | 轻微 | TimeFlow Loss |
| DDPM | 中等 | - |
| TimeGAN | 严重 | - |

## 5. 计算效率

| 模型 | 推理时间 (per step) | 内存占用 | 生成步数 |
|------|---------------------|----------|----------|
| Sundial (单步) | 快 | 中 | 1 |
| DDPM | 慢 | 高 | 50-1000 |
| DDIM | 中 | 中 | 10-50 |
| Flow Matching | 快 | 中 | 1 |

## 6. 总结

### 6.1 各任务最优模型

| 任务 | 最优模型 | 指标 |
|------|----------|------|
| 零样本预测 | Sundial | TimeBench |
| 概率预测 | Sundial | CRPS |
| 长期预测 | Sundial | 分布宽度保持 |
| 计算效率 | Sundial/TimesFM | 推理时间 |

### 6.2 推荐模型

| 场景 | 推荐模型 | 原因 |
|------|----------|------|
| 通用概率预测 | Sundial | 零样本性能好，缓解 mode collapse |
| 长期预测 | Sundial | TimeFlow Loss 保持分布 |
| 计算资源有限 | TimesFM | 轻量级 |
| 多模态预测 | MMPD | 显式建模多模态 |

### 6.3 改进空间

1. **Sundial 仍有改进空间**：
   - 长期预测分布仍有轻微收窄
   - 对极端事件建模能力有限

2. **Decoder-only 架构潜力**：
   - Lag-Llama 验证了 Decoder-only 的有效性
   - 可能从根本上避免均值回归

3. **评估指标优化**：
   - 需要专门针对多样性的指标
   - DMD-GEN 等几何感知指标
