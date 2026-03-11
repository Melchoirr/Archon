"""方案展开 Agent：将 idea 展开为详细的技术方案"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.file_ops import read_file, write_file, READ_FILE_SCHEMA, WRITE_FILE_SCHEMA
from tools.research_tree import read_tree, update_tree, READ_TREE_SCHEMA, UPDATE_TREE_SCHEMA
from tools.memory import query_memory, QUERY_MEMORY_SCHEMA
from tools.web_search import web_search, WEB_SEARCH_SCHEMA
from tools.semantic_scholar import search_papers, SEARCH_PAPERS_SCHEMA

SYSTEM_PROMPT_TEMPLATE = """你是 AI 科研方案设计专家。你的任务是将一个研究 idea 展开为详细的技术方案。

研究课题: {topic_title}

方案需要包含:
1. **问题定义**: 形式化的问题描述
2. **方法详述**:
   - 数学公式推导
   - 算法伪代码
   - 关键实现细节
3. **与现有方法的对比**: 与 baseline 的理论差异
4. **实验设计初步方案**:
   - 数据集：{dataset_names}
   - 评估指标：{metric_names}
   - 消融实验设计
5. **风险评估**: 可能失败的原因及缓解策略

将方案写入对应 idea 目录下的 design.md。
更新研究树中该 idea 的 design 状态。"""


class DesignAgent(BaseAgent):
    def __init__(self, config_path="config.yaml"):
        tc = load_topic_config(config_path)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=tc["topic_title"],
            dataset_names=tc["dataset_names"],
            metric_names=tc["metric_names"],
        )

        super().__init__(
            name="方案设计Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=20,
        )
        self.register_tool("read_file", read_file, READ_FILE_SCHEMA)
        self.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
        self.register_tool("read_tree", read_tree, READ_TREE_SCHEMA)
        self.register_tool("update_tree", update_tree, UPDATE_TREE_SCHEMA)
        self.register_tool("query_memory", query_memory, QUERY_MEMORY_SCHEMA)
        self.register_tool("web_search", web_search, WEB_SEARCH_SCHEMA)
        self.register_tool("search_papers", search_papers, SEARCH_PAPERS_SCHEMA)
