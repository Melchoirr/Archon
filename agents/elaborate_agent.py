"""展开调研背景 Agent：梳理研究问题空间，保持开放性"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.file_ops import read_file, write_file, READ_FILE_SCHEMA, WRITE_FILE_SCHEMA
from tools.web_search import web_search, WEB_SEARCH_SCHEMA

SYSTEM_PROMPT_TEMPLATE = """你是科研领域分析专家。你的任务是展开和梳理研究课题的调研背景。

研究课题: {topic_title}
领域: {topic_domain}

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

不要简化或妥协方案，除非 idea 本身被证明有根本性错误。遇到实现困难时，寻找解决办法而非回退到更简单的版本。"""


class ElaborateAgent(BaseAgent):
    def __init__(self, config_path="config.yaml", output_path="knowledge/context.md"):
        tc = load_topic_config(config_path)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=tc["topic_title"],
            topic_domain=tc.get("topic_domain", ""),
            output_path=output_path,
        )

        super().__init__(
            name="背景展开Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=15,
        )
        self.register_tool("read_file", read_file, READ_FILE_SCHEMA)
        self.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
        self.register_tool("web_search", web_search, WEB_SEARCH_SCHEMA)
