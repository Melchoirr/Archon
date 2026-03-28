# [F02] 编排引擎与 FSM 状态机

## 状态
- **实现状态**：✅已完成

## 核心文件
- `agents/orchestrator.py` — `ResearchOrchestrator`，初始化 PathManager / IdeaRegistryService / KB / ContextManager；`phase_*()` 方法编排各阶段
- `agents/fsm_engine.py` — `ResearchFSM`，FSM 引擎（不再依赖 ResearchTreeService）
  - 常量：MAX_RETRIES、TOPIC_TRANSITIONS、IDEA_LINEAR_TRANSITIONS、USER_CONFIRM_TRANSITIONS
  - 核心方法：`run_topic()`, `run_idea()`, `step()`, `force_transition()`, `status()`, `history()`
  - 持久化：`_persist_snapshot()`（原子写入）、`_load_snapshot()`、`_recover_from_filesystem()`
  - 审计：`_record_transition()` → 写 `audit_log.yaml`（唯一写入点）
  - 评估路由：`_route_analysis`, `_route_theory_check`, `_route_debug` — 纯质量评估
- `shared/models/fsm.py` — `FSMState`, `IdeaFSMState`, `FSMSnapshot`（精简版，仅恢复数据）
- `shared/models/audit.py` — `TransitionRecord`（精简版，verdict_summary 替代 decision_snapshot）
- `shared/models/decisions.py` — `AnalysisDecision`, `TheoryDecision`, `SurveyDecision`, `DebugDecision`（含 `to_summary()` 方法）
- `shared/models/idea_registry.py` — `TopicMeta`, `IdeaEntry`, `IdeaRegistry`, `Score`, `Relationship`
- `tools/idea_registry.py` — `IdeaRegistryService`，Idea 元数据 CRUD + `read_research_status()` 合并视图

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
- 评估器驱动的非线性转换（回退、重试）；`need_literature` verdict 路由到 refine（由 refine agent 搜索补充论文）
- **两种运行模式**：interactive（默认，用户确认回退转换，无重试限制）/ auto（跳过确认，MAX_RETRIES 控制上限）
- 路由方法纯做质量评估，重试策略由上层按模式决定
- 状态快照持久化到 `fsm_state.yaml`

**三文件分离架构**（替代旧 research_tree + FSM 双轨制）：
- `fsm_state.yaml` — 恢复数据：`FSMSnapshot`（topic_state + idea_states，~15 行）
- `idea_registry.yaml` — Idea 元数据：`IdeaRegistry`（scores/category/relationships）
- `audit_log.yaml` — 流转记录：`TransitionRecord` 列表（精简摘要，用户可通览）

**关键数据结构**：
- `FSMSnapshot`（`shared/models/fsm.py`）：schema_version + topic_state + topic_retry_counts + idea_states
- `IdeaFSMState`（`shared/models/fsm.py`）：current_state + step_id + version + retry_counts（无 feedback，运行时内存传递）
- `TransitionRecord`（`shared/models/audit.py`）：timestamp + from/to state + trigger + verdict_summary（一行摘要）
- `*Decision`（`shared/models/decisions.py`）：评估器产出，含 `to_summary()` 方法

## 运行流程

### 触发条件
- 手动模式：CLI cmd_* → `_get_orchestrator()` 获取实例
- FSM 模式：CLI `cmd_fsm()` → `_get_fsm()` → `fsm.run_topic()` 或 `fsm.run_idea()`

### 处理步骤
1. **初始化** — 创建 PathManager、IdeaRegistryService、KnowledgeBaseManager、ContextManager
2. **阶段执行**（Orchestrator）— 创建对应 Agent，传入上下文和工具集，调用 Agent.run()
3. **状态评估**（FSM）— 阶段完成后调用评估器，获取结构化 verdict
4. **状态转换**（FSM）— 根据 verdict 决定下一状态，记录 TransitionRecord 到 audit_log.yaml，更新 FSMSnapshot
5. **重试管理**（FSM）— retry_counts 跟踪；auto 模式达到 MAX_RETRIES 时自动 abandon；interactive 模式由用户在确认环节决定

### 输出
- Orchestrator：各阶段产物（context.md, survey/, ideas/, results/ 等）
- FSM：fsm_state.yaml（恢复快照）、audit_log.yaml（流转记录）

### 依赖关系
- **上游**：F01（CLI 创建实例）
- **下游**：F03-F12（所有 Agent 和工具）

### 错误与边界情况
- auto 模式重试上限（refine:4, theory_check:3, debug:6, experiment:6, survey:4），interactive 模式不限制
- retry_count 递增当前状态，仅 auto 模式用于上限判断
- interactive 模式下回退转换（theory_check→refine, analyze→refine, debug→refine）需用户确认，无效输入重新提示
- `force_transition()` 手动跳转到任意状态（附带 feedback）
- Topic 目录不存在时自动发现最新 topic
- `_mark_idea_abandoned()` 通过 `IdeaRegistryService.update_idea_status()` 更新
- FSM 快照原子写入（tempfile + os.replace），防止半写损坏
- `_recover_from_filesystem()` 从产出文件推断状态（不依赖 research_tree）

## 测试方法
```bash
python run_research.py fsm status --topic T001
python run_research.py fsm history --topic T001
python run_research.py elaborate --topic T001
```

## 建议
（暂无）

## 变化
### [实现] 2026-03-28 09:43 — research 子仓库自动 commit (`b8e512e`)
- **目的**：research/ 有独立 git repo 但从未自动 commit，需在每个 agent/phase 完成后自动提交产出物
- **改动**：`agents/orchestrator.py` — 新增 `_commit_research(phase, idea_id, detail, version)` 方法，委托 `shared/utils/research_git.py`；在 `phase_survey()` 6 个子步骤 + 其他 10 个 `phase_*()` 方法中各插入 1 次调用（共 16 处）
- **验证**：`commit_research()` 成功在 research repo 创建 commit，`git -C research log` 确认

### [修复] 2026-03-28 00:57 — Orchestrator 新增 idea 兜底注册逻辑 (`b8e512e`)
- **目的**：配合 F06 修复，在评分前自动补注册未被 IdeationAgent 注册的 idea
- **改动**：`agents/orchestrator.py` — 新增 `_backfill_unregistered_ideas(ideas_dir)` 方法，扫描 ideas 目录匹配 `I\d+_*` 模式，对比 registry 已注册 ID，从 proposal.md 提取标题后调用 `registry.add_idea()` 补注册；在 `phase_ideation()` 评分前调用
- **验证**：import 通过

### [重构] 2026-03-26 19:09 — 移除 deep_survey 状态，need_literature 改路由到 refine (`3bed669`)
- **目的**：deep_survey 实质是完整 survey 重跑，与 refine 的补充文献搜索重叠且不传递 analyze 反馈，删除该状态简化 FSM
- **改动**：
  - `shared/models/fsm.py` — 删除 `FSMState.deep_survey` 枚举值
  - `agents/fsm_engine.py` — 删除 TOPIC_TRANSITIONS/USER_CONFIRM_TRANSITIONS/TOPIC_OPTIONS/IDEA_OPTIONS/dispatch 中的 deep_survey 引用；`_execute_topic_state` 不再匹配 deep_survey；`_route_analysis` 中 `need_literature` 从 `deep_survey` 改路由到 `refine`
  - `agents/orchestrator.py` — 删除 `phase_deep_survey()` 方法
  - `agents/evaluators/analysis_evaluator.py` — 更新 need_literature 描述说明新行为
- **验证**：三个模块 import 通过

### [重构] 2026-03-26 16:53 — Orchestrator 消除硬编码路径，统一使用 PathManager (`cd282c6`)
- **目的**：消除 orchestrator.py 中所有硬编码 `os.path.join(self.project_root, "knowledge", ...)` 的 fallback 模式，统一走 `self.paths.*` 属性
- **改动**：
  - `agents/orchestrator.py` — 移除 6 处 `if self.topic_dir ... else os.path.join(...)` fallback 分支（phase_elaborate、phase_survey、phase_ideation 中 context_md/survey_dir/baselines_md/datasets_md/metrics_md/survey_md/ideas_dir）；1 处错误路径 `os.path.join(self.project_root, "ideas")` → `self.paths.ideas_dir`；1 处 `os.path.join(ideas_dir, d, "proposal.md")` → `self.paths.idea_proposal(d)`；7 处 `os.makedirs(..., exist_ok=True)` → `self.paths.ensure_dir(...)`
  - 保留所有动态文件名构造（目录内迭代拼接文件名的 os.path.join）
- **验证**：`from agents.orchestrator import ResearchOrchestrator` import 通过

### [重构] 2026-03-26 15:49 — FSM 全面接管：消除 research_tree 双轨制 (`7a63dca`)
- **目的**：消除 FSM + research_tree 双轨并行导致的状态不一致和载入失败问题
- **改动**：
  - `agents/fsm_engine.py` — 删除 `tree_service` 依赖、`_mark_phase_completed()`、`_recover_from_tree()`、`STATE_TO_PHASE`；新增 `_recover_from_filesystem()`（从产出文件推断状态）、原子写入、`_record_transition()` 写 audit_log.yaml、`feedback` 改为运行时局部变量、survey 轮次用 `topic_retry_counts` 替代 history 扫描
  - `agents/orchestrator.py` — `tree_service` → `registry`（IdeaRegistryService）；删除所有 `_update_idea_phase()` 调用和方法本身
  - 新增 `shared/models/audit.py`（TransitionRecord）、`shared/models/decisions.py`（4 个 Decision + to_summary()）、`shared/models/idea_registry.py`（Score, Relationship, TopicMeta, IdeaEntry, IdeaRegistry）、`tools/idea_registry.py`（IdeaRegistryService + read_research_status）
  - 精简 `shared/models/fsm.py`（删除 TransitionRecord/Decision/feedback/transition_history，新增 schema_version + topic_retry_counts）
  - 5 个 Agent：`read_tree` → `read_research_status`，删除 `update_idea_phase` 工具
  - `run_research.py`：init 创建 idea_registry.yaml 替代 research_tree.yaml；FSM 构造不再传 tree_service
  - 删除 `shared/models/research_tree.py`、`tools/research_tree.py`、`enums.py` 中 PhaseName
  - 迁移脚本 `scripts/migrate_tree_to_registry.py`
- **验证**：全部 import 通过；T001 fsm_state.yaml 从 1222 行压缩到 15 行；audit_log.yaml 54 条精简记录；idea_registry.yaml 含 5 个 idea

### [修复] 2026-03-26 10:18 — FSM 快照序列化修复 + 损坏快照自动恢复 (`d4e0e0a`)
- **目的**：修复 StrEnum 等类型写入 YAML 时带 Python 对象标签的问题；加载损坏快照恢复后自动覆写文件
- **改动**：`agents/fsm_engine.py` `_persist_snapshot()` 改用 `model_dump(mode="json")` 确保纯字符串序列化；`_load_snapshot()` 从 research_tree 恢复后立即覆写 fsm_state.yaml
- **验证**：未测试

### [重构] 2026-03-24 10:57 — FSM auto/interactive 模式 + 路由纯化 + 输入验证修复 (`f944c36`)
- **目的**：分离质量评估与重试策略，修复 interactive 模式下 retry_counts 导致误 abandon、无效输入默认到推荐状态、Pydantic 序列化警告
- **改动**：`fsm_engine.py` — `__init__` 增加 `auto` 参数；`_route_analysis/_route_theory_check/_route_debug` 剥离所有重试上限逻辑（纯返回评估结果）；`run_idea/step` 增加 auto 模式重试上限检查；`run_idea/run_topic` 用户确认加 `not self.auto` 守卫；`_prompt_user_idea` 无效输入 while 循环重新提示；`_mark_idea_abandoned` 改用 `IdeaStatus.failed` 枚举。`run_research.py` — fsm run 增加 `--auto` CLI 参数。`fsm_state.yaml` — I001 retry_counts 清零、状态重置
- **验证**：import 通过，CLI `--help` 显示 `--auto` 参数

### [修改] 2026-03-24 00:13 — FSM 反馈循环统一用文档路径替代 thin feedback 字符串 (`1e3166c`)
- **目的**：FSM 回退时 `idea_fsm.feedback` 只是拼接的短字符串，下游 Agent 信息不足。改为传完整文档路径让 Agent 自行读取
- **改动**：`fsm_engine.py` `_run_debug()` 去掉 `feedback=idea_fsm.feedback`，改为检查 analysis.md/debug_report.md 并传路径，通过 `orch.phase_debug()` 调用；`orchestrator.py` `phase_debug()` 签名去掉 `feedback`，增加 `analysis_path` + `debug_report_path`；`phase_code()` 检查 debug_report.md 并传路径；`phase_refine()` 检查 analysis.md 并传路径
- **验证**：import 通过

### [修改] 2026-03-23 23:43 — refine feedback 改为文件路径方式 (`ca9682c`)
- **目的**：去掉 feedback 字符串传递，改为让 RefinementAgent 自行读取 theory_review.md 获取完整审查信息
- **改动**：`orchestrator.py` `phase_refine()` 移除 feedback 参数，改为检测 theory_review.md 是否存在并传路径；`refinement_agent.py` `build_prompt()` 移除 feedback 参数，改为 theory_review_path；`fsm_engine.py` refine 调用不再传 feedback
- **验证**：import 通过

### [修复] 2026-03-23 23:36 — FSM retry_count 递增错误 + theory_check→refine 缺少用户确认 (`069d579`)
- **目的**：修复 theory_check↔refine 死循环：retry_count 递增了 next_state 而非 current_state 导致上限不生效；theory_check→refine 不在 USER_CONFIRM_TRANSITIONS 中导致自动循环无干预
- **改动**：`fsm_engine.py` 行 201+256 `retry_counts[next_state]` → `retry_counts[state]`；USER_CONFIRM_TRANSITIONS 新增 `("theory_check", "refine")`
- **验证**：未测试

### [修改] 2026-03-23 23:05 — FSM 路由增加 derivative verdict + 跨 idea 上下文 + refine feedback 传递 (`535b346`)
- **目的**：支持 TheoryEvaluator 新增的 derivative 判定；为评估器提供同 batch 其他 idea 摘要；refine 回退时传递评估 feedback
- **改动**：`fsm_engine.py` `_route_theory_check()` 增加 derivative 分支（→ refine 或 abandon）；`_gather_theory_eval_context()` 增加 other_ideas_summary；新增 `_gather_other_ideas_summary()` 方法；`_execute_idea_state("refine")` 传递 `feedback=idea_fsm.feedback`。`orchestrator.py` `phase_refine()` 签名增加 feedback 参数并传递给 RefinementAgent
- **验证**：import 通过

### [修复] 2026-03-23 22:15 — phase_ideation 传入 topic_dir (`d081a7c`)
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
