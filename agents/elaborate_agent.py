"""展开调研背景 Agent：梳理研究问题空间，保持开放性"""
from .base_agent import BaseAgent
from tools.file_ops import read_file, write_file
from tools.web_search import web_search
from shared.models.tool_params import (
    ReadFileParams, WriteFileParams, WebSearchParams,
)

SYSTEM_PROMPT_TEMPLATE = """你是科研领域分析专家。你的任务是展开和梳理研究课题的调研背景。

研究课题: {topic_title}

## 核心目标

分析课题的研究背景，产出结构化的 context.md 文档，为后续的深入文献调研做准备。

## 输出要求

将结果写入 {output_path}，包含以下结构:

1. **研究背景（宏观）**
   - 该领域的发展现状
   - 为什么这个问题重要
   - 工业界/学术界的关注度

2. **问题空间（不局限于单一方向）**
   - 该课题涉及的核心问题是什么
   - 有哪些不同的研究角度和方法流派
   - 每个角度的优劣和适用场景

3. **具体科研问题列表**
   - 从多个角度列出可探索的具体科研问题
   - 每个问题的难度和潜在影响

4. **范围边界**
   - 明确哪些在范围内，哪些不在
   - 防止过于 narrow 或过于 broad

## 关键约束

**不要太深入，保持开放性。** 你的任务是广度而非深度：
- 不要在某个方向上深入太多技术细节
- 保持多角度并列，不要过早做判断
- 可以用 web_search 轻量搜索理解领域概况
- 避免下结论，更多是提出问题和可能性

## 输出质量要求

**总输出不少于 2000 字。** 每个章节必须充分展开：
- 研究背景: ≥400字，覆盖领域发展现状、重要性、关注度
- 问题空间: ≥500字，至少列出 3 个不同研究角度，每个角度 2-3 段分析
- 具体科研问题列表: ≥500字，至少 5 个问题，每个问题含难度评估和影响分析
- 范围边界: ≥200字，明确 in-scope 和 out-of-scope

不要用一句话概括一个研究角度。每个角度需要说明：核心思路、代表性工作、优劣势、适用场景。"""


class ElaborateAgent(BaseAgent):
    def __init__(self, topic_dir: str, output_path: str = "context.md",
                 allowed_dirs: list[str] = None):
        from shared.utils.config_helpers import extract_topic_title
        topic_title = extract_topic_title(topic_dir)

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=topic_title,
            output_path=output_path,
        )

        super().__init__(
            name="背景展开Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=12,
            allowed_dirs=allowed_dirs,
        )
        self.register_tool("read_file", read_file, ReadFileParams)
        self.register_tool("write_file", write_file, WriteFileParams)
        self.register_tool("web_search", web_search, WebSearchParams)

    def build_prompt(self, *, topic_title: str, spec_content: str = "",
                     context: str = "", output_path: str) -> str:
        prompt = f"开始展开调研背景。\n\n课题: {topic_title}\n\n"
        if spec_content:
            prompt += f"""以下是用户对课题的初步描述，仅作为线索参考，不要被其限制：

---
{spec_content}
---

注意：以上只是出发点，你需要更广泛地探索问题空间，不要局限于上述描述的方向。

"""
        if context:
            prompt += f"\n{context}\n"
        prompt += f"\n请将结果写入 {output_path}"
        return prompt
