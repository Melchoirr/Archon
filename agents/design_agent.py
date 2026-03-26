"""方案展开 Agent：将 idea 展开为详细的技术方案"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import extract_topic_title
from tools.file_ops import read_file, write_file
from tools.idea_registry import read_research_status
from tools.memory import query_memory
from tools.web_search import web_search
from tools.openalex import search_papers
from tools.knowledge_index import check_local_knowledge
from shared.models.tool_params import (
    ReadFileParams, WriteFileParams, ReadResearchStatusParams,
    QueryMemoryParams, WebSearchParams, SearchPapersParams,
    CheckLocalKnowledgeParams,
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
   - 消融实验设计: 每个创新组件对应一个消融实验
5. **风险评估**（≥200字）: 至少 3 个可能失败的原因，每个配缓解策略

不要用"详见 xxx"省略内容，所有关键设计必须在本文档中写完整。
## 可用工具

| 工具 | 用途 |
|------|------|
| read_research_status | 开始前读取研究状态，了解当前 idea 状态 |
| read_file | 读取 proposal.md、survey 文档、已有论文笔记等输入材料 |
| write_file | 将 design.md 写入 idea 目录 |
| query_memory | 查询历史经验，复用成功方案、避免已知陷阱 |
| search_papers | 搜索相关论文，获取 baseline 方法和典型超参数 |
| web_search | 搜索技术博客、实现细节等补充信息 |
| (FSM 自动管理阶段状态) | |

## 工作流

1. read_research_status() → 确认目标 idea 的当前状态
2. read_file() → 读取 proposal.md 获取 idea 描述
3. query_memory() → 查询相关历史经验
4. search_papers() / web_search() → 补充技术细节和 baseline 信息
5. write_file() → 将完整方案写入 design.md
6. （FSM 自动管理阶段状态转移）

将方案写入对应 idea 目录下的 design.md。
更新研究树中该 idea 的 design 状态。"""


class DesignAgent(BaseAgent):
    def __init__(self, topic_dir: str):
        topic_title = extract_topic_title(topic_dir)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=topic_title,
        )

        super().__init__(
            name="方案设计Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=15,
        )
        self.register_tool("read_file", read_file, ReadFileParams)
        self.register_tool("write_file", write_file, WriteFileParams)
        self.register_tool("read_research_status", read_research_status, ReadResearchStatusParams)
        self.register_tool("query_memory", query_memory, QueryMemoryParams)
        self.register_tool("web_search", web_search, WebSearchParams)
        self.register_tool("search_papers", search_papers, SearchPapersParams)
        self.register_tool("check_local_knowledge", check_local_knowledge, CheckLocalKnowledgeParams)
