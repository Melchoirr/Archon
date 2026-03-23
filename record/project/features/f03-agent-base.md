# [F03] Agent 基座（ReAct 循环）

## 状态
- **实现状态**：✅已完成

## 核心文件
- `agents/base_agent.py:19-31` — `llm_call_with_retry()`，指数退避重试（2s/4s/8s）
- `agents/base_agent.py:34-56` — `BaseAgent.__init__()`，初始化 MiniMax 客户端、PathGuard、自动注册 KB 搜索
- `agents/base_agent.py:58-79` — `register_tool()`，工具注册（Pydantic schema + PathGuard 包装）
- `agents/base_agent.py:81-118` — `_compress_messages()`，消息压缩（150K 字符上限）
- `agents/base_agent.py:120-218` — `run()`，ReAct 循环核心
- `agents/base_agent.py:220-222` — `get_message_history()`

## 功能描述
所有专用 Agent 的基类，实现 ReAct（Reasoning + Acting）循环。

- **ReAct 循环**：推理 → 调用工具 → 观察结果 → 继续推理，直到完成或达迭代上限
- **工具注册**：Pydantic 模型自动转 JSON Schema，PathGuard 包装写操作
- **并行工具执行**：ThreadPoolExecutor(max_workers=8) 并行执行同轮多工具调用
- **消息压缩**：超 150K 字符时保留首条 + 最近 12 条 + 中间摘要
- **LLM 重试**：指数退避 3 次（APIConnectionError, RateLimitError, InternalServerError）
- **紧急提示**：剩余≤5 次迭代时注入催促消息

**LLM 配置**：MiniMax M2.5（200K context），Anthropic SDK 兼容接口，默认 max_tokens=8192

## 运行流程

### 触发条件
- 被子类继承，Orchestrator 创建实例后调用 `agent.run(prompt)`

### 处理步骤
1. **初始化** — 创建 Anthropic 客户端（MiniMax 端点）、设置 system_prompt、注册 KB 搜索
2. **子类注册工具** — 子类 `__init__` 调用 `self.register_tool()` 注册专用工具
3. **run() 循环**（最多 max_iterations 次）：
   - `_compress_messages()` 检查并压缩历史
   - `llm_call_with_retry()` 调用 LLM
   - 提取 text 块和 tool_use 块
   - Pydantic 校验参数 → 执行 handler → 收集结果（并行）
   - 工具结果追加到消息历史
4. **收敛** — LLM 不再调用工具则返回最终文本

### 输出
- 最终文本输出
- 消息历史（`get_message_history()`）

### 依赖关系
- **上游**：F02（Orchestrator 创建实例）
- **下游**：所有专用 Agent（F05-F09）继承此基类

### 错误与边界情况
- API 连接错误：指数退避重试 3 次
- Pydantic 校验失败：返回错误信息给 LLM（不中断）
- 工具异常：捕获 Exception，返回错误文本给 LLM
- 迭代上限：返回 "unable to complete" 提示

## 测试方法
```python
from agents.base_agent import BaseAgent
agent = BaseAgent("test", "You are a test agent.")
# 需配置 MINIMAX_API_KEY
```

## 建议
（暂无）

## 变化
### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
- **目的**：实现通用 ReAct 循环基座
- **改动**：新增 base_agent.py（222 行）
- **验证**：未测试
