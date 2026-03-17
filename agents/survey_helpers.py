"""Survey 流水线辅助：agent 工厂函数 + 单篇论文总结"""
import os
import re
import logging

from .base_agent import BaseAgent, llm_call_with_retry
from shared.utils.config_helpers import load_topic_config
from tools.openalex import (
    search_papers, search_topics, get_paper_references, get_paper_citations,
)
from tools.web_search import web_search
from tools.file_ops import (
    read_file, write_file, list_directory,
)
from tools.paper_manager import (
    search_paper_index,
)
from tools.github_repo import (
    clone_repo, summarize_repo, list_repos,
)
from shared.models.tool_params import (
    SearchTopicsParams, SearchPapersParams, GetPaperReferencesParams, GetPaperCitationsParams,
    WebSearchParams, ReadFileParams, WriteFileParams, ListDirectoryParams,
    SearchPaperIndexParams, CloneRepoParams, SummarizeRepoParams, ListReposParams,
)

import anthropic

logger = logging.getLogger(__name__)

# ---------- Step 1: 搜索论文 ----------

_SEARCH_SYSTEM = """你是学术文献搜索专家，为课题"{topic_title}"搜集 15-30 篇高质量论文。

{search_directions}

## 工具说明

| 工具 | 关键参数 | 返回 |
|------|---------|------|
| search_topics | query | JSON 数组: topic_id, name, works_count — **第一步：找到领域 topic_id** |
| search_papers | query, limit, min_citations, topic_id, search_mode, sort | JSON 数组: paperId, title, year, citationCount, venue, authors, topics, externalIds.ArXiv, openAccessPdf.url |
| get_paper_references | paper_id (用 paperId 字段) | JSON 数组: citedPaper 对象，字段同上 |
| get_paper_citations | paper_id | JSON 数组: citingPaper 对象，字段同上 |
| web_search | query | JSON 数组: title, href, body — **仅在 search_papers 返回 Error 时使用** |
| search_paper_index | query | 已入库论文匹配列表，用于去重 |

## ⚠️ 关键：search_papers 三种搜索模式

search_papers 支持三种搜索模式（search_mode 参数）：

### 1. keyword 模式（默认）
- 适合短关键词组合（2-4 个英文词），如 `query="mean reversion forecasting"`
- 支持引号精确短语：`query='"mean reversion" forecasting'`（引号内词组不会被拆分）
- 支持近邻搜索：`query='"mean reversion forecasting"~5'`（词间距≤5）
- 支持通配符：`query="machin* learning"`（匹配 machine, machines 等）
- 支持 Boolean：`query="diffusion AND time series NOT image"`
- **禁止用长句子**，长句子应使用 semantic 模式

### 2. semantic 模式
- 适合长自然语言描述和探索性查询
- 例：`search_papers(query="using diffusion models for time series generation with mean reversion properties", search_mode="semantic")`
- 限制：1 req/s，最多返回 50 条
- **当 keyword 模式结果不相关时，切换到 semantic 模式重试**

### 3. exact 模式
- 不做词干化（stemming），"surgery" 不匹配 "surgical"
- 适合需要精确词形匹配的场景

### 排序说明
- 默认 sort="relevance"（按相关性排序，推荐）
- 需要高引论文时显式传 sort="citationCount:desc"

## 执行流程

**阶段零：确定领域 topic_id**（首次必做，1 轮）
0. 调用 search_topics(query="课题核心领域关键词") 获取 1-2 个最相关的 topic_id
   例如课题是时序预测，调用 search_topics(query="time series forecasting")
   记住返回的 topic_id（如 T12205），后续所有 search_papers 都带上此参数

**阶段一：逐查询搜索**（核心，用 search_papers + topic_id）
对上述每个查询依次:
1. 调用 search_papers(query=查询词, limit=15, min_citations=10, topic_id=上面获得的 topic_id)
   - 精确概念用引号包裹：`query='"mean reversion" forecasting'`
2. 如果结果不相关或为空 → **先切换 semantic 模式重试**（用完整自然语言描述）
3. 仍不相关 → 不带 topic_id 重试（扩大范围），或降低 min_citations 为 0
4. 仅当 search_papers 返回 "Error" 时 → 改用 web_search(query="查询词 site:arxiv.org OR site:semanticscholar.org")
5. 不要对同一查询重试超过 3 次，直接推进下一个
6. 如果返回结果中有 topics 字段，观察是否有更精确的 topic_id 可用于后续搜索

**阶段二：引用链展开**（如剩余轮次 ≥ 5）
7. 选 citationCount 最高的 3-5 篇论文
8. 调用 get_paper_references(paper_id=该论文的 paperId)
9. 调用 search_paper_index(query=标题关键词) 检查重复，跳过已有论文

**阶段三：写入**（必须执行）
10. 调用 write_file 写入 paper_list.yaml，按 citation_count 降序
11. 即使不足 10 篇也必须写入

## paper_list.yaml 格式
papers:
  - paper_id: "W..."          # paperId 字段
    title: "..."
    year: 2021
    citation_count: 4114       # citationCount 字段
    arxiv_id: "2106.13008"     # externalIds.ArXiv，无则空字符串
    venue: "NeurIPS"
    authors: ["Author1"]
    open_access_url: "..."     # openAccessPdf.url，无则空字符串
    relevance: "与课题关联说明"
    download_status: pending
    summary_status: pending"""


def _build_search_directions(topic_config) -> str:
    keywords = topic_config.search_keywords
    title = topic_config.topic.title
    domain = topic_config.topic.domain

    if not keywords:
        return (
            f'请根据课题 "{title}"（领域: {domain}）自行确定 8-12 个搜索方向。\n'
            f'- 短关键词（2-4 词）用 keyword 模式\n'
            f'- 精确概念用引号包裹，如 `\'"mean reversion" forecasting\'`\n'
            f'- 长描述性查询用 semantic 模式'
        )

    queries = []  # (query_text, mode, note)

    # 原始关键词：截断到 4 个词，keyword 模式 + 引号包裹核心概念
    for kw in keywords:
        words = kw.split()
        short = " ".join(words[:4])
        # 如果关键词本身是多词概念（≥2词），建议引号包裹
        if len(words) >= 2:
            quoted = f'"{short}"'
            queries.append((quoted, "keyword", "精确短语"))
        else:
            queries.append((short, "keyword", ""))

    # 两两交叉：keyword 模式，引号包裹核心概念
    for i in range(len(keywords)):
        for j in range(i + 1, len(keywords)):
            t_i = keywords[i].split()[0]
            t_j = keywords[j].split()[0]
            combo = f'"{t_i}" "{t_j}"'
            queries.append((combo, "keyword", "交叉组合"))

    # 领域扩展：semantic 模式，用长描述
    domain_extras = {
        "time_series_forecasting": [
            (f"{title} with deep learning methods", "semantic", "领域扩展"),
            ("time series foundation model", "keyword", "领域扩展"),
            ("time series generation", "keyword", "领域扩展"),
        ],
    }
    queries.extend(domain_extras.get(domain, []))

    # 去重，上限 14
    seen = set()
    unique = []
    for item in queries:
        key = item[0].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    unique = unique[:14]

    lines = ["强制搜索查询列表（必须按顺序全部执行）:"]
    for i, (q, mode, note) in enumerate(unique, 1):
        mode_tag = f" [mode={mode}]" if mode != "keyword" else ""
        note_tag = f" ({note})" if note else ""
        lines.append(f"{i}. `{q}`{mode_tag}{note_tag}")
    lines.append("")
    lines.append("说明：无标注的默认用 keyword 模式。[mode=semantic] 表示用 search_mode='semantic'。")
    lines.append("如果 keyword 模式结果不相关，可切换 semantic 模式用完整自然语言描述重试。")
    return "\n".join(lines)


def build_search_prompt(*, topic: str, round_num: int, paper_list_path: str,
                        context: str = "", past_exp: str = "") -> str:
    prompt = f"开始搜索论文（第 {round_num} 轮）。\n研究课题: {topic}\n"
    if context:
        prompt += f"\n{context}\n"
    prompt += f"\n请将论文列表写入 {paper_list_path}\n"
    if round_num > 1:
        prompt += (
            f"\n这是第 {round_num} 轮调研。请:\n"
            f"1. 先调用 read_file(path='{paper_list_path}') 了解已有论文\n"
            f"2. 使用 min_citations=0, year_range='2023-' 扩大范围\n"
            f"3. 对高引论文调用 get_paper_citations 发现新方向\n"
        )
    if past_exp and "No matching" not in past_exp:
        prompt += f"\n历史经验:\n{past_exp}"
    return prompt


def make_search_agent(config_path: str, allowed_dirs: list[str] = None) -> BaseAgent:
    """Step 1: 搜索论文，输出 paper_list.yaml"""
    tc = load_topic_config(config_path)
    search_directions = _build_search_directions(tc)
    system_prompt = _SEARCH_SYSTEM.format(
        topic_title=tc.topic.title,
        search_directions=search_directions,
    )

    agent = BaseAgent(
        name="论文搜索Agent",
        system_prompt=system_prompt,
        tools=[],
        max_iterations=25,
        allowed_dirs=allowed_dirs,
    )
    agent.register_tool("search_topics", search_topics, SearchTopicsParams)
    agent.register_tool("search_papers", search_papers, SearchPapersParams)
    agent.register_tool("get_paper_references", get_paper_references, GetPaperReferencesParams)
    agent.register_tool("get_paper_citations", get_paper_citations, GetPaperCitationsParams)
    agent.register_tool("web_search", web_search, WebSearchParams)
    agent.register_tool("search_paper_index", search_paper_index, SearchPaperIndexParams)
    agent.register_tool("read_file", read_file, ReadFileParams)
    agent.register_tool("write_file", write_file, WriteFileParams)
    agent.register_tool("list_directory", list_directory, ListDirectoryParams)
    return agent


# ---------- Step 3: 单篇论文总结 ----------

_SUMMARY_TEMPLATE = """你是一位资深的学术论文分析专家。请对以下论文进行**深度、详尽**的结构化总结。
这不是简单的摘要——你需要像写一篇精读笔记一样，深入分析每个部分。

## 论文标题
{paper_title}

## 论文全文
{paper_text}

## 输出要求

**重要：每个章节必须充分展开，总输出不少于 3000 字。不要偷懒用一两句话概括，要深入分析。**

请按以下结构输出：

# {paper_title}

## 基本信息
- 作者:（列出所有作者及其机构）
- 年份:
- 会议/期刊:
- Paper ID:（留空）

## 研究场景与任务（≥200字）
详细描述该论文所处的研究领域背景、针对的具体任务类型（如长期预测、短期预测、多变量预测等）、
应用场景（如能源、交通、金融等），以及该任务在实际中的重要性。

## 针对的问题（≥200字）
深入分析现有方法的具体不足，论文指出的关键瓶颈是什么？
引用论文中的具体论述，说明为什么现有方法不够好，gap 在哪里。

## 创新点摘要（≥300字）
逐条列出核心贡献（通常 2-4 点），每个贡献需要解释：
1. 提出了什么新概念/方法
2. 为什么这个设计是合理的（motivation）
3. 与现有方法的本质区别

## 方法详解（≥500字）
这是最重要的章节，需要详细描述：
- **整体架构**：模型的宏观结构，各模块的连接关系
- **核心模块**：每个关键模块的设计思路和具体实现
- **关键公式**：列出论文中最重要的 3-5 个公式，并解释每个变量的含义
- **训练策略**：损失函数设计、优化方法、数据增强等
- **算法流程**：如果有伪代码或算法框图，描述其步骤

## 实验分析（≥400字）
- **数据集**：列出所有使用的 benchmark 数据集及其特点
- **对比方法**：主要的 baseline 有哪些
- **主实验结果**：在各数据集上的关键指标（MSE/MAE 等），与 SOTA 的对比
- **消融实验**：哪些组件的贡献最大，去掉什么会导致性能下降
- **可视化分析**：论文中有哪些有意义的可视化结果

## 局限性与不足（≥150字）
论文自身承认的局限性，以及你从分析中发现的潜在问题（如计算开销、适用范围、假设条件等）。

## 未来工作（≥150字）
作者明确提到的未来研究方向，以及基于论文分析可以延伸的方向。

## 与本课题的关系（≥200字）
深入分析该论文与课题"{topic_title}"的关联：
- 哪些方法/思路可以直接借鉴
- 哪些实验设置值得参考
- 该论文的结论对本课题有什么启示"""

_ABSTRACT_SUMMARY_TEMPLATE = """请根据以下论文摘要，生成尽可能详细的结构化总结。
注意：此总结仅基于摘要，无法确定的部分请标注"需全文确认"，但已知部分仍需充分展开分析。

## 论文标题
{paper_title}

## 摘要
{abstract}

## 输出要求

**尽量从摘要中提取最多信息，每个章节至少写 2-3 句话，不要留空。**

请按以下结构输出：

# {paper_title}

## 基本信息
- 作者:（从摘要推断）
- 年份:（从摘要推断）
- 会议/期刊:（未知）
- Paper ID:（留空）
- 数据来源: 仅摘要

## 研究场景与任务
描述该论文所处的研究领域和针对的任务类型。

## 针对的问题
现有方法的不足，论文要解决什么关键问题。

## 创新点摘要
核心贡献，逐条列出并解释 motivation。

## 方法概述
从摘要推断的方法设计思路（细节需全文确认）。

## 实验结果
摘要中提到的关键实验结果和性能提升。

## 局限性与不足
基于摘要推断的潜在局限（需全文确认）。

## 未来工作
可能的研究延伸方向。

## 与本课题的关系
与课题"{topic_title}"的关联分析：可借鉴之处、对本课题的启示。"""


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
    if abstract_only:
        prompt = _ABSTRACT_SUMMARY_TEMPLATE.format(
            paper_title=paper_title,
            abstract=paper_text,
            topic_title=topic_title,
        )
    else:
        prompt = _SUMMARY_TEMPLATE.format(
            paper_title=paper_title,
            paper_text=paper_text,
            topic_title=topic_title,
        )

    response = llm_call_with_retry(
        client,
        model=model,
        system="你是学术论文分析专家，擅长提取论文核心信息并生成结构化总结。",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=16384,  # ~65K chars，深度总结需要充足输出空间
    )

    result = ""
    for block in response.content:
        if block.type == "text":
            result += block.text

    # 在顶部加 topic 标记
    header = f"<!-- topic: {topic_id}, phase: survey -->\n"
    return header + result


# ---------- Step 4: 代码仓库调研 ----------

_REPO_SYSTEM = """你是代码仓库调研专家，为课题"{topic_title}"搜索和分析开源实现。

## 工具说明

| 工具 | 返回 |
|------|------|
| web_search(query) | JSON 数组: title, href, body |
| clone_repo(repo_url) | "Cloned ... -> knowledge/repos/名" 或 "already exists at ..." |
| summarize_repo(repo_path) | 仓库摘要 markdown（模型结构、训练方法、关键文件） |
| list_repos() | 已 clone 仓库名列表 |

## 执行流程

**步骤 1: 确定搜索目标**
1. 调用 read_file(path=论文列表路径) 读取 paper_list.yaml
2. 调用 list_directory(path=总结目录) 查看总结文件
3. 选 citation_count 前 8 的论文作为搜索目标

**步骤 2: 逐论文搜索**（最多搜 8 个仓库）
对每篇目标论文:
4. 调用 web_search(query="论文标题 github code implementation")
5. 从 href 筛选 github.com 链接
6. 无 github 链接 → 跳过该论文，继续下一篇
7. 有链接 → 调用 clone_repo(repo_url=链接)

**步骤 3: 分析仓库**
8. 对每个新 clone 的仓库调用 summarize_repo(repo_path="knowledge/repos/仓库名")
9. 重点提取: 模型结构实现、训练流程、数据处理 pipeline

**步骤 4: 写入报告**
10. 调用 write_file 写入 repos_summary.md

## repos_summary.md 格式
# 代码仓库调研
## 仓库列表
### 1. [仓库名](url)
- 对应论文: xxx
- 语言/框架: PyTorch/...
- 关键发现: （从 summarize_repo 提取核心模块+训练 trick）
- 可复用性: 高/中/低（有清晰 API=高，仅脚本=低）

## 错误处理
- clone 失败 → 记录 URL 和错误，继续下一个
- summarize_repo 失败 → 用 list_directory + read_file 手动查看核心文件

## 输出质量要求

**repos_summary.md ≥1000字（假设找到 3+ 仓库）。** 每个仓库的分析 ≥200字：
- 关键发现: 具体写出核心模块名称、训练策略、数据预处理方法（不要泛泛说"实现完整"）
- 可复用性判断: 说明判断依据（有 API 文档？有 README？有 requirements.txt？）
- 与课题的关联: 哪些模块/代码片段可以直接借鉴"""


def build_repo_prompt(*, paper_list_path: str, summaries_dir: str,
                      repos_summary_path: str) -> str:
    return f"""请调研与本课题相关的开源代码仓库。

## 关键路径
- 论文列表: {paper_list_path}
- 论文总结目录: {summaries_dir}
- 输出文件: {repos_summary_path}

## 执行步骤
1. 调用 read_file(path='{paper_list_path}') 获取论文列表
2. 调用 list_directory(path='{summaries_dir}') 查看有哪些总结可读
3. 读取高引论文的总结，识别提及开源代码的论文
4. 逐论文用 web_search 搜索 GitHub 仓库
5. clone + summarize 找到的仓库
6. 将所有结果写入 {repos_summary_path}"""


def make_repo_agent(config_path: str, allowed_dirs: list[str] = None) -> BaseAgent:
    """Step 4: 搜索和分析代码仓库"""
    tc = load_topic_config(config_path)
    system_prompt = _REPO_SYSTEM.format(topic_title=tc.topic.title)

    agent = BaseAgent(
        name="代码仓库Agent",
        system_prompt=system_prompt,
        tools=[],
        max_iterations=15,
        allowed_dirs=allowed_dirs,
    )
    agent.register_tool("web_search", web_search, WebSearchParams)
    agent.register_tool("clone_repo", clone_repo, CloneRepoParams)
    agent.register_tool("summarize_repo", summarize_repo, SummarizeRepoParams)
    agent.register_tool("list_repos", list_repos, ListReposParams)
    agent.register_tool("read_file", read_file, ReadFileParams)
    agent.register_tool("write_file", write_file, WriteFileParams)
    agent.register_tool("list_directory", list_directory, ListDirectoryParams)
    return agent


# ---------- Step 4a: EDA 规划 ----------

_EDA_GUIDE_SYSTEM = """你是数据分析规划专家，为课题"{topic_title}"从论文总结中提取数据集和分析方法。

## 工具说明

| 工具 | 用途 |
|------|------|
| list_directory(path) | 列出目录下文件名 |
| read_file(path) | 读取文件内容 |
| web_search(query) | 搜索数据集下载链接 |
| write_file(path, content) | 写入文件 |

## 执行流程

**步骤 1: 阅读全部论文总结**（先读完，再做后续步骤）
1. 调用 list_directory(path=总结目录) 获取所有 .md 文件名
2. 逐个调用 read_file 阅读每篇总结，重点关注:
   - "实验分析" 章节 → 提取数据集名称、规模、benchmark 指标
   - "方法详解" 章节 → 提取数据预处理方法、特征工程
   - "局限性" 章节 → 识别数据层面的约束

**步骤 2: 阅读仓库调研**
3. 调用 read_file(path=repos_summary_path) 补充数据处理实现细节
4. 调用 read_file(path=context_path) 了解课题方向

**步骤 3: 搜索数据集下载链接**
5. 对每个识别出的数据集:
   - 调用 web_search(query="数据集名 download csv OR parquet OR zip")
   - 从 href 中筛选纯数据文件直链（非 GitHub 仓库首页）
   - 找不到直链 → 记录搜索关键词供手动查找

**步骤 4: 写入三个文件**
6. write_file(path=eda_guide_path) — EDA 执行指南
7. write_file(path=datasets_path) — 数据集描述
8. write_file(path=metrics_path) — 评估指标

## eda_guide.md 格式
# EDA 执行指南
## 数据集列表
### 1. 数据集名
- 描述/规模/论文使用频率
- 下载链接: URL（或搜索关键词）
- 文件格式: csv/parquet/...

## 推荐 EDA 分析方法
（每项注明出处论文）
### 数据预处理
- 方法: xxx（论文 A 使用）
### 统计分析
- 方法: xxx（论文 B 使用）
### 可视化类型
- 图表类型: xxx（论文 C 中常见）
### 领域特定分析
- 需验证的数据属性: xxx（论文 D 的方法假设）

## datasets.md 格式
每个数据集: 名称、规模、特点、下载方式、各论文使用情况

## metrics.md 格式
每个指标: 名称、公式（LaTeX）、适用场景、论文中常用组合

## 输出质量要求

**不要简略概括，每个文件必须充分展开：**
- eda_guide.md: ≥1500字 — 每个数据集的描述 ≥100字，每种分析方法需注明出处论文和具体操作步骤
- datasets.md: ≥1000字 — 每个数据集 ≥150字，包含规模数值、特点分析、各论文使用情况对比
- metrics.md: ≥800字 — 每个指标需写出完整公式、适用条件、与其他指标的互补关系"""


def build_eda_guide_prompt(*, summaries_dir: str, repos_summary_path: str,
                           context_path: str, eda_guide_path: str,
                           datasets_path: str, metrics_path: str) -> str:
    return f"""请基于论文总结和代码仓库调研，生成 EDA 规划文档。

## 材料目录
- 论文总结: {summaries_dir}/
- 代码仓库调研: {repos_summary_path}
- 课题上下文: {context_path}

## 输出文件
1. {eda_guide_path} — EDA 执行指南（数据集列表 + 推荐分析方法）
2. {datasets_path} — 推荐数据集描述
3. {metrics_path} — 推荐评估指标

请先用 list_directory 和 read_file 阅读论文总结，提取各论文使用的数据集、分析方法和评估指标，
然后综合生成上述三个文件。"""


def make_eda_guide_agent(config_path: str, allowed_dirs: list[str] = None) -> BaseAgent:
    """Step 4a: 从论文提取数据集+分析方法，生成 EDA 规划"""
    tc = load_topic_config(config_path)
    system_prompt = _EDA_GUIDE_SYSTEM.format(topic_title=tc.topic.title)

    agent = BaseAgent(
        name="EDA规划Agent",
        system_prompt=system_prompt,
        tools=[],
        max_iterations=12,
        allowed_dirs=allowed_dirs,
    )
    agent.register_tool("read_file", read_file, ReadFileParams)
    agent.register_tool("write_file", write_file, WriteFileParams)
    agent.register_tool("list_directory", list_directory, ListDirectoryParams)
    agent.register_tool("web_search", web_search, WebSearchParams)
    return agent


# ---------- Step 5: 综合整理 ----------

_SYNTHESIS_SYSTEM = """你是学术综述撰写专家，为课题"{topic_title}"整合全部调研材料生成综合文档。

## 工具说明

| 工具 | 用途 |
|------|------|
| list_directory(path) | 列出目录文件 |
| read_file(path) | 读取文件（一次读取完整内容） |
| write_file(path, content) | 写入文件（一次写完整内容，不要分段追加同一文件） |

## 执行流程

**步骤 1: 阅读全部材料**（必须全部读完再写，不要边读边写）
1. 调用 list_directory(path=总结目录) → 获取文件列表
2. 逐个调用 read_file 阅读所有论文总结
3. 调用 read_file 阅读 repos_summary.md（如存在）
4. 调用 read_file 阅读 eda_report.md（如存在）
5. 调用 read_file 阅读 datasets.md 和 metrics.md（作为参考，不要重新生成）

**步骤 2: 依次写入三个文件**
6. 调用 write_file → survey.md
7. 调用 write_file → leaderboard.md
8. 调用 write_file → baselines.md

## survey.md 结构
# 综合文献综述: {topic_title}
## 1. 研究背景与问题定义
## 2. 方法分类与综述
（按方法类别分节，每节对比多篇论文的思路/性能/优劣）
## 3. 实验对比分析（引用 leaderboard 数据）
## 4. 代码实现现状（引用 repos_summary 发现）
## 5. 数据特性分析（引用 EDA 报告，如存在）
## 6. 研究不足与未来方向

## leaderboard.md 结构
按数据集分表: 方法 | 年份 | MSE | MAE | 其他 | 来源论文
用 **加粗** 标注每列最优值

## baselines.md 结构
推荐 3-5 个 baseline: 方法名、论文、核心思路、代码可用性、推荐理由

## 输出质量要求

**综述是最终交付物，必须充分展开，不要逐篇摘要式罗列。**
- survey.md: ≥5000字
  - 研究背景与问题定义: ≥500字
  - 方法分类与综述: ≥2000字，按方法类别分节，每节对比多篇论文的思路差异和性能优劣
  - 实验对比分析: ≥800字，引用 leaderboard 中的具体数值
  - 代码实现现状: ≥400字
  - 研究不足与未来方向: ≥500字，至少 3 个具体方向，每个方向说明 gap 来源和可能路径
- leaderboard.md: 每个数据集一张完整表格，数据必须来自论文总结中 "实验分析" 章节，用 **加粗** 标注最优值
- baselines.md: ≥800字，每个 baseline ≥150字，含核心思路、代码可用性评价、推荐理由
- 每个论断注明来源论文
- 论文结论冲突时，标注分歧并分析可能原因"""


def build_synthesis_prompt(*, summaries_dir: str, repos_summary_path: str,
                           repos_exists: bool, survey_dir: str,
                           baselines_path: str,
                           eda_report_path: str = None, eda_exists: bool = False,
                           datasets_path: str = None, metrics_path: str = None) -> str:
    repos_line = f"- 代码仓库调研: {repos_summary_path}" if repos_exists else "- 代码仓库调研: (未生成)"
    eda_line = f"- EDA 报告: {eda_report_path}" if eda_exists else "- EDA 报告: (未生成)"
    ref_lines = ""
    if datasets_path:
        ref_lines += f"- 数据集描述（参考）: {datasets_path}\n"
    if metrics_path:
        ref_lines += f"- 评估指标（参考）: {metrics_path}\n"
    return f"""请基于以下材料生成综合文档:

## 材料目录
- 论文总结: {summaries_dir}/
{repos_line}
{eda_line}
{ref_lines}
## 输出文件
1. {survey_dir}/survey.md - 综合文献综述
2. {survey_dir}/leaderboard.md - 排行榜
3. {baselines_path} - Baseline 方法

注意：datasets.md 和 metrics.md 已由前序步骤生成，请将其作为参考材料引用，不要重新生成。

请先用 list_directory 和 read_file 阅读所有总结文件、仓库调研报告和 EDA 报告，再生成综合文档。"""


def make_synthesis_agent(config_path: str, allowed_dirs: list[str] = None) -> BaseAgent:
    """Step 5: 读 summaries + repos_summary + eda_report 写综述文档"""
    tc = load_topic_config(config_path)
    system_prompt = _SYNTHESIS_SYSTEM.format(topic_title=tc.topic.title)

    agent = BaseAgent(
        name="综合整理Agent",
        system_prompt=system_prompt,
        tools=[],
        max_iterations=15,
        allowed_dirs=allowed_dirs,
    )
    agent.register_tool("read_file", read_file, ReadFileParams)
    agent.register_tool("write_file", write_file, WriteFileParams)
    agent.register_tool("list_directory", list_directory, ListDirectoryParams)
    return agent


# ---------- 代码参考获取 ----------

_CODE_REF_SYSTEM = """你是代码参考获取专家，根据研究方案搜索相关开源实现并分析。

## 工具说明

| 工具 | 返回 |
|------|------|
| web_search(query) | JSON 数组: title, href, body |
| clone_repo(repo_url) | "Cloned ... -> path" 或 "already exists" |
| summarize_repo(repo_path) | 仓库摘要 markdown |
| list_repos() | 已 clone 仓库列表 |

## 执行流程

**步骤 1: 提取搜索目标**
1. 分析输入的 refinement 文档，提取核心方法名/论文名（2-5 个）

**步骤 2: 逐方法搜索**
对每个方法:
2. 调用 web_search(query="论文标题 github pytorch implementation")
3. 从 href 筛选 github.com 链接
4. 无结果 → web_search(query="方法名 code open source") 重试一次
5. 仍无结果 → 记录"未找到"，继续下一个

**步骤 3: clone 并分析**
6. 调用 list_repos() 检查是否已 clone
7. 未 clone → clone_repo(repo_url=链接)
8. 调用 summarize_repo(repo_path="knowledge/repos/仓库名")

**步骤 4: 写入报告**
9. 调用 write_file 写入代码参考报告

## 输出格式
# 代码参考报告
## 1. [仓库名](url)
- 对应方法: xxx
- 关键发现: （从 summarize_repo 结果提取核心模块）
- 与本 idea 关联: 可借鉴的具体实现
- 代码质量: 高/中/低

## 错误处理
- clone 失败 → 记录错误，继续下一个
- summarize_repo 失败 → 用 list_directory + read_file 查看核心文件（model.py, train.py）

## 输出质量要求

**每个仓库的分析 ≥150字，不要只写一行。** 报告需包含：
- 关键发现: 从 summarize_repo 结果中提取核心模块名、训练 trick、数据处理方式
- 与本 idea 关联: 具体说明哪段代码/哪个模块可以借鉴，如何适配
- 代码质量判断依据: 是否有文档、测试、清晰的 API（不要凭空评价）"""


def build_code_ref_prompt(*, ref_content: str, output_path: str = None) -> str:
    prompt = f"""根据以下 refinement 文档，搜索相关论文的开源实现:

{ref_content}

## 执行步骤
1. 从上述文档提取需要搜索代码的方法名/论文名
2. 逐个用 web_search 搜索 GitHub 仓库
3. 用 clone_repo 拉取找到的仓库
4. 用 summarize_repo 分析代码结构"""
    if output_path:
        prompt += f"\n5. 将报告写入 {output_path}"
    return prompt


def make_code_ref_agent(allowed_dirs: list[str] = None) -> BaseAgent:
    """代码参考获取：搜索论文相关的开源仓库并生成摘要"""
    agent = BaseAgent(
        name="代码参考Agent",
        system_prompt=_CODE_REF_SYSTEM,
        tools=[],
        max_iterations=15,
        allowed_dirs=allowed_dirs,
    )
    agent.register_tool("web_search", web_search, WebSearchParams)
    agent.register_tool("read_file", read_file, ReadFileParams)
    agent.register_tool("write_file", write_file, WriteFileParams)
    agent.register_tool("list_directory", list_directory, ListDirectoryParams)
    agent.register_tool("clone_repo", clone_repo, CloneRepoParams)
    agent.register_tool("summarize_repo", summarize_repo, SummarizeRepoParams)
    agent.register_tool("list_repos", list_repos, ListReposParams)
    return agent
