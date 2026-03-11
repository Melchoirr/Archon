"""Idea 生成 Agent：基于文献 gap 发散生成研究 idea（增强版：ReAct 循环、去重、关系图）"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.file_ops import read_file, write_file, list_directory, READ_FILE_SCHEMA, WRITE_FILE_SCHEMA, LIST_DIRECTORY_SCHEMA
from tools.research_tree import add_idea_to_tree, read_tree, ADD_IDEA_SCHEMA, READ_TREE_SCHEMA
from tools.memory import query_memory, QUERY_MEMORY_SCHEMA
from tools.web_search import web_search, WEB_SEARCH_SCHEMA
from tools.semantic_scholar import search_papers, SEARCH_PAPERS_SCHEMA
from tools.idea_graph import (
    add_idea_relationship, get_idea_graph,
    ADD_RELATIONSHIP_SCHEMA, GET_GRAPH_SCHEMA,
)

SYSTEM_PROMPT_TEMPLATE = """你是 AI 科研创意专家。你的任务是基于文献综述中的 research gap，
针对"{topic_title}"生成创新的研究 idea。

## ReAct 循环流程

对每个 idea，执行以下循环:
1. **Think**: 基于 survey 和 baselines 思考一个方向
2. **Search**: 用 search_papers 或 web_search 验证该方向是否已有人做过
3. **Refine**: 根据搜索结果，调整 idea 的创新点
4. **Generate**: 确认无重复后，写出完整的 proposal

## 去重约束

生成 idea 前，必须:
1. 用 read_tree 检查已有 idea 列表
2. 用 list_directory 查看 ideas/ 目录下的现有 idea
3. 确保新 idea 的核心创新点与已有 idea **不重复**
4. 如果方向相似但角度不同，在 proposal 中明确说明差异

## 原子性约束

每个 idea **只允许一个核心创新点**:
- 不要把多个改进打包成一个 idea
- 如果一个方向有多个可能的改进，拆分为独立的 idea
- idea 之间可以有关系（互补、组合、替代），用 add_idea_relationship 记录

## 生成角度

根据 survey 和 context.md 的内容，从多个研究角度生成 idea:
- 分析 survey 中各方法的不足，针对性提出改进
- 从理论/方法/实验/应用等不同层面思考
- 每个 idea 只包含一个核心创新点

## 每个 idea 需要包含

- 标题（简洁有力）
- 动机（为什么这个方向可能有效）
- 核心方法描述（2-3 段）
- 预期效果
- 可能的风险/局限
- 相关文献支撑
- 实现难度估计（1-5）

## 输出

将每个 idea 写入 ideas/{idea_id}_{shortname}/proposal.md
用 add_idea_to_tree 注册到研究树
用 add_idea_relationship 记录 idea 间的关系
最后用 get_idea_graph 生成并保存关系图

注意避免与已失败的方向重复。

不要简化或妥协方案，除非 idea 本身被证明有根本性错误。遇到实现困难时，寻找解决办法而非回退到更简单的版本。"""


class IdeationAgent(BaseAgent):
    def __init__(self, config_path="config.yaml"):
        tc = load_topic_config(config_path)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=tc["topic_title"],
        )

        super().__init__(
            name="Idea生成Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=25,
        )
        self.register_tool("read_file", read_file, READ_FILE_SCHEMA)
        self.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
        self.register_tool("list_directory", list_directory, LIST_DIRECTORY_SCHEMA)
        self.register_tool("add_idea_to_tree", add_idea_to_tree, ADD_IDEA_SCHEMA)
        self.register_tool("read_tree", read_tree, READ_TREE_SCHEMA)
        self.register_tool("query_memory", query_memory, QUERY_MEMORY_SCHEMA)
        self.register_tool("web_search", web_search, WEB_SEARCH_SCHEMA)
        self.register_tool("search_papers", search_papers, SEARCH_PAPERS_SCHEMA)
        self.register_tool("add_idea_relationship", add_idea_relationship, ADD_RELATIONSHIP_SCHEMA)
        self.register_tool("get_idea_graph", get_idea_graph, GET_GRAPH_SCHEMA)
