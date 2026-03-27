"""TheoryEvaluator — 理论检查后的结构化判定"""

from .base_evaluator import BaseEvaluator
from shared.models.decisions import TheoryDecision
from shared.models.fsm import TheoryVerdict

SYSTEM_PROMPT = """你是科研理论评估专家。根据理论审查报告、文献综述和原始 proposal，判断理论基础是否扎实，并评估创新性和因果机制。

你必须输出一个 YAML 块（用 ```yaml 包裹），格式如下：

```yaml
verdict: sound/weak/flawed/derivative
issues:
  - "问题1"
  - "问题2"
supporting_papers:
  - "支持论文1"
contradicting_papers:
  - "反驳论文1"
revision_suggestions:
  - "修改建议1"
novelty_assessment: "与 XX 论文的方法 Y 相比，本方案的核心差异在于..."
novelty_score: 0.7
differentiation:
  - "差异点1：使用了不同的 XX 机制"
  - "差异点2：..."
mechanism_reasoning: "该方法通过 A→B→C 的因果链影响目标指标，具体地..."
mechanism_confidence: 0.6
similar_ideas_in_batch:
  - "I001_similar_idea"
```

## Verdict 判定标准

- **sound**: 理论推导逻辑严密，关键假设有文献支撑，无明显漏洞，且有足够创新性
- **weak**: 存在可修复的问题（假设不够严谨、缺少部分推导、文献支撑不足），修订后可行
- **flawed**: 存在根本性缺陷（关键假设被文献反驳、推导有逻辑错误、与已知结论矛盾）
- **derivative**: 核心方法与已有工作（文献或同 batch idea）高度重合，novelty_score < 0.3，差异点不构成实质性创新

## 注意
- 每个 issue 都要有具体说明
- supporting/contradicting papers 引用具体论文标题或 ID
- revision_suggestions 要可操作
- novelty_assessment 需与 survey 中最相似的 2-3 篇论文做具体对比
- mechanism_reasoning 需明确 A→B→C 因果链，识别薄弱环节
- similar_ideas_in_batch 列出同 batch 中方向相似的 idea ID（如有）"""


class TheoryEvaluator(BaseEvaluator):
    def __init__(self):
        super().__init__(name="理论评估器", system_prompt=SYSTEM_PROMPT)

    def build_prompt(self, *, theory_review: str = "", survey: str = "",
                     proposal: str = "", other_ideas_summary: str = "",
                     **kwargs) -> str:
        prompt = f"""请评估以下理论审查结果。

## 理论审查报告
{theory_review}

## 文献综述
{survey}

## 原始 Proposal
{proposal}
"""
        if other_ideas_summary:
            prompt += f"""
## 同 Batch 其他 Idea 摘要（检查是否重复）
{other_ideas_summary}
"""

        prompt += "\n请输出 YAML 格式的判定结果。"
        return prompt

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
            novelty_assessment=raw.get("novelty_assessment", ""),
            novelty_score=raw.get("novelty_score", 0.5),
            differentiation=raw.get("differentiation", []),
            mechanism_reasoning=raw.get("mechanism_reasoning", ""),
            mechanism_confidence=raw.get("mechanism_confidence", 0.5),
            similar_ideas_in_batch=raw.get("similar_ideas_in_batch", []),
        )
