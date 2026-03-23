# Archon — AI 驱动的科研自动化系统

## 项目概要
三层架构：入口层(run_research.py) → 编排层(Orchestrator + FSM) → 执行层(11 Agent + 20 Tool)
核心模式：ReAct 循环、FSM 状态机、Pydantic 全链路类型校验
主力 LLM：MiniMax M2.5 (200K ctx, Anthropic SDK 兼容接口)

## 文档体系
开始工作前阅读相关文档了解当前状态：
- `record/project/index.md` — 功能索引总览（状态、时间、维护情况）
- `record/project/features/` — 各功能详情文件（状态 + 变化历史）
- `record/project/workflow.md` — 开发工作流方法论

### Skill 使用
- `/catch-up` — 初始化文档或追赶落后的文档状态（扫描代码+git→生成/更新所有文档）
- `/update-docs` — 日常文档更新（Plan阶段标记计划，Execute阶段根据diff记录实现）
- `/audit` — 审计未测试区域和潜在问题，输出优先级排序的待办清单
- `/suggest` — 为功能生成增量改进建议，用户决定采纳或否决

完成变更后，必须自动执行 `/update-docs` 更新相关文档并提交 commit（无需用户提醒）。
Hook 会自动 `git add` 每个编辑的文件，文档更新完成后执行 `git commit`。

## 行为规则（基于 Insights 分析）
1. 收到计划/规范时，嵌入为模板或规则供 Agent 系统使用，不要直接实现代码（除非明确要求）
2. 实现外部 API 集成前，先向用户确认 API 文档和签名，不要猜测端点或参数
3. 执行编号计划时按顺序推进到代码变更，不要停留在探索/分析阶段
4. 生成 Python 代码前验证库的 import 路径和 API 签名
5. 修复 Bug 时严格限定范围，不添加未请求的功能或重构
6. Python 模板中 `.format()` 注意花括号转义（含 `{idea_id}` 等模板变量时用双花括号或 string.Template）
