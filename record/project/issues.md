# 已知问题和 Bug 跟踪

## 格式说明

| 字段 | 说明 |
|------|------|
| ID | `#001` 递增 |
| 状态 | 🔴 Open / 🟡 In Progress / 🟢 Resolved |
| 优先级 | P0（紧急）/ P1（高）/ P2（中）/ P3（低） |

---

## #001 — Memory 系统内容未填充

- **状态**：🔴 Open
- **优先级**：P2
- **描述**：`memory/experience_log.yaml`、`memory/failed_ideas.md`、`memory/insights.md` 目前为空或仅含模板结构，尚未有实际经验记录写入。memory.py 工具已实现 `query_memory()` 和 `add_experience()` 接口，但缺少实际调用验证。
- **发现日期**：2026-03-19
- **相关文件**：`memory/`, `tools/memory.py`

## #002 — 缺少统一的错误处理和重试机制

- **状态**：🔴 Open
- **优先级**：P2
- **描述**：各 Agent 和工具模块的异常处理分散，LLM API 调用缺乏统一的重试/降级策略。网络请求（OpenAlex、Zhipu、DuckDuckGo）失败时的恢复逻辑不一致。
- **发现日期**：2026-03-19
- **相关文件**：`agents/base_agent.py`, `tools/openalex.py`, `tools/paper_manager.py`, `tools/knowledge_base.py`

## #003 — 测试覆盖为零

- **状态**：🔴 Open
- **优先级**：P1
- **描述**：项目无任何单元测试或集成测试。核心组件（FSM 引擎、ResearchTree CRUD、Evaluator 解析）缺少自动化验证。
- **发现日期**：2026-03-19
- **相关文件**：项目根目录（无 tests/ 目录）

## #004 — embedding.py 为新增未提交文件

- **状态**：🟡 In Progress
- **优先级**：P3
- **描述**：`tools/embedding.py` 作为 untracked 文件存在，已被 idea_scorer.py 引用但尚未纳入版本控制。
- **发现日期**：2026-03-19
- **相关文件**：`tools/embedding.py`, `tools/idea_scorer.py`

## #005 — ideas/ 和 record/ 目录未纳入版本控制

- **状态**：🔴 Open
- **优先级**：P3
- **描述**：`ideas/` 和 `record/` 目录为 untracked 状态，需要决定哪些内容应被版本控制，哪些应加入 `.gitignore`。
- **发现日期**：2026-03-19
- **相关文件**：`ideas/`, `record/`, `.gitignore`

## #006 — Survey 辅助函数大规模重构中

- **状态**：🟡 In Progress
- **优先级**：P1
- **描述**：`survey_helpers.py` 有 186 行未提交改动，涉及 survey 管道全部步骤的重构。需确保重构后与 orchestrator 和 FSM 引擎的衔接正确。
- **发现日期**：2026-03-19
- **相关文件**：`agents/survey_helpers.py`, `agents/orchestrator.py`, `agents/fsm_engine.py`

## #008 — FSM 跨状态回退死循环

- **状态**：🟢 Resolved
- **优先级**：P0
- **描述**：`retry_counts` 仅在 same-state 转换时递增，跨状态回退循环（如 refine→theory_check→refine）的计数永远为 0，导致永远不触发重试上限。`step()` 方法完全不更新 `retry_counts`，问题更严重。修复方式：无条件递增 `retry_counts[next_state]`，`step()` 补充 retry + feedback 逻辑，MAX_RETRIES +1 补偿首次进入。
- **发现日期**：2026-03-21
- **解决日期**：2026-03-21
- **相关文件**：`agents/fsm_engine.py`

## #007 — 上下文窗口管理的 40KB 截断可能丢失关键信息

- **状态**：🔴 Open
- **优先级**：P2
- **描述**：`context_manager.py` 对每个注入文件做 40KB 截断，对于大型 survey 文档或代码文件，可能截断关键内容。缺乏智能截断策略（如按相关性摘要）。
- **发现日期**：2026-03-19
- **相关文件**：`tools/context_manager.py`
