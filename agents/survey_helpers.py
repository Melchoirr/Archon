"""Survey 流水线辅助：agent 工厂函数 + 单篇论文总结"""
import os
import re
import logging

from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.semantic_scholar import (
    search_papers, get_paper_references, get_paper_citations,
    SEARCH_PAPERS_SCHEMA, GET_PAPER_REFERENCES_SCHEMA, GET_PAPER_CITATIONS_SCHEMA,
)
from tools.web_search import web_search, WEB_SEARCH_SCHEMA
from tools.file_ops import (
    read_file, write_file, list_directory,
    READ_FILE_SCHEMA, WRITE_FILE_SCHEMA, LIST_DIRECTORY_SCHEMA,
)
from tools.paper_manager import (
    search_paper_index, SEARCH_PAPER_INDEX_SCHEMA,
)
from tools.github_repo import (
    clone_repo, summarize_repo, list_repos,
    CLONE_REPO_SCHEMA, SUMMARIZE_REPO_SCHEMA, LIST_REPOS_SCHEMA,
)

import anthropic

logger = logging.getLogger(__name__)

# ---------- Step 1: 搜索论文 ----------

_SEARCH_SYSTEM = """你是学术文献搜索专家。你的任务是为课题"{topic_title}"搜集高质量的相关论文列表。

{search_directions}

## 工作流程

1. 用 search_papers 按多个关键词方向搜索论文
2. 读摘要判断覆盖度，动态生成新查询补充遗漏方向
3. 用 get_paper_references / get_paper_citations 展开引用链，发现重要论文
4. 用 search_paper_index 检查已有论文，避免重复
5. 最终将完整的论文列表写入 paper_list.yaml

## paper_list.yaml 格式

```yaml
papers:
  - paper_id: "abc123"
    title: "Autoformer: ..."
    year: 2021
    citation_count: 4114
    arxiv_id: "2106.13008"        # 如果有
    venue: "NeurIPS"
    authors: ["Haixu Wu", "..."]
    open_access_url: "https://..."  # 如果有
    relevance: "时序分解+自相关机制"
    download_status: pending
    summary_status: pending
```

## 要求
- 搜集 15-30 篇高质量论文（优先高引用、顶会/顶刊）
- 覆盖问题定义、主流方法、前沿进展、相关技术
- 每篇论文必须填写 relevance 字段说明与课题的关联
- arxiv_id 从 externalIds 中提取 ArXiv 字段，没有则留空
- open_access_url 从搜索结果的 openAccessPdf 字段提取
- 按 citation_count 降序排列"""


def _build_search_directions(topic_config: dict) -> str:
    keywords = topic_config.get("search_keywords", [])
    if keywords:
        lines = ["搜索方向:"] + [f"- {kw}" for kw in keywords]
        return "\n".join(lines)
    title = topic_config["topic_title"]
    domain = topic_config.get("topic_domain", "")
    return f'请根据课题 "{title}"（领域: {domain}）自行确定 5-8 个搜索关键词方向，覆盖问题定义、方法流派、相关技术。'


def make_search_agent(config_path: str) -> BaseAgent:
    """Step 1: 搜索论文，输出 paper_list.yaml"""
    tc = load_topic_config(config_path)
    search_directions = _build_search_directions(tc)
    system_prompt = _SEARCH_SYSTEM.format(
        topic_title=tc["topic_title"],
        search_directions=search_directions,
    )

    agent = BaseAgent(
        name="论文搜索Agent",
        system_prompt=system_prompt,
        tools=[],
        max_iterations=15,
    )
    agent.register_tool("search_papers", search_papers, SEARCH_PAPERS_SCHEMA)
    agent.register_tool("get_paper_references", get_paper_references, GET_PAPER_REFERENCES_SCHEMA)
    agent.register_tool("get_paper_citations", get_paper_citations, GET_PAPER_CITATIONS_SCHEMA)
    agent.register_tool("web_search", web_search, WEB_SEARCH_SCHEMA)
    agent.register_tool("search_paper_index", search_paper_index, SEARCH_PAPER_INDEX_SCHEMA)
    agent.register_tool("read_file", read_file, READ_FILE_SCHEMA)
    agent.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
    agent.register_tool("list_directory", list_directory, LIST_DIRECTORY_SCHEMA)
    return agent


# ---------- Step 3: 单篇论文总结 ----------

_SUMMARY_TEMPLATE = """请根据以下论文全文，生成结构化总结。

## 论文标题
{paper_title}

## 论文全文（可能截断）
{paper_text}

## 输出格式

请严格按以下模板输出:

# {paper_title}

## 基本信息
- 作者:（从全文推断）
- 年份:（从全文推断）
- 会议/期刊:（从全文推断）
- Paper ID:（留空）

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
<与课题"{topic_title}"的关联>"""

_ABSTRACT_SUMMARY_TEMPLATE = """请根据以下论文摘要，生成结构化总结。注意：此总结仅基于摘要，非全文精读。

## 论文标题
{paper_title}

## 摘要
{abstract}

## 输出格式

请严格按以下模板输出（基于摘要能推断的部分尽量填写，无法确定的标注"需全文确认"）:

# {paper_title}

## 基本信息
- 作者:（从摘要推断）
- 年份:（从摘要推断）
- 会议/期刊:（未知）
- Paper ID:（留空）
- 数据来源: 仅摘要

## 研究场景与任务
## 针对的问题
## 创新点摘要
## 具体实现
## 结果分析
## 代码 Trick
## 未来工作
## 与本课题的关系
<与课题"{topic_title}"的关联>"""


def summarize_single_paper(client, model: str, paper_title: str, paper_text: str,
                           topic_title: str, topic_id: str,
                           abstract_only: bool = False) -> str:
    """Step 3: 单次 LLM 调用生成论文总结（无工具循环）

    Args:
        client: anthropic.Anthropic 实例
        model: 模型名
        paper_title: 论文标题
        paper_text: 论文全文 markdown 或摘要文本
        topic_title: 课题标题
        topic_id: 课题 ID
        abstract_only: 是否仅基于摘要

    Returns:
        生成的总结 markdown 文本
    """
    MAX_TEXT_CHARS = 12000

    if abstract_only:
        prompt = _ABSTRACT_SUMMARY_TEMPLATE.format(
            paper_title=paper_title,
            abstract=paper_text[:3000],
            topic_title=topic_title,
        )
    else:
        truncated = paper_text[:MAX_TEXT_CHARS]
        if len(paper_text) > MAX_TEXT_CHARS:
            truncated += f"\n\n... [全文共 {len(paper_text)} 字符，已截断至 {MAX_TEXT_CHARS}]"
        prompt = _SUMMARY_TEMPLATE.format(
            paper_title=paper_title,
            paper_text=truncated,
            topic_title=topic_title,
        )

    response = client.messages.create(
        model=model,
        system="你是学术论文分析专家，擅长提取论文核心信息并生成结构化总结。",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4096,
    )

    result = ""
    for block in response.content:
        if block.type == "text":
            result += block.text

    # 在顶部加 topic 标记
    header = f"<!-- topic: {topic_id}, phase: survey -->\n"
    return header + result


# ---------- Step 4: 代码仓库调研 ----------

_REPO_SYSTEM = """你是代码仓库调研专家。你的任务是为课题"{topic_title}"搜索和分析相关的开源代码仓库。

## 工作流程

1. 读取论文总结目录，识别有开源代码的关键论文
2. 用 web_search 搜索 "论文名 github" 或 "方法名 implementation"
3. 用 clone_repo 拉取代码
4. 用 summarize_repo 生成代码摘要
5. 将所有仓库调研结果写入 repos_summary.md

## repos_summary.md 格式

```markdown
# 代码仓库调研

## 仓库列表

### 1. [仓库名](github_url)
- 对应论文: xxx
- 语言/框架: PyTorch / TensorFlow / ...
- 代码质量: 高/中/低
- 关键实现:
  - 模型结构: xxx
  - 训练流程: xxx
  - 数据处理: xxx
- 可复用性: 高/中/低
- 备注: xxx
```

## 要求
- 优先搜索高引用论文和关键方法的代码
- 重点关注模型结构和训练方法的实现
- 评估代码质量和可复用性"""


def make_repo_agent(config_path: str) -> BaseAgent:
    """Step 4: 搜索和分析代码仓库"""
    tc = load_topic_config(config_path)
    system_prompt = _REPO_SYSTEM.format(topic_title=tc["topic_title"])

    agent = BaseAgent(
        name="代码仓库Agent",
        system_prompt=system_prompt,
        tools=[],
        max_iterations=10,
    )
    agent.register_tool("web_search", web_search, WEB_SEARCH_SCHEMA)
    agent.register_tool("clone_repo", clone_repo, CLONE_REPO_SCHEMA)
    agent.register_tool("summarize_repo", summarize_repo, SUMMARIZE_REPO_SCHEMA)
    agent.register_tool("list_repos", list_repos, LIST_REPOS_SCHEMA)
    agent.register_tool("read_file", read_file, READ_FILE_SCHEMA)
    agent.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
    agent.register_tool("list_directory", list_directory, LIST_DIRECTORY_SCHEMA)
    return agent


# ---------- Step 5: 综合整理 ----------

_SYNTHESIS_SYSTEM = """你是学术综述撰写专家。你的任务是基于已有的论文总结和代码仓库调研，为课题"{topic_title}"生成综合文档。

## 需要生成的文件

1. **survey/survey.md** - 综合文献综述
   - 整合所有论文分析 + 代码仓库发现
   - 按主题/方法分类组织
   - 包含方法对比和发展脉络
   - 指出当前研究的不足和未来方向

2. **survey/leaderboard.md** - 排行榜
   - 按任务分组
   - 列出各方法在标准 benchmark 上的指标
   - 标注最优方法

3. **baselines.md** - Baseline 方法
   - 主流方法总结
   - 含代码实现质量评价（参考 repos_summary.md）
   - 推荐的 baseline 组合

4. **datasets.md** - 推荐数据集
   - 数据集名称、规模、特点
   - 下载方式
   - 适用任务

5. **metrics.md** - 推荐指标
   - 指标名称、公式
   - 适用场景
   - 业界常用组合

## 要求
- 综述要有深度，不是简单罗列
- 分析方法间的关系和演进
- 结合代码实现情况评估方法可行性
- 中文撰写，术语保持英文原文"""


def make_synthesis_agent(config_path: str) -> BaseAgent:
    """Step 5: 读 summaries + repos_summary 写综述文档"""
    tc = load_topic_config(config_path)
    system_prompt = _SYNTHESIS_SYSTEM.format(topic_title=tc["topic_title"])

    agent = BaseAgent(
        name="综合整理Agent",
        system_prompt=system_prompt,
        tools=[],
        max_iterations=8,
    )
    agent.register_tool("read_file", read_file, READ_FILE_SCHEMA)
    agent.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
    agent.register_tool("list_directory", list_directory, LIST_DIRECTORY_SCHEMA)
    return agent
