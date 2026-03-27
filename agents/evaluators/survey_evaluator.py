"""SurveyEvaluator — 文献调研后的覆盖度评估"""

from .base_evaluator import BaseEvaluator
from shared.models.decisions import SurveyDecision
from shared.models.fsm import SurveyVerdict

SYSTEM_PROMPT = """你是文献调研评估专家。根据综述文档、论文列表和课题背景，评估文献调研的覆盖度。

你必须输出一个 YAML 块（用 ```yaml 包裹），格式如下：

```yaml
verdict: sufficient/need_more
coverage_score: 0.0-1.0
covered_areas:
  - "已覆盖方向1"
  - "已覆盖方向2"
gap_areas:
  - "缺失方向1"
  - "缺失方向2"
recommended_queries:
  - "建议搜索关键词1"
  - "建议搜索关键词2"
```

## Verdict 判定标准

- **sufficient**: coverage_score ≥ 0.7，核心方向均已覆盖，无明显缺失
- **need_more**: 存在重要的文献空白，需要补充调研

## Coverage 评估维度
1. 核心方法覆盖：是否覆盖了领域内主流方法
2. 最新进展覆盖：近 2 年的重要工作是否包含
3. 理论基础覆盖：所需的理论背景文献是否充分
4. 竞争方法覆盖：是否了解了主要的 baseline 方法
5. 相关数据集和评估方法覆盖

## 注意
- gap_areas 要具体到研究方向，不要太泛
- recommended_queries 要可直接用于学术搜索"""


class SurveyEvaluator(BaseEvaluator):
    def __init__(self):
        super().__init__(name="文献评估器", system_prompt=SYSTEM_PROMPT)

    def build_prompt(self, *, survey: str = "", paper_list: str = "",
                     context: str = "", **kwargs) -> str:
        return f"""请评估以下文献调研的覆盖度。

## 文献综述
{survey}

## 论文列表
{paper_list}

## 课题背景
{context}

请输出 YAML 格式的评估结果。"""

    def parse_decision(self, raw: dict) -> SurveyDecision:
        """将原始 dict 解析为 SurveyDecision"""
        try:
            verdict = SurveyVerdict(raw.get("verdict", "need_more"))
        except ValueError:
            verdict = SurveyVerdict.need_more

        return SurveyDecision(
            verdict=verdict,
            coverage_score=float(raw.get("coverage_score", 0.0)),
            covered_areas=raw.get("covered_areas", []),
            gap_areas=raw.get("gap_areas", []),
            recommended_queries=raw.get("recommended_queries", []),
        )
