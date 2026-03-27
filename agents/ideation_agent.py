"""Idea 生成 Agent：基于文献 gap 发散生成研究 idea（增强版：ReAct 循环、去重、关系图）"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import extract_topic_title
from tools.file_ops import read_file, write_file, list_directory
from tools.idea_registry import add_idea, read_research_status
from tools.memory import query_memory
from tools.web_search import web_search
from tools.openalex import search_papers
from tools.knowledge_index import check_local_knowledge
from functools import partial
from tools.idea_graph import (
    add_idea_relationship, get_idea_graph,
)
from shared.models.tool_params import (
    ReadFileParams, WriteFileParams, ListDirectoryParams,
    AddIdeaParams, ReadResearchStatusParams, QueryMemoryParams, CheckLocalKnowledgeParams,
    WebSearchParams, SearchPapersParams,
    AddRelationshipParams, GetGraphParams,
)

SYSTEM_PROMPT_TEMPLATE = """你是 AI 科研创意专家。你的任务是基于文献综述中的 research gap，
针对"{topic_title}"生成创新的研究 idea。

## ReAct 循环流程

对每个 idea，执行以下循环:
1. **Think**: 基于 survey 和 baselines 思考一个方向
2. **Search（至少 3 次查询）**:
   a. 核心方法英文关键词: search_papers(query="...", year_range="2022-")
   b. 方法 + 应用场景组合: search_papers(query="...", limit=5)
   c. web_search 搜最新预印本: web_search("方法名 arxiv 2024 2025")
   d. 如果找到高度相似工作，必须在 proposal 中说明差异或放弃该方向
3. **Refine**: 根据搜索结果，调整 idea 的创新点
4. **Generate**: 确认无重复后，写出完整的 proposal

## 去重约束

生成 idea 前，必须:
1. 用 read_research_status 检查已有 idea 列表
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

## 每个 idea 需要包含（proposal.md ≥800字）

- 标题（简洁有力）
- 动机: ≥150字，为什么这个方向可能有效，引用 survey 中的具体 gap
- 核心方法描述: ≥300字，分 2-3 段详细说明技术路线，不要只写一句话概括
- 预期效果: 具体说明在哪些指标上预期提升多少，依据是什么
- 可能的风险/局限: ≥100字，至少列 2 个风险及缓解思路
- 相关文献支撑: 至少引用 3 篇相关论文，说明借鉴/改进关系
- 实现难度估计（1-5）及理由

## 输出

将每个 idea 写入 ideas/{{idea_id}}_{{shortname}}/proposal.md
用 add_idea 注册到 idea 注册表
用 add_idea_relationship 记录 idea 间的关系
最后用 get_idea_graph 生成并保存关系图

注意避免与已失败的方向重复。

不要简化或妥协方案，除非 idea 本身被证明有根本性错误。遇到实现困难时，寻找解决办法而非回退到更简单的版本。"""


class IdeationAgent(BaseAgent):
    def __init__(self, topic_dir: str, allowed_dirs: list[str] = None):
        topic_title = extract_topic_title(topic_dir)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=topic_title,
        )

        super().__init__(
            name="Idea生成Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=20,
            allowed_dirs=allowed_dirs,
        )
        self.register_tool("read_file", read_file, ReadFileParams)
        self.register_tool("write_file", write_file, WriteFileParams)
        self.register_tool("list_directory", list_directory, ListDirectoryParams)
        self.register_tool("add_idea", add_idea, AddIdeaParams)
        self.register_tool("read_research_status", read_research_status, ReadResearchStatusParams)
        self.register_tool("query_memory", query_memory, QueryMemoryParams)
        self.register_tool("web_search", web_search, WebSearchParams)
        self.register_tool("search_papers", search_papers, SearchPapersParams)
        self.register_tool("check_local_knowledge", check_local_knowledge, CheckLocalKnowledgeParams)
        # 绑定 topic_dir，Agent 无需手动传递
        self.register_tool("add_idea_relationship",
                           partial(add_idea_relationship, topic_dir=topic_dir),
                           AddRelationshipParams)
        self.register_tool("get_idea_graph",
                           partial(get_idea_graph, topic_dir=topic_dir),
                           GetGraphParams)

    def build_prompt(self, *, topic_title: str, survey: str = "",
                     baselines: str = "", datasets_md: str = "",
                     metrics_md: str = "", failed: str = "",
                     context: str = "", ideas_dir: str) -> str:
        self._output_paths = [ideas_dir]
        existing = self._scan_existing_outputs()
        return existing + f"""基于以下综述生成研究 idea:

## 研究课题
{topic_title}

## 综述
{survey[:80000]}

## Baselines
{baselines[:20000]}

## 可用数据集
{datasets_md[:10000]}

## 评估指标
{metrics_md[:10000]}

## 已失败的方向（避免重复）
{failed}

{context}

根据 survey 和 context.md 的内容，从多个研究角度生成 idea:
- 分析 survey 中各方法的不足，针对性提出改进
- 从理论/方法/实验/应用等不同层面思考
- 每个 idea 只包含一个核心创新点

每个 idea 创建对应的 {ideas_dir}/{{idea_id}}_{{shortname}}/proposal.md，
并用 add_idea 注册到 idea 注册表。
生成完毕后用 add_idea_relationship 记录 idea 间的关系，
最后用 get_idea_graph 生成关系图。"""
