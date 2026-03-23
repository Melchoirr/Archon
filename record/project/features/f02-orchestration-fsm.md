# [F02] 编排引擎与 FSM 状态机

## 状态
- **实现状态**：✅已完成

## 核心文件
- `agents/orchestrator.py:39-84` — `ResearchOrchestrator.__init__()`，初始化 PathManager / TreeService / KB / ContextManager
- `agents/orchestrator.py:118-157` — `phase_elaborate()`，展开研究背景
- `agents/orchestrator.py:159-304` — `phase_survey()`，5 步文献调研管道
- `agents/orchestrator.py` — `phase_ideation()`, `phase_refine()`, `phase_code_reference()`, `phase_code()`, `phase_theory_check()`, `phase_debug()`, `phase_experiment()`, `phase_analyze()`, `phase_conclude()`
- `agents/fsm_engine.py:27-74` — FSM 常量（MAX_RETRIES、TOPIC_TRANSITIONS、IDEA_LINEAR_TRANSITIONS、USER_CONFIRM_TRANSITIONS）
- `agents/fsm_engine.py:77-88` — `ResearchFSM.__init__()`，懒加载评估器
- `agents/fsm_engine.py:105-148` — `run_topic()`，Topic 级 FSM 循环
- `agents/fsm_engine.py:150-225` — `run_idea()`，Idea 级 FSM 循环
- `agents/fsm_engine.py:227-284` — `step()`，单步状态转换
- `agents/fsm_engine.py:438-580` — 评估路由（`_route_analysis`, `_route_theory_check`(含 derivative), `_route_debug`）
- `agents/fsm_engine.py` — `_gather_other_ideas_summary()`，跨 idea 摘要收集

## 功能描述
系统的中枢控制层，包含两个核心组件：

**ResearchOrchestrator**：阶段执行引擎
- 组装上下文（`ContextManager.build_context()`）
- 创建专用 Agent（配置工具、迭代上限、allowed_dirs）
- 调用 Agent.run() 执行 ReAct 循环
- 记录阶段日志（`phase_logger`）+ 上传产物到知识库

**ResearchFSM**：有限状态机
- Topic 级：elaborate → survey → ideation → completed
- Idea 级：refine → theory_check → code_reference → code → debug → experiment → analyze → conclude
- 评估器驱动的非线性转换（回退、重试）
- 每状态最大重试次数防止死循环
- 状态快照持久化到 `fsm_state.yaml`

**关键数据结构**：
- `FSMSnapshot`（`shared/models/fsm.py:124`）：topic_state + idea_states + transition_history
- `IdeaFSMState`（`shared/models/fsm.py:115`）：current_state + step_id + version + retry_counts + feedback
- `TransitionRecord`（`shared/models/fsm.py:104`）：timestamp + from/to state + trigger + decision_snapshot

## 运行流程

### 触发条件
- 手动模式：CLI cmd_* → `_get_orchestrator()` 获取实例
- FSM 模式：CLI `cmd_fsm()` → `_get_fsm()` → `fsm.run_topic()` 或 `fsm.run_idea()`

### 处理步骤
1. **初始化** — 创建 PathManager、TreeService、KnowledgeBaseManager、ContextManager
2. **阶段执行**（Orchestrator）— 创建对应 Agent，传入上下文和工具集，调用 Agent.run()
3. **状态评估**（FSM）— 阶段完成后调用评估器，获取结构化 verdict
4. **状态转换**（FSM）— 根据 verdict 决定下一状态，记录 TransitionRecord，更新 FSMSnapshot
5. **重试管理**（FSM）— retry_counts 跟踪，达到 MAX_RETRIES 时暂停

### 输出
- Orchestrator：各阶段产物（context.md, survey/, ideas/, results/ 等）
- FSM：状态转换历史、fsm_state.yaml

### 依赖关系
- **上游**：F01（CLI 创建实例）
- **下游**：F03-F12（所有 Agent 和工具）

### 错误与边界情况
- FSM 重试上限（refine:4, theory_check:3, debug:6, experiment:6, survey:4）
- retry_count 递增当前状态（评估器用 state 的 count 判断重试上限）
- 回退转换（theory_check→refine, analyze→refine, debug→refine）需用户确认
- `force_transition()` 手动跳转到任意状态（附带 feedback）
- Topic 目录不存在时自动发现最新 topic

## 测试方法
```bash
python run_research.py fsm status --topic T001
python run_research.py fsm history --topic T001
python run_research.py elaborate --topic T001
```

## 建议
（暂无）

## 变化
### [修改] 2026-03-23 — refine feedback 改为文件路径方式
- **目的**：去掉 feedback 字符串传递，改为让 RefinementAgent 自行读取 theory_review.md 获取完整审查信息
- **改动**：`orchestrator.py` `phase_refine()` 移除 feedback 参数，改为检测 theory_review.md 是否存在并传路径；`refinement_agent.py` `build_prompt()` 移除 feedback 参数，改为 theory_review_path；`fsm_engine.py` refine 调用不再传 feedback
- **验证**：import 通过

### [修复] 2026-03-23 — FSM retry_count 递增错误 + theory_check→refine 缺少用户确认 (`069d579`)
- **目的**：修复 theory_check↔refine 死循环：retry_count 递增了 next_state 而非 current_state 导致上限不生效；theory_check→refine 不在 USER_CONFIRM_TRANSITIONS 中导致自动循环无干预
- **改动**：`fsm_engine.py` 行 201+256 `retry_counts[next_state]` → `retry_counts[state]`；USER_CONFIRM_TRANSITIONS 新增 `("theory_check", "refine")`
- **验证**：未测试

### [修改] 2026-03-23 — FSM 路由增加 derivative verdict + 跨 idea 上下文 + refine feedback 传递 (`535b346`)
- **目的**：支持 TheoryEvaluator 新增的 derivative 判定；为评估器提供同 batch 其他 idea 摘要；refine 回退时传递评估 feedback
- **改动**：`fsm_engine.py` `_route_theory_check()` 增加 derivative 分支（→ refine 或 abandon）；`_gather_theory_eval_context()` 增加 other_ideas_summary；新增 `_gather_other_ideas_summary()` 方法；`_execute_idea_state("refine")` 传递 `feedback=idea_fsm.feedback`。`orchestrator.py` `phase_refine()` 签名增加 feedback 参数并传递给 RefinementAgent
- **验证**：import 通过

### [修复] 2026-03-23 — phase_ideation 传入 topic_dir (`d081a7c`)
- **目的**：确保 IdeationAgent 的 idea_graph 工具写入正确的 topic 目录
- **改动**：orchestrator.py `phase_ideation()` 创建 IdeationAgent 时传入 `topic_dir=self.topic_dir`
- **验证**：未测试

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
- **目的**：实现编排引擎和 FSM 状态机
- **改动**：新增 orchestrator.py + fsm_engine.py
- **验证**：未测试

### [重构] 2026-03-17 10:38 — FSM 引擎重构 + 评估器体系 (`b6b5ff6`)
- **目的**：拆分评估逻辑为独立评估器，新增 venv 隔离和 EDA 支持
- **改动**：fsm_engine.py 重构路由逻辑，引入 3 个评估器
- **验证**：未测试

### [修复] 2026-03-21 11:07 — FSM 跨状态回退死循环修复 (`f4aaf7a`)
- **目的**：修复 retry_counts 无条件递增导致的死循环 + step() 方法补齐
- **改动**：fsm_engine.py 修正 retry_counts 逻辑，补齐 step() 支持单步执行
- **验证**：未测试
