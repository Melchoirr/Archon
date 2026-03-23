# Archon — 功能索引

## 架构概览

三层架构：入口层 → 编排层 → 执行层

```
run_research.py (CLI 入口)
    ↓
ResearchOrchestrator + ResearchFSM (编排 + 状态机)
    ↓
11 Agent (ReAct 循环)  ←→  3 Evaluator (结构化判定)
    ↓
20 Tool (文件/搜索/论文/代码/知识库/...)
    ↓
shared/ (Pydantic 模型 + 路径管理 + 配置)
```

**核心模式**：ReAct 循环、FSM 状态机、Pydantic 全链路类型校验
**主力 LLM**：MiniMax M2.5 (200K ctx, Anthropic SDK 兼容接口)

## 功能清单

| ID | 功能 | 核心文件 | 最初实现 | 最后变更 | 状态 | 维护 | 详情 |
|----|------|----------|----------|----------|------|------|------|
| F01 | CLI 入口与项目初始化 | run_research.py | 03-11 17:12 | 03-17 10:38 | ✅无误 | 🟢在用 | [详情](features/f01-cli-entry.md) |
| F02 | 编排引擎与 FSM 状态机 | orchestrator.py, fsm_engine.py | 03-11 17:12 | 03-21 11:07 | ✅无误 | 🟢在用 | [详情](features/f02-orchestration-fsm.md) |
| F03 | Agent 基座（ReAct 循环） | base_agent.py | 03-11 17:12 | 03-11 17:12 | ✅无误 | 🟢在用 | [详情](features/f03-agent-base.md) |
| F04 | 评估器体系 | evaluators/ | 03-17 10:38 | 03-17 10:38 | ✅无误 | 🟢在用 | [详情](features/f04-evaluators.md) |
| F05 | 文献调研管道 | survey_helpers.py, openalex.py, paper_manager.py | 03-11 17:12 | 03-11 17:12 | ✅无误 | 🟢在用 | [详情](features/f05-literature-survey.md) |
| F06 | Idea 生成与评分 | ideation_agent.py, idea_scorer.py, idea_graph.py | 03-11 17:12 | 03-11 17:12 | ✅无误 | 🟢在用 | [详情](features/f06-ideation.md) |
| F07 | 研究设计 | elaborate_agent.py, refinement_agent.py, design_agent.py, theory_check_agent.py | 03-11 17:12 | 03-11 17:12 | ✅无误 | 🟢在用 | [详情](features/f07-research-design.md) |
| F08 | 实验执行与调试 | experiment_agent.py, debug_agent.py, claude_code.py, venv_manager.py | 03-11 17:12 | 03-17 10:38 | ✅无误 | 🟢在用 | [详情](features/f08-experiment-debug.md) |
| F09 | 分析与结论 | analysis_agent.py, conclusion_agent.py, vlm_analysis.py | 03-11 17:12 | 03-11 17:12 | ✅无误 | 🟢在用 | [详情](features/f09-analysis-conclusion.md) |
| F10 | 数据模型与路径管理 | shared/models/, shared/paths.py | 03-11 17:12 | 03-17 10:46 | ✅无误 | 🟢在用 | [详情](features/f10-data-models.md) |
| F11 | 知识管理与上下文 | knowledge_base.py, memory.py, context_manager.py, embedding.py | 03-11 17:12 | 03-11 17:12 | ✅无误 | 🟢在用 | [详情](features/f11-knowledge-context.md) |
| F12 | 通用工具集 | file_ops.py, web_search.py, github_repo.py, research_tree.py | 03-11 17:12 | 03-11 17:12 | ✅无误 | 🟢在用 | [详情](features/f12-utility-tools.md) |

## 全局问题汇总

（暂无已知问题）
