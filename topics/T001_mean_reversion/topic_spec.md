# 生成式时序预测中的均值回归问题

## 领域
time_series_forecasting

## 关键词
- mean reversion generative time series
- distribution collapse flow matching
- diffusion model time series prediction
- probabilistic forecasting sharpness

## 描述
研究生成式时序预测模型（如基于 Flow Matching 的 Sundial/TimeFlow）在长期预测中出现的均值回归/分布塌缩现象，探索改进方法。

核心问题：生成式模型（Diffusion、Flow Matching）在时序预测任务中，随着预测步长增加，预测分布趋于退化为均值附近的窄分布，丧失了概率预测的多样性和校准性。

也可能是因为encode部分信息提取时，多层自注意力平均掉了高频部分，如何重新注入也是一个办法。或者使用decoder only可以免于这个问题？

## 范围
- 较多考虑生成式模型，若有好的非生成式模型思路也可以
