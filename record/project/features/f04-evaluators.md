# [F04] 评估器体系

## 状态
- **实现状态**：✅已完成

## 核心文件
- `agents/evaluators/base_evaluator.py:15-93` — `BaseEvaluator`，轻量评估器基类（单次 LLM 调用，无工具）
- `agents/evaluators/analysis_evaluator.py:44-90` — `AnalysisEvaluator`，verdict: success/tune/enrich/restructure/code_bug/need_literature/abandon
- `agents/evaluators/theory_evaluator.py:35-82` — `TheoryEvaluator`，verdict: sound/weak/flawed/derivative
- `agents/evaluators/survey_evaluator.py:41-73` — `SurveyEvaluator`，verdict: sufficient/need_more
- `agents/evaluators/__init__.py:1-6` — 评估器包导出

## 功能描述
轻量级决策组件，不走 ReAct 循环，单次 LLM 调用返回结构化 YAML verdict。被 FSM 引擎用于路由状态转换。

**BaseEvaluator**：`evaluate(context)` 单次 LLM 调用 + `_parse_yaml()` 解析（支持 ```yaml``` 块、直接 YAML、逐行 key:value fallback）

**AnalysisEvaluator** 输出：verdict, confidence, metrics_vs_baseline, metrics_vs_expectation, expectations_met_ratio, failure_category, root_cause, iteration_trend, remaining_potential, next_action_detail, suggested_changes[]

**TheoryEvaluator** 输出：verdict, issues[], supporting_papers[], contradicting_papers[], revision_suggestions[], novelty_assessment, novelty_score(0-1), differentiation[], mechanism_reasoning, mechanism_confidence(0-1), similar_ideas_in_batch[]

**SurveyEvaluator** 输出：verdict, coverage_score (0-1), covered_areas[], gap_areas[], recommended_queries[]

**关键数据结构**：`AnalysisDecision`(fsm.py:62)、`TheoryDecision`(fsm.py:77, 含创新性+因果推演字段)、`SurveyDecision`(fsm.py:93)

## 运行流程

### 触发条件
- AnalysisEvaluator：FSM analyze 完成后，`fsm_engine._route_analysis()` 调用
- TheoryEvaluator：FSM theory_check 完成后，`fsm_engine._route_theory_check()` 调用
- SurveyEvaluator：FSM survey 完成后，`fsm_engine._evaluate_topic_transition()` 调用

### 处理步骤
1. **构建 prompt** — `build_prompt(**context)` 组装评估上下文
2. **LLM 调用** — `evaluate()` 单次调用 MiniMax，要求输出 YAML
3. **解析结果** — `_parse_yaml()` 提取结构化数据
4. **转换决策** — `parse_decision(raw)` → Pydantic 决策模型

### 输出
- 结构化决策对象（AnalysisDecision / TheoryDecision / SurveyDecision）

### 依赖关系
- **上游**：F02（FSM 调用）、F07/F09（Agent 产出物作为输入）
- **下游**：F02（FSM 根据 verdict 决定转换方向）

### 错误与边界情况
- YAML 解析失败：fallback 逐行 key:value
- 解析彻底失败：返回 `{"raw_output": text}`

## 测试方法
```python
from agents.evaluators import AnalysisEvaluator
evaluator = AnalysisEvaluator()
result = evaluator.evaluate({"analysis_md": "...", "metrics_json": "..."})
```

## 建议
（暂无）

## 变化
### [修复] 2026-03-27 23:22 — 修复全部 Evaluator 的 Decision import 路径错误
- **目的**：三个 evaluator 都从 `shared.models.fsm` 导入 `*Decision`，但这些类实际定义在 `shared.models.decisions`
- **改动**：`analysis_evaluator.py`、`theory_evaluator.py`、`survey_evaluator.py` — 将 `*Decision` 的 import 改为从 `shared.models.decisions` 导入，`*Verdict` 仍从 `shared.models.fsm` 导入
- **验证**：`python -c 'from agents.evaluators import ...'` 通过

### [修复] 2026-03-27 23:13 — 修复 AnalysisEvaluator import 路径错误 (`ae2f390`)
- **目的**：修复 `AnalysisDecision` 从错误模块导入导致的 ImportError
- **改动**：`agents/evaluators/analysis_evaluator.py` — 将 `from shared.models.fsm import AnalysisDecision` 改为 `from shared.models.decisions import AnalysisDecision`（`AnalysisDecision` 定义在 decisions.py 而非 fsm.py）
- **验证**：未测试

### [修改] 2026-03-26 19:09 — need_literature verdict 路由变更 (`3bed669`)
- **目的**：deep_survey 被移除，need_literature 改路由到 refine
- **改动**：`agents/evaluators/analysis_evaluator.py` — 更新 need_literature 描述，说明将回退到 refine 由 refine agent 搜索补充论文
- **验证**：import 通过

### [修改] 2026-03-23 23:05 — TheoryEvaluator 扩展创新性 + 因果推演 + 跨 idea 去重 (`535b346`)
- **目的**：评估 idea 的创新性、因果机制可信度，并检测同 batch idea 重复
- **改动**：`theory_evaluator.py` SYSTEM_PROMPT 增加 derivative verdict 和 6 个新字段；`build_prompt()` 增加 `other_ideas_summary` 参数；`parse_decision()` 解析新字段
- **验证**：import + build_prompt 调用通过

### [实现] 2026-03-17 10:38 — 评估器体系初始实现 (`b6b5ff6`)
- **目的**：从 FSM 引擎中拆分评估逻辑为独立评估器
- **改动**：新增 evaluators/ 目录（base + 3 个专用评估器）
- **验证**：未测试
