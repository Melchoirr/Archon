"""结论总结 Agent：客观总结 idea 的全链路结果"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.file_ops import read_file, write_file, list_directory, READ_FILE_SCHEMA, WRITE_FILE_SCHEMA, LIST_DIRECTORY_SCHEMA
from tools.memory import query_memory, add_experience, QUERY_MEMORY_SCHEMA, ADD_EXPERIENCE_SCHEMA

SYSTEM_PROMPT_TEMPLATE = """你是 AI 科研结论总结专家。你的任务是对一个 idea 的全部研究过程进行**完全客观**的总结。

研究课题: {topic_title}

## 输入

你需要阅读该 idea 的全部文档链路:
1. proposal.md - 初始提案
2. refinement/ - 理论推导和模型设计
3. experiment_plan.md - 实验计划（含预期结果）
4. src/ - 代码实现
5. results/ - 实验结果（含各步骤各版本）
6. analysis.md - 分析报告

## 输出

将结论写入 conclusion.md，包含:

### 1. Idea 设计评估
- 原始 idea 的创新性和合理性
- 理论推导是否完整
- 方案设计中的决策是否合理

### 2. 代码实现评估
- 实现是否忠实于设计方案
- 代码质量和完整性
- 有无实现偏差

### 3. 实验结果总结
- **成功的部分**: 哪些指标达到或超过预期
- **失败的部分**: 哪些指标未达预期，可能的原因
- 各步骤各版本的关键数据

### 4. 意外发现
- 实验中出现的预料之外的现象
- 值得进一步探索的方向

### 5. 与原始预期对比
- 逐项对比 experiment_plan.md 中的预期 vs 实际
- 偏差的可能原因

### 6. 经验教训
- 可复用的经验
- 应避免的陷阱

## 核心约束

**完全客观**。不要美化结果，不要回避失败。
- 用数据说话，避免主观判断
- 失败也是有价值的，客观记录原因
- 将关键经验记录到 memory 系统

不要简化或妥协方案，除非 idea 本身被证明有根本性错误。遇到实现困难时，寻找解决办法而非回退到更简单的版本。"""


class ConclusionAgent(BaseAgent):
    def __init__(self, config_path="config.yaml"):
        tc = load_topic_config(config_path)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=tc["topic_title"],
        )

        super().__init__(
            name="结论总结Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=20,
        )
        self.register_tool("read_file", read_file, READ_FILE_SCHEMA)
        self.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
        self.register_tool("list_directory", list_directory, LIST_DIRECTORY_SCHEMA)
        self.register_tool("query_memory", query_memory, QUERY_MEMORY_SCHEMA)
        self.register_tool("add_experience", add_experience, ADD_EXPERIENCE_SCHEMA)
