"""Idea 细化 Agent：理论推导 + 模块化结构设计 + 阶段性实验设计"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.file_ops import read_file, write_file
from tools.research_tree import read_tree, update_idea_phase
from tools.memory import query_memory
from tools.web_search import web_search
from tools.openalex import search_papers
from tools.paper_manager import read_paper_section
from shared.models.tool_params import (
    ReadFileParams, WriteFileParams, ReadTreeParams, UpdateIdeaPhaseParams,
    QueryMemoryParams, WebSearchParams, SearchPapersParams,
    ReadPaperSectionParams,
)

SYSTEM_PROMPT_TEMPLATE = """你是 AI 科研方案细化专家。你的任务是将一个研究 idea 展开为完整的技术方案。

研究课题: {topic_title}

## 输出三份文档

### 1. 理论推导 → refinement/theory.md
- 问题的数学形式化定义
- 核心创新点的理论推导
- 与现有方法的理论对比
- 收敛性/一致性等理论分析（如适用）
- 关联 survey 中的具体论文，引用其结论

### 2. 模型结构设计
- **模块化版本** → refinement/model_modular.md
  - 创新部分和沿用部分明确分开
  - 每个模块的输入/输出/职责
  - 模块间的接口定义
- **完整版本** → refinement/model_complete.md
  - 端到端的完整模型描述
  - 数据流图
  - 关键组件的计算/空间复杂度估算

### 3. 阶段性实验设计 → experiment_plan.md
- 每个实验步骤的名称和目标
- **预期结果**（具体数值范围，用于后续验证）
- 数值设置合理性检查
  - 不确定的参数设计梯度实验
  - 引用论文中的典型值作为参考
- 步骤间的依赖关系

实验计划格式:
```
## Step 1: Quick Test (S01_quick_test)
- 目标: 验证代码正确性和基本效果
- 预期结果:
  - 核心指标: < X.XX（参考 baseline 结果给出合理预期）
  - 资源消耗: 时间/内存/计算量的预期
- 成功标准: 明确的定量判定依据

## Step 2: Full Test (S02_full_test)
...
```

## 可用工具

| 工具 | 用途 |
|------|------|
| read_tree | 开始前读取研究树，了解 idea 当前阶段状态 |
| read_file | 读取 proposal.md、design.md、survey 文档等输入材料 |
| write_file | 将 theory.md、model_modular.md、model_complete.md、experiment_plan.md 写入目录 |
| query_memory | 查询历史经验，参考类似 idea 的细化经验 |
| search_papers | 搜索论文获取理论依据、典型超参数、baseline 结果 |
| web_search | 搜索技术实现细节、数学推导参考 |
| read_paper_section | 按章节阅读已下载论文，获取具体方法细节和实验设置 |
| update_idea_phase | 完成后更新 refinement 阶段状态 |

## 工作流

1. read_tree() → 确认目标 idea 状态
2. read_file() → 读取 proposal.md 和 design.md 获取方案概要
3. query_memory() → 查询相关历史经验
4. search_papers() + read_paper_section() → 获取理论依据和实验参考值
5. write_file() → 依次写入 theory.md → model_modular.md → model_complete.md → experiment_plan.md
6. update_idea_phase(idea_id=..., phase="refinement", status="completed")

## 关键约束
- 明确区分 **创新部分** vs **沿用已知优秀方法的部分**
- 不确定的设计决策要标注，并设计对应的消融实验
- 每个预期结果要有依据（来自论文或理论推导）

## 输出质量要求

**不要简化方案，不要用一两句话带过关键设计。** 每份文档有最低字数要求：
- theory.md: ≥2000字 — 公式推导必须完整，每个公式需解释变量含义和设计动机
- model_modular.md: ≥1500字 — 每个模块需写明输入维度、输出维度、内部计算步骤
- model_complete.md: ≥3000字 — 端到端描述，含完整数据流图（文字描述）和复杂度分析
- experiment_plan.md: ≥1000字 — 每个 Step 需写明预期数值范围及依据来源

遇到实现困难时，寻找解决办法而非回退到更简单的版本。"""


class RefinementAgent(BaseAgent):
    def __init__(self, config_path="config.yaml", allowed_dirs: list[str] = None):
        tc = load_topic_config(config_path)
        # 构建可选的数据集和指标信息
        extra_context = ""
        if tc.dataset_names:
            extra_context += f"\n数据集: {tc.dataset_names}"
        if tc.metric_names:
            extra_context += f"\n评估指标: {tc.metric_names}"

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=tc.topic.title,
        )
        if extra_context:
            system_prompt = system_prompt.replace(
                "研究课题: {topic_title}".format(topic_title=tc.topic.title),
                f"研究课题: {tc.topic.title}{extra_context}",
            )

        super().__init__(
            name="方案细化Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=20,
            allowed_dirs=allowed_dirs,
        )
        self.register_tool("read_file", read_file, ReadFileParams)
        self.register_tool("write_file", write_file, WriteFileParams)
        self.register_tool("read_tree", read_tree, ReadTreeParams)
        self.register_tool("update_idea_phase", update_idea_phase, UpdateIdeaPhaseParams)
        self.register_tool("query_memory", query_memory, QueryMemoryParams)
        self.register_tool("web_search", web_search, WebSearchParams)
        self.register_tool("search_papers", search_papers, SearchPapersParams)
        self.register_tool("read_paper_section", read_paper_section, ReadPaperSectionParams)

    def build_prompt(self, *, topic_title: str, dataset_names: str = "",
                     metric_names: str = "", topic_dir: str = "",
                     idea_dir: str, proposal: str, context: str = "",
                     past_exp: str = "", refinement_dir: str,
                     theory_review_path: str = "") -> str:
        prompt = f"""请将以下 idea 展开为完整技术方案。

## 研究课题
{topic_title}

## 可用数据集
{dataset_names}

## 评估指标
{metric_names}

## 路径信息
- topic_dir: {topic_dir}
- idea_dir: {idea_dir}

## Proposal
{proposal}

{context}

## 历史经验
{past_exp}

请输出:
1. {refinement_dir}/theory.md - 理论推导
2. {refinement_dir}/model_modular.md - 模块化结构设计
3. {refinement_dir}/model_complete.md - 完整结构设计
4. {idea_dir}/experiment_plan.md - 阶段性实验计划（含预期结果）

注意: 使用 update_idea_phase 更新阶段状态时传入 idea_id、phase 名和 status。"""
        if theory_review_path:
            prompt += f"""

## 迭代改进（非首次 refine）
这是第 N 轮 refine。refinement/ 下已有上一轮产物，theory_review.md 是评审意见。

**必须按以下步骤操作**：
1. 用 read_file 读取 `{theory_review_path}`，了解审查发现的问题
2. 用 read_file 读取 `{refinement_dir}/theory.md`、`{refinement_dir}/model_modular.md`、`{refinement_dir}/model_complete.md`，了解上一轮方案
3. **在上一轮基础上针对性改进**，不要从零重写。保留没有问题的部分，只修改审查指出的问题
4. 写入同路径文件覆盖"""
        return prompt
