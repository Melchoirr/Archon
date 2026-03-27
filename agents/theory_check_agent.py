"""理论检查 Agent：对 refinement 产出的理论进行交叉验证"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import extract_topic_title
from tools.file_ops import read_file, write_file
from tools.web_search import web_search
from tools.openalex import search_papers, search_topics
from tools.paper_manager import read_paper_section
from tools.knowledge_index import check_local_knowledge
from shared.models.tool_params import (
    ReadFileParams, WriteFileParams,
    WebSearchParams, SearchTopicsParams, SearchPapersParams, ReadPaperSectionParams,
    CheckLocalKnowledgeParams,
)

SYSTEM_PROMPT_TEMPLATE = """你是 AI 科研理论审查专家。你的任务是对研究方案的理论基础进行严格的交叉验证。

研究课题: {topic_title}

## 审查流程

### 1. 提取关键声明
- 从 theory.md 中提取所有关键理论声明、假设和推导
- 识别每个声明的类型：公理性假设、定理推导、经验性假设、设计选择

### 2. 文献交叉验证
- 对每个关键声明，搜索 OpenAlex 和 web 寻找支持或反驳的证据
- 与 survey.md 中已有的文献交叉比对
- 记录支持论文和反驳论文

### 3. 逻辑一致性检查
- 检查推导链的逻辑完整性
- 识别隐含假设是否合理
- 验证数学推导的正确性

### 4. 产出报告
将审查结果写入 refinement/theory_review.md，包含：
- 每个关键声明的验证结果（支持/反驳/存疑）
- 发现的问题列表
- 支持和反驳的文献引用
- 修订建议（如有）

### 5. 创新性评估
- 与 survey 中最相似的 2-3 篇论文做详细对比
- 明确列出本方案的差异化贡献点
- 如果核心方法与已有工作高度相似，在报告中明确标注

### 6. 因果推演（为什么能 work）
- 从理论角度推演：本方案的核心创新如何通过 A→B→C 的因果链影响目标指标
- 识别因果链中的薄弱环节
- 评估推演的可信度（强因果 / 合理推测 / 缺乏依据）

## 输出质量要求

**每个声明都要有明确的验证结论和文献依据。**
- theory_review.md: ≥1500字
- 每个关键声明至少引用 1 篇支持/反驳文献
- 问题列表要具体，包含改进方向
- 创新性评估需列出与最相似论文的具体差异
- 因果推演需完整写出 A→B→C 链条"""


class TheoryCheckAgent(BaseAgent):
    def __init__(self, topic_dir: str, allowed_dirs: list[str] = None):
        topic_title = extract_topic_title(topic_dir)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=topic_title,
        )

        super().__init__(
            name="理论检查Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=15,
            allowed_dirs=allowed_dirs,
        )
        self.register_tool("read_file", read_file, ReadFileParams)
        self.register_tool("write_file", write_file, WriteFileParams)
        self.register_tool("search_topics", search_topics, SearchTopicsParams)
        self.register_tool("search_papers", search_papers, SearchPapersParams)
        self.register_tool("web_search", web_search, WebSearchParams)
        self.register_tool("read_paper_section", read_paper_section, ReadPaperSectionParams)
        self.register_tool("check_local_knowledge", check_local_knowledge, CheckLocalKnowledgeParams)

    def build_prompt(self, *, theory_path: str, survey_path: str,
                     proposal_path: str, output_path: str) -> str:
        self._output_paths = [output_path]
        existing = self._scan_existing_outputs()
        return existing + f"""请对以下研究方案的理论基础进行交叉验证。

## 输入文件
- 理论推导: {theory_path}
- 文献综述: {survey_path}
- 原始 Proposal: {proposal_path}

## 输出
将审查报告写入: {output_path}

请:
1. 读取上述文件
2. 提取 theory.md 中的关键声明
3. 搜索文献进行交叉验证
4. 检查逻辑一致性
5. 撰写审查报告
"""
