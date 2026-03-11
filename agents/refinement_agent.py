"""Idea 细化 Agent：理论推导 + 模块化结构设计 + 阶段性实验设计"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.file_ops import read_file, write_file, READ_FILE_SCHEMA, WRITE_FILE_SCHEMA
from tools.research_tree import read_tree, update_tree, READ_TREE_SCHEMA, UPDATE_TREE_SCHEMA
from tools.memory import query_memory, QUERY_MEMORY_SCHEMA
from tools.web_search import web_search, WEB_SEARCH_SCHEMA
from tools.semantic_scholar import search_papers, SEARCH_PAPERS_SCHEMA
from tools.paper_manager import read_paper_section, READ_PAPER_SECTION_SCHEMA

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

## 关键约束
- 明确区分 **创新部分** vs **沿用已知优秀方法的部分**
- 不确定的设计决策要标注，并设计对应的消融实验
- 每个预期结果要有依据（来自论文或理论推导）

不要简化或妥协方案，除非 idea 本身被证明有根本性错误。遇到实现困难时，寻找解决办法而非回退到更简单的版本。"""


class RefinementAgent(BaseAgent):
    def __init__(self, config_path="config.yaml"):
        tc = load_topic_config(config_path)
        # 构建可选的数据集和指标信息
        extra_context = ""
        if tc["dataset_names"]:
            extra_context += f"\n数据集: {tc['dataset_names']}"
        if tc["metric_names"]:
            extra_context += f"\n评估指标: {tc['metric_names']}"

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=tc["topic_title"],
        )
        if extra_context:
            system_prompt = system_prompt.replace(
                "研究课题: {topic_title}".format(topic_title=tc["topic_title"]),
                f"研究课题: {tc['topic_title']}{extra_context}",
            )

        super().__init__(
            name="方案细化Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=25,
        )
        self.register_tool("read_file", read_file, READ_FILE_SCHEMA)
        self.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
        self.register_tool("read_tree", read_tree, READ_TREE_SCHEMA)
        self.register_tool("update_tree", update_tree, UPDATE_TREE_SCHEMA)
        self.register_tool("query_memory", query_memory, QUERY_MEMORY_SCHEMA)
        self.register_tool("web_search", web_search, WEB_SEARCH_SCHEMA)
        self.register_tool("search_papers", search_papers, SEARCH_PAPERS_SCHEMA)
        self.register_tool("read_paper_section", read_paper_section, READ_PAPER_SECTION_SCHEMA)
