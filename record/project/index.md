# Archon — 功能索引

## 架构概览

三层架构：入口层 → 编排层 → 执行层

```
run_research.py (CLI 入口, 15 个子命令)
    ↓
ResearchOrchestrator (阶段编排) + ResearchFSM (状态机路由)
    ↓
11 Agent (ReAct 循环)  ←→  3 Evaluator (结构化判定)
    ↓
20 Tool (文件/搜索/论文/代码/知识库/...)
    ↓
shared/ (Pydantic 模型 + 路径管理 + 配置)
```

**核心模式**：ReAct 循环、FSM 状态机、Pydantic 全链路类型校验
**主力 LLM**：MiniMax M2.5 (200K ctx, Anthropic SDK 兼容接口)
**完整运行流程**：→ [运行流程](flow.md)

## 功能清单

### F01 — CLI 入口与项目初始化 · ✅已完成 · 🟢在用
- **核心文件**：`run_research.py`
- **上游**：无 / **下游**：F02
- **最后变更**：2026-03-26 10:18

<details><summary>功能概要</summary>

**做什么**：提供 15 个 CLI 子命令（init, elaborate, survey, ideation, refine, code, experiment, analyze, conclude 等），支持手动模式和 FSM 自动模式
**怎么做**：argparse 解析命令 → 创建 ResearchOrchestrator → 派发到对应 phase 方法。FSM 模式支持 --force 跳转和 --from 指定起始状态
**关键接口**：`cmd_init(args)`, `_get_orchestrator(args)`, `_get_fsm(args)`, `main()`
**数据流**：CLI 参数 → Orchestrator 实例 → 阶段执行 → 结果摘要输出

</details>

→ [完整详情](features/f01-cli-entry.md)

### F02 — 编排引擎与 FSM 状态机 · ✅已完成 · 🟢在用
- **核心文件**：`agents/orchestrator.py`, `agents/fsm_engine.py`, `tools/idea_registry.py`, `shared/models/fsm.py`, `shared/models/decisions.py`, `shared/models/audit.py`, `shared/models/idea_registry.py`
- **上游**：F01 / **下游**：F03-F12
- **最后变更**：2026-03-28 09:43

<details><summary>功能概要</summary>

**做什么**：Orchestrator 编排 12 个研究阶段，FSM 管理 Topic 级和 Idea 级状态转换
**怎么做**：FSM 是唯一状态源。三文件分离：fsm_state.yaml（恢复数据）+ idea_registry.yaml（Idea 元数据）+ audit_log.yaml（流转记录）。Orchestrator 使用 IdeaRegistryService 管理 Idea 元数据，FSM 引擎不再依赖 ResearchTreeService
**关键接口**：`ResearchOrchestrator.phase_*()`, `ResearchFSM.run_topic()`, `run_idea()`, `step()`, `IdeaRegistryService.read_research_status()`
**数据流**：CLI 命令 → Orchestrator 组装上下文 → Agent 执行 → 评估器判定 → FSM 状态转换 → audit_log.yaml 记录

</details>

→ [完整详情](features/f02-orchestration-fsm.md)

### F03 — Agent 基座（ReAct 循环） · ✅已完成 · 🟢在用
- **核心文件**：`agents/base_agent.py`
- **上游**：F02 / **下游**：F05-F09 所有专用 Agent
- **最后变更**：2026-03-11 17:12

<details><summary>功能概要</summary>

**做什么**：所有专用 Agent 的基类，实现 ReAct 循环（推理→工具→观察→推理）
**怎么做**：LLM 调用（MiniMax M2.5）→ 工具执行（ThreadPoolExecutor 并行）→ 消息压缩（150K 上限）→ 紧急提示（≤5 次迭代时）。Pydantic 校验工具参数，PathGuard 包装写操作
**关键接口**：`BaseAgent.run(prompt)`, `register_tool(name, handler, schema)`, `llm_call_with_retry()`
**数据流**：user prompt → ReAct 循环（LLM ↔ Tools） → 最终文本输出

</details>

→ [完整详情](features/f03-agent-base.md)

### F04 — 评估器体系 · ✅已完成 · 🟢在用
- **核心文件**：`agents/evaluators/`
- **上游**：F02, F07, F09 / **下游**：F02
- **最后变更**：2026-03-27 23:22

<details><summary>功能概要</summary>

**做什么**：3 个轻量级评估器（单次 LLM 调用，无工具），为 FSM 提供结构化路由决策
**怎么做**：build_prompt() → 单次 LLM 调用 → YAML 解析 → Pydantic Decision 模型。AnalysisEvaluator(7 verdict)、TheoryEvaluator(4 verdict: sound/weak/flawed/derivative + 创新性/因果推演)、SurveyEvaluator(2 verdict)
**关键接口**：`BaseEvaluator.evaluate(context)`, `parse_decision(raw)`
**数据流**：Agent 产出物（analysis.md, theory_review.md 等） → 评估器 → verdict → FSM 路由

</details>

→ [完整详情](features/f04-evaluators.md)

### F05 — 文献调研管道 · ✅已完成 · 🟢在用
- **核心文件**：`agents/survey_helpers.py`, `tools/openalex.py`, `tools/paper_manager.py`, `agents/data_agent.py`
- **上游**：F01, F02, F07, F11 / **下游**：F06, F07
- **最后变更**：2026-03-26 17:14

<details><summary>功能概要</summary>

**做什么**：5 步文献调研流水线（搜索→下载→摘要→Repo→综合），从零到完整文献综述
**怎么做**：4 阶段搜索策略（OpenAlex + web search + 引用图）→ PDF 双后端解析（Zhipu→MinerU）→ LLM 单篇摘要 → GitHub Repo 克隆+摘要 → DataAgent EDA → 综合写 survey/baselines/datasets/metrics
**关键接口**：`make_search_agent()`, `make_repo_agent()`, `summarize_single_paper()`, `download_paper()`, `DataAgent`
**数据流**：config 关键词 → OpenAlex 搜索 → PDF 下载解析 → 摘要 → survey.md + baselines.md + datasets.md + metrics.md

</details>

→ [完整详情](features/f05-literature-survey.md)

### F06 — Idea 生成与评分 · ✅已完成 · 🟢在用
- **核心文件**：`agents/ideation_agent.py`, `tools/idea_scorer.py`, `tools/idea_graph.py`
- **上游**：F05, F11 / **下游**：F07
- **最后变更**：2026-03-28 00:57

<details><summary>功能概要</summary>

**做什么**：ReAct 循环生成 idea（proposal.md），然后多维评分（查重+embedding 相似度+LLM 4 维评分）并排名
**怎么做**：IdeationAgent 读调研材料 → 搜索验证 → 写 proposal → 注册研究树。score_all_ideas() 对每个 idea：搜索查询提取 → OpenAlex 查重 → embedding 相似度检测（≥0.85 高相似）→ LLM 评分（N×0.35+S×0.35+F×0.20+A×0.10）→ 排名
**关键接口**：`IdeationAgent.build_prompt()`, `score_all_ideas()`, `add_idea_relationship()`, `get_idea_graph()`
**数据流**：survey 产物 → proposal.md → 评分流水线 → review.md + 研究树 scores/status 更新

</details>

→ [完整详情](features/f06-ideation.md)

### F07 — 研究设计 · ✅已完成 · 🟢在用
- **核心文件**：`agents/elaborate_agent.py`, `agents/refinement_agent.py`, `agents/design_agent.py`, `agents/theory_check_agent.py`
- **上游**：F01, F05, F06 / **下游**：F04, F08
- **最后变更**：2026-03-25 19:42

<details><summary>功能概要</summary>

**做什么**：研究设计全流程（背景展开→理论深化→模块设计→理论验证）
**怎么做**：ElaborateAgent 写 context.md。RefinementAgent 输出 4 文档（theory.md, model_modular.md, model_complete.md, experiment_plan.md）。TheoryCheckAgent 文献交叉验证 → TheoryEvaluator 判定
**关键接口**：`ElaborateAgent.build_prompt()`, `RefinementAgent.build_prompt()`, `TheoryCheckAgent.build_prompt()`
**数据流**：topic_spec.md → context.md → proposal.md → refinement/ (4 文档) → theory_review.md

</details>

→ [完整详情](features/f07-research-design.md)

### F08 — 实验执行与调试 · ✅已完成 · 🟢在用
- **核心文件**：`agents/experiment_agent.py`, `agents/debug_agent.py`, `tools/claude_code.py`, `tools/venv_manager.py`
- **上游**：F07, F02 / **下游**：F09, F04
- **最后变更**：2026-03-28 10:05

<details><summary>功能概要</summary>

**做什么**：代码编写（PM→Claude Code 委托）、测试调试（最多 5 轮）、实验运行（多步骤多版本）
**怎么做**：ExperimentAgent 作 PM 分解任务 → claude_write_module() 逐模块实现 → setup_venv() 隔离环境。DebugAgent 运行测试 → claude_fix_error() 修复。实验按步骤(SXX)版本(VN)组织
**关键接口**：`ExperimentAgent.build_code_prompt()`, `build_experiment_prompt()`, `DebugAgent.build_prompt()`, `claude_write_module()`, `setup_idea_venv()`
**数据流**：设计文档 → src/ (代码) → debug_report.md → results/SXX/VN/ (实验结果)

</details>

→ [完整详情](features/f08-experiment-debug.md)

### F09 — 分析与结论 · ✅已完成 · 🟢在用
- **核心文件**：`agents/analysis_agent.py`, `agents/conclusion_agent.py`, `tools/vlm_analysis.py`
- **上游**：F08, F02 / **下游**：F04, F11
- **最后变更**：2026-03-24 00:11

<details><summary>功能概要</summary>

**做什么**：实验结果分析（数据驱动+VLM 图表分析）+ 全链路客观结论
**怎么做**：AnalysisAgent 逐步骤版本分析（vs baseline, vs 预期）→ VLM 批量图表分析 → analysis.md。ConclusionAgent 读全链路 → conclusion.md（6 节，≥2000 字符）→ 记录经验
**关键接口**：`AnalysisAgent.build_prompt()`, `ConclusionAgent.build_prompt()`, `analyze_plots_dir()`, `analyze_image()`
**数据流**：results/ → analysis.md → AnalysisEvaluator verdict → conclusion.md + experience_log

</details>

→ [完整详情](features/f09-analysis-conclusion.md)

### F10 — 数据模型与路径管理 · ✅已完成 · 🟢在用
- **核心文件**：`shared/paths.py`, `shared/path_guard.py`, `shared/models/`, `shared/utils/`, `shared/templates/`
- **上游**：无 / **下游**：F01-F12 全部
- **最后变更**：2026-03-28 09:43

<details><summary>功能概要</summary>

**做什么**：类型安全基础设施——统一路径解析、写操作安全校验、Pydantic 模型体系、实验代码模板
**怎么做**：PathManager 统一路径（全局+topic+idea 级）。PathGuard 正则检测写目标。Pydantic 模型体系：FSM 核心（fsm.py）+ 评估器决策（decisions.py）+ 审计记录（audit.py）+ Idea 注册表（idea_registry.py）+ 工具参数模型
**关键接口**：`PathManager(project_root, topic_dir)`, `PathGuard.check(path)`, `ToolParamsBase.to_schema()`, `TopicConfig`, `IdeaRegistry`, `FSMSnapshot`
**数据流**：代码路径请求 → PathManager 解析 → 绝对路径；数据加载 → Pydantic 校验 → 类型安全模型

</details>

→ [完整详情](features/f10-data-models.md)

### F11 — 知识管理与上下文 · ✅已完成 · 🟢在用
- **核心文件**：`tools/knowledge_index.py`, `tools/knowledge_base.py`, `tools/memory.py`, `tools/context_manager.py`, `tools/embedding.py`, `tools/phase_logger.py`
- **上游**：F10 / **下游**：F03-F09, F12
- **最后变更**：2026-03-26 17:14

<details><summary>功能概要</summary>

**做什么**：三大知识积累机制——智谱知识库（云端向量检索）、经验日志（YAML 本地存储）、自动上下文组装
**怎么做**：KnowledgeBaseManager 管理智谱 KB（混合召回 embedding+keyword）。memory 按 phase/idea/topic 过滤经验。ContextManager 按阶段规则自动收集文件 + 跨引用 + 截断。Embedding-3 批量编码用于 idea 查重
**关键接口**：`ContextManager.build_context()`, `search_knowledge_base()`, `query_memory()`, `add_experience()`, `compute_max_similarity()`
**数据流**：阶段产物 → 上传 KB / 记录经验 → 下游 Agent 通过 build_context() 获取

</details>

→ [完整详情](features/f11-knowledge-context.md)

### F12 — 通用工具集 · ✅已完成 · 🟢在用
- **核心文件**：`tools/file_ops.py`, `tools/web_search.py`, `tools/github_repo.py`, `tools/idea_registry.py`
- **上游**：F03, F11 / **下游**：F05-F09
- **最后变更**：2026-03-26 17:14

<details><summary>功能概要</summary>

**做什么**：被多 Agent 共用的基础工具——文件 I/O、DuckDuckGo 搜索、GitHub 仓库管理、Idea 注册表 CRUD
**怎么做**：file_ops 提供 read/write/append/list。web_search 封装 DuckDuckGo。github_repo 浅克隆+Claude 摘要。IdeaRegistryService 线程安全 CRUD + read_research_status() 合并视图
**关键接口**：`read_file()`, `write_file()`, `web_search()`, `clone_repo()`, `summarize_repo()`, `IdeaRegistryService.read_research_status()`
**数据流**：Agent 工具调用 → 文件/搜索/Git/注册表操作 → 结果返回 Agent

</details>

→ [完整详情](features/f12-utility-tools.md)

## 全局问题汇总

（暂无已知问题）
