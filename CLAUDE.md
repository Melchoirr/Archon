# Archon — AI 驱动的科研自动化系统

## 项目概要
三层架构：入口层(run_research.py) → 编排层(Orchestrator + FSM) → 执行层(11 Agent + 20 Tool)
核心模式：ReAct 循环、FSM 状态机、Pydantic 全链路类型校验
主力 LLM：MiniMax M2.5 (200K ctx, Anthropic SDK 兼容接口)

## 文档体系
开始工作前，阅读相关文档以了解当前状态：
- `record/project/architecture.md` — 模块结构和数据流
- `record/project/todo.md` — 当前任务优先级
- `record/project/issues.md` — 已知问题
- `record/project/decisions.md` — 设计决策(ADR)
- `record/project/changelog.md` — 变更历史

完成变更后，必须自动执行 `/update-docs` 更新相关文档并提交 commit（无需用户提醒）。
Hook 会自动 `git add` 每个编辑的文件，文档更新完成后执行 `git commit`。

## 行为规则（基于 Insights 分析）
1. 收到计划/规范时，嵌入为模板或规则供 Agent 系统使用，不要直接实现代码（除非明确要求）
2. 实现外部 API 集成前，先向用户确认 API 文档和签名，不要猜测端点或参数
3. 执行编号计划时按顺序推进到代码变更，不要停留在探索/分析阶段
4. 生成 Python 代码前验证库的 import 路径和 API 签名
5. 修复 Bug 时严格限定范围，不添加未请求的功能或重构
6. Python 模板中 `.format()` 注意花括号转义（含 `{idea_id}` 等模板变量时用双花括号或 string.Template）
