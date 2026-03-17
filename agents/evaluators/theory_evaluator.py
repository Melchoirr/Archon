"""TheoryEvaluator — 理论检查后的结构化判定"""

from .base_evaluator import BaseEvaluator
from shared.models.fsm import TheoryDecision, TheoryVerdict

SYSTEM_PROMPT = """你是科研理论评估专家。根据理论审查报告、文献综述和原始 proposal，判断理论基础是否扎实。

你必须输出一个 YAML 块（用 ```yaml 包裹），格式如下：

```yaml
verdict: sound/weak/flawed
issues:
  - "问题1"
  - "问题2"
supporting_papers:
  - "支持论文1"
contradicting_papers:
  - "反驳论文1"
revision_suggestions:
  - "修改建议1"
```

## Verdict 判定标准

- **sound**: 理论推导逻辑严密，关键假设有文献支撑，无明显漏洞
- **weak**: 存在可修复的问题（假设不够严谨、缺少部分推导、文献支撑不足），修订后可行
- **flawed**: 存在根本性缺陷（关键假设被文献反驳、推导有逻辑错误、与已知结论矛盾）

## 注意
- 每个 issue 都要有具体说明
- supporting/contradicting papers 引用具体论文标题或 ID
- revision_suggestions 要可操作"""


class TheoryEvaluator(BaseEvaluator):
    def __init__(self):
        super().__init__(name="理论评估器", system_prompt=SYSTEM_PROMPT)

    def build_prompt(self, *, theory_review: str = "", survey: str = "",
                     proposal: str = "", **kwargs) -> str:
        return f"""请评估以下理论审查结果。

## 理论审查报告
{theory_review}

## 文献综述
{survey}

## 原始 Proposal
{proposal}

请输出 YAML 格式的判定结果。"""

    def parse_decision(self, raw: dict) -> TheoryDecision:
        """将原始 dict 解析为 TheoryDecision"""
        try:
            verdict = TheoryVerdict(raw.get("verdict", "weak"))
        except ValueError:
            verdict = TheoryVerdict.weak

        return TheoryDecision(
            verdict=verdict,
            issues=raw.get("issues", []),
            supporting_papers=raw.get("supporting_papers", []),
            contradicting_papers=raw.get("contradicting_papers", []),
            revision_suggestions=raw.get("revision_suggestions", []),
        )
