# [F03] Agent 基座（ReAct 循环）

## 状态

- **实现状态**：✅已完成
- **核心文件**：
  - `agents/base_agent.py:34` — `BaseAgent`，ReAct 循环核心（推理→工具调用→观察→继续）
  - `agents/base_agent.py:19` — `llm_call_with_retry()`，指数退避重试（2s/4s/8s）
  - `agents/base_agent.py:58` — `register_tool()`，Pydantic schema 工具注册 + PathGuard 路径白名单包装
  - `agents/base_agent.py:81` — `_compress_messages()`，历史消息压缩（保留首尾，中间摘要化）
- **功能描述**：所有工作 Agent 的基类。通过 Anthropic SDK 兼容接口调用 MiniMax M2.5。工具注册支持 Pydantic BaseModel（推荐）和 dict（兼容）。写操作自动经过 PathGuard 路径校验。消息历史超过 150K 字符时自动压缩。并行工具调用（ThreadPoolExecutor，最多 8 线程）。自动注册全局 `search_knowledge_base` 工具。
- **测试方法**：
  ```python
  from agents.base_agent import BaseAgent
  agent = BaseAgent("test", "You are a test agent.")
  # 需要配置 MINIMAX_API_KEY
  ```

## 建议

（暂无）

## 变化

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)

<details><summary>详情</summary>

**计划**：建立 Agent 基座，支持 ReAct 循环、工具注册、消息压缩
**代码修改**：新增 agents/base_agent.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>
