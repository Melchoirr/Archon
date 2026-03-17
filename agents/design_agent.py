"""方案展开 Agent：将 idea 展开为详细的技术方案"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.file_ops import read_file, write_file
from tools.research_tree import read_tree, update_idea_phase
from tools.memory import query_memory
from tools.web_search import web_search
from tools.openalex import search_papers
from shared.models.tool_params import (
    ReadFileParams, WriteFileParams, ReadTreeParams, UpdateIdeaPhaseParams,
    QueryMemoryParams, WebSearchParams, SearchPapersParams,
)

SYSTEM_PROMPT_TEMPLATE = """你是 AI 科研方案设计专家。你的任务是将一个研究 idea 展开为详细的技术方案。

研究课题: {topic_title}

方案需要包含（design.md 总计 ≥2000字）:
1. **问题定义**（≥300字）: 形式化的问题描述，含输入/输出定义、约束条件、目标函数
2. **方法详述**（≥800字）:
   - 数学公式推导: 关键公式必须完整写出，每个变量注明含义
   - 算法伪代码: 至少包含核心算法的完整伪代码
   - 关键实现细节: 数据流维度变化、关键超参数选择依据
3. **与现有方法的对比**（≥300字）: 与 baseline 的理论差异，用表格对比关键设计决策
4. **实验设计初步方案**（≥300字）:
   - 数据集：{dataset_names}
   - 评估指标：{metric_names}
   - 消融实验设计: 每个创新组件对应一个消融实验
5. **风险评估**（≥200字）: 至少 3 个可能失败的原因，每个配缓解策略

不要用"详见 xxx"省略内容，所有关键设计必须在本文档中写完整。
将方案写入对应 idea 目录下的 design.md。
更新研究树中该 idea 的 design 状态。"""


class DesignAgent(BaseAgent):
    def __init__(self, config_path="config.yaml"):
        tc = load_topic_config(config_path)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=tc.topic.title,
            dataset_names=tc.dataset_names,
            metric_names=tc.metric_names,
        )

        super().__init__(
            name="方案设计Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=15,
        )
        self.register_tool("read_file", read_file, ReadFileParams)
        self.register_tool("write_file", write_file, WriteFileParams)
        self.register_tool("read_tree", read_tree, ReadTreeParams)
        self.register_tool("update_idea_phase", update_idea_phase, UpdateIdeaPhaseParams)
        self.register_tool("query_memory", query_memory, QueryMemoryParams)
        self.register_tool("web_search", web_search, WebSearchParams)
        self.register_tool("search_papers", search_papers, SearchPapersParams)
