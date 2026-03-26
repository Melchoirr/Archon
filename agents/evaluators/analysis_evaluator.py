"""AnalysisEvaluator — 实验分析后的结构化判定"""

from .base_evaluator import BaseEvaluator
from shared.models.fsm import AnalysisDecision, AnalysisVerdict

SYSTEM_PROMPT = """你是实验结果评估专家。根据分析报告、指标数据和迭代历史，做出结构化判定。

你必须输出一个 YAML 块（用 ```yaml 包裹），格式如下：

```yaml
verdict: success/tune/enrich/restructure/code_bug/need_literature/abandon
confidence: 0.0-1.0
metrics_vs_baseline:
  指标名: {baseline: 数值, actual: 数值, delta_pct: 百分比}
metrics_vs_expectation:
  指标名: {expected: 数值, actual: 数值, met: true/false}
expectations_met_ratio: 0.0-1.0
failure_category: hyperparameter/architecture/data/theory/implementation/null
root_cause: "根因描述"
iteration_trend: improving/plateau/degrading
remaining_potential: 0.0-1.0
next_action_detail: "具体建议"
suggested_changes:
  - "修改1"
  - "修改2"
```

## Verdict 判定标准

- **success**: expectations_met_ratio ≥ 0.7，核心指标达到或超过预期
- **tune**: 有改进空间，参数调整可能有效（趋势 improving 或 plateau 但 remaining_potential > 0.3）
- **enrich**: 方案核心有效但细节不足，需要增强模块或补充组件
- **restructure**: 方案根本方向需要调整，需要大幅修改设计
- **code_bug**: 指标异常（NaN、极端值、不合理结果），怀疑实现 bug
- **need_literature**: 分析中发现理论基础不足，需要补充文献（将回退到 refine，由 refine agent 搜索补充论文）
- **abandon**: 多次迭代无改进，理论基础被证伪，或成本收益比过低

## 注意
- 用数据说话，不要空洞判断
- confidence 反映你对判定的确信度
- remaining_potential 反映你预估的改进空间"""


class AnalysisEvaluator(BaseEvaluator):
    def __init__(self):
        super().__init__(name="分析评估器", system_prompt=SYSTEM_PROMPT)

    def build_prompt(self, *, analysis_md: str = "", metrics_json: str = "",
                     experiment_plan: str = "", iteration_history: str = "",
                     retry_count: int = 0, max_retries: int = 5,
                     **kwargs) -> str:
        return f"""请评估以下实验分析结果并做出判定。

## 分析报告
{analysis_md}

## 指标数据
{metrics_json}

## 实验计划（含预期结果）
{experiment_plan}

## 迭代历史
{iteration_history}

## 当前状态
- 已重试次数: {retry_count}/{max_retries}

请输出 YAML 格式的判定结果。"""

    def parse_decision(self, raw: dict) -> AnalysisDecision:
        """将原始 dict 解析为 AnalysisDecision"""
        try:
            verdict = AnalysisVerdict(raw.get("verdict", "tune"))
        except ValueError:
            verdict = AnalysisVerdict.tune

        return AnalysisDecision(
            verdict=verdict,
            confidence=float(raw.get("confidence", 0.5)),
            metrics_vs_baseline=raw.get("metrics_vs_baseline", {}),
            metrics_vs_expectation=raw.get("metrics_vs_expectation", {}),
            expectations_met_ratio=float(raw.get("expectations_met_ratio", 0.0)),
            failure_category=raw.get("failure_category"),
            root_cause=str(raw.get("root_cause", "")),
            iteration_trend=str(raw.get("iteration_trend", "unknown")),
            remaining_potential=float(raw.get("remaining_potential", 0.5)),
            next_action_detail=str(raw.get("next_action_detail", "")),
            suggested_changes=raw.get("suggested_changes", []),
        )
