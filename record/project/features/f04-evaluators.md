# [F04] 评估器体系

## 状态

- **实现状态**：✅已完成
- **核心文件**：
  - `agents/evaluators/base_evaluator.py` — `BaseEvaluator`，轻量评估器基类（单次 LLM 调用→YAML 输出）
  - `agents/evaluators/analysis_evaluator.py` — `AnalysisEvaluator`，实验结果判定（success/tune/enrich/restructure/code_bug/need_literature/abandon）
  - `agents/evaluators/theory_evaluator.py` — `TheoryEvaluator`，理论判定（sound/weak/flawed）
  - `agents/evaluators/survey_evaluator.py` — `SurveyEvaluator`，调研覆盖度判定（sufficient/need_more）
- **功能描述**：独立于工作 Agent 的评估层。不使用 ReAct 循环，而是单次 LLM 调用产出结构化 YAML 判定。评估结果被 FSM 引擎用于决定状态转换方向（前进/回退/abandon）。每个评估器有对应的 Pydantic Decision 模型确保输出格式。
- **测试方法**：
  ```python
  from agents.evaluators.analysis_evaluator import AnalysisEvaluator
  evaluator = AnalysisEvaluator()
  # evaluator.evaluate(context_text) → AnalysisDecision
  ```

## 建议

（暂无）

## 变化

### [实现] 2026-03-17 10:38 — 从 FSM 引擎中独立 (`b6b5ff6`)

<details><summary>详情</summary>

**计划**：将评估逻辑从 FSM 引擎中分离，建立独立评估器体系
**代码修改**：新增 agents/evaluators/ 目录，含 base_evaluator.py、analysis_evaluator.py、theory_evaluator.py、survey_evaluator.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>
