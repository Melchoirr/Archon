"""文献调研 Agent：搜索、阅读、整理学术论文（增强版：单篇总结、多轮调研、排行榜、GitHub 代码）"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.semantic_scholar import (
    search_papers, get_paper_details, get_paper_references, get_paper_citations,
    SEARCH_PAPERS_SCHEMA, GET_PAPER_DETAILS_SCHEMA, GET_PAPER_REFERENCES_SCHEMA,
    GET_PAPER_CITATIONS_SCHEMA,
)
from tools.web_search import web_search, WEB_SEARCH_SCHEMA
from tools.file_ops import read_file, write_file, list_directory, READ_FILE_SCHEMA, WRITE_FILE_SCHEMA, LIST_DIRECTORY_SCHEMA
from tools.paper_manager import (
    download_paper, read_paper_section, list_papers, search_paper_index,
    DOWNLOAD_PAPER_SCHEMA, READ_PAPER_SECTION_SCHEMA, LIST_PAPERS_SCHEMA,
    SEARCH_PAPER_INDEX_SCHEMA,
)
from tools.github_repo import (
    clone_repo, summarize_repo, list_repos,
    CLONE_REPO_SCHEMA, SUMMARIZE_REPO_SCHEMA, LIST_REPOS_SCHEMA,
)

SYSTEM_PROMPT_TEMPLATE = """你是学术文献调研专家。你的任务是:
1. 搜索与"{topic_title}"相关的论文
2. 通过 Semantic Scholar API 获取论文元数据和引用关系
3. 用网页搜索补充最新信息
4. 整理成结构化的综述文档

{search_directions}

## 单篇论文详细总结

对每篇重要论文，生成独立的 md 文件: survey/papers/<paper_slug>.md
模板:
```markdown
# <论文标题>

## 基本信息
- 作者:
- 年份:
- 会议/期刊:
- 引用数:
- Paper ID:

## 研究场景与任务
<该论文针对什么场景和任务>

## 针对的问题
<具体要解决什么问题>

## 创新点摘要
<核心贡献，1-3 点>

## 具体实现
<方法细节、公式、算法>

## 结果分析
<在哪些数据集上验证，关键指标>

## 代码 Trick
<实现中值得注意的技巧>

## 未来工作
<作者提到的未来方向>

## 与本课题的关系
<如何与我们的研究课题关联>
```

## 引用论文展开

对关键论文的重要引用，也需要递归展开:
- 使用 get_paper_references 获取参考文献列表
- 使用 get_paper_citations 获取引用了该论文的后续论文
- 对高相关的引用论文也生成独立总结

## GitHub 代码拉取

对有开源代码的重要论文:
1. 用 web_search 搜索 "论文名 github" 找到仓库地址
2. 用 clone_repo 拉取代码
3. 用 summarize_repo 生成代码摘要

## 排行榜

生成 survey/leaderboard.md:
- 按任务分组
- 列出各方法在标准 benchmark 上的指标
- 标注最优方法

## 多轮调研

如果收到 round 参数 > 1，表示这是第 N 轮调研:
- 阅读上一轮的 survey/index.md，了解已覆盖的内容
- 扩大搜索范围（新关键词、相关领域、最新论文）
- 补充上一轮遗漏的方向

## 输出要求

1. survey/survey.md - 综合文献综述
2. survey/index.md - 所有论文摘要索引（含链接到单篇总结）
3. survey/leaderboard.md - 排行榜
4. survey/papers/*.md - 单篇论文详细总结
5. baselines.md - baseline 方法总结
6. datasets.md - 推荐数据集
7. metrics.md - 推荐评估指标

格式使用 Markdown，中文撰写。

深入阅读策略:
- 对关键论文，调用 download_paper 下载 PDF 并解析
- 用 read_paper_section 阅读 method 和 experiment 部分
- 先调用 read_paper_section(paper_id) 不带 section 参数查看结构概览

不要简化或妥协方案，除非 idea 本身被证明有根本性错误。遇到实现困难时，寻找解决办法而非回退到更简单的版本。"""


def _build_search_directions(topic_config: dict) -> str:
    """根据 config 构建搜索方向提示"""
    keywords = topic_config.get("search_keywords", [])
    if keywords:
        lines = ["搜索方向:"] + [f"- {kw}" for kw in keywords]
        return "\n".join(lines)
    title = topic_config["topic_title"]
    domain = topic_config.get("topic_domain", "")
    return f"请根据课题 \"{title}\"（领域: {domain}）自行确定 5-8 个搜索关键词方向，覆盖问题定义、方法流派、相关技术。"


class LiteratureAgent(BaseAgent):
    def __init__(self, config_path="config.yaml"):
        tc = load_topic_config(config_path)

        search_directions = _build_search_directions(tc)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=tc["topic_title"],
            search_directions=search_directions,
        )

        super().__init__(
            name="文献调研Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=40,
        )
        self.register_tool("search_papers", search_papers, SEARCH_PAPERS_SCHEMA)
        self.register_tool("get_paper_details", get_paper_details, GET_PAPER_DETAILS_SCHEMA)
        self.register_tool("get_paper_references", get_paper_references, GET_PAPER_REFERENCES_SCHEMA)
        self.register_tool("get_paper_citations", get_paper_citations, GET_PAPER_CITATIONS_SCHEMA)
        self.register_tool("web_search", web_search, WEB_SEARCH_SCHEMA)
        self.register_tool("read_file", read_file, READ_FILE_SCHEMA)
        self.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
        self.register_tool("list_directory", list_directory, LIST_DIRECTORY_SCHEMA)
        self.register_tool("download_paper", download_paper, DOWNLOAD_PAPER_SCHEMA)
        self.register_tool("read_paper_section", read_paper_section, READ_PAPER_SECTION_SCHEMA)
        self.register_tool("list_papers", list_papers, LIST_PAPERS_SCHEMA)
        self.register_tool("clone_repo", clone_repo, CLONE_REPO_SCHEMA)
        self.register_tool("summarize_repo", summarize_repo, SUMMARIZE_REPO_SCHEMA)
        self.register_tool("list_repos", list_repos, LIST_REPOS_SCHEMA)
        self.register_tool("search_paper_index", search_paper_index, SEARCH_PAPER_INDEX_SCHEMA)
