"""实验执行 Agent：MiniMax 拆解任务，claude -p 逐模块编写代码（增强版：结构文档、代码拆分、参考代码）"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.file_ops import read_file, write_file, list_directory, READ_FILE_SCHEMA, WRITE_FILE_SCHEMA, LIST_DIRECTORY_SCHEMA
from tools.bash_exec import run_command, RUN_COMMAND_SCHEMA
from tools.research_tree import read_tree, update_tree, READ_TREE_SCHEMA, UPDATE_TREE_SCHEMA
from tools.memory import query_memory, add_experience, QUERY_MEMORY_SCHEMA, ADD_EXPERIENCE_SCHEMA
from tools.claude_code import (
    claude_write_module, claude_fix_error, claude_review,
    CLAUDE_WRITE_MODULE_SCHEMA, CLAUDE_FIX_ERROR_SCHEMA, CLAUDE_REVIEW_SCHEMA,
)
from tools.github_repo import list_repos, LIST_REPOS_SCHEMA


SYSTEM_PROMPT_TEMPLATE = """你是 AI 实验执行专家。你的职责是**拆解编码任务并逐模块调度 Claude 编写代码**。

## 研究课题
{topic_title}

## 核心原则

你是项目经理，Claude (-p) 是程序员。你负责:
- 读取 refinement/*.md 和 experiment_plan.md，理解要实现什么
- 将实现拆解为独立的功能模块（每个模块一个文件）
- 为每个模块编写清晰的任务描述，交给 claude_write_module
- 测试代码，发现错误后用 claude_fix_error 修复
- 用 claude_review 审查关键代码

## 代码结构

先生成 src/structure.md 记录端到端结构。
代码组织由研究内容决定，典型结构可参考:
- src/model/ - 核心方法实现
- src/experiment/ - 实验相关代码（数据处理、运行、评估）

根据 refinement/*.md 和 experiment_plan.md 确定具体需要哪些模块。
每写完一个模块更新 structure.md 的细分结构。

## 参考代码

用 list_repos 查看已 clone 的参考仓库，在 claude_write_module 的 task 中引用相关代码。

## 工具分工（严格遵守）

### 你直接使用的工具:
- **read_file**: 读取 refinement/*.md、experiment_plan.md、查看结果
- **list_directory**: 查看目录结构
- **run_command**: 运行测试和实验脚本
- **write_file**: 只用于 structure.md、配置文件或少量修改
- **query_memory / add_experience**: 查询和记录经验
- **list_repos**: 查看可参考的代码仓库

### 交给 Claude 的工具:
- **claude_write_module**: 每次写一个模块。在 task 中详细描述:
  - 模块的功能和职责
  - 输入输出的数据格式（tensor shape、数据类型）
  - 与其他模块的接口（import 什么、暴露什么函数/类）
  - 关键的技术细节（算法、公式、超参数）
  - 参考已有的代码（如 clone 的仓库中的实现）
- **claude_fix_error**: 代码出错时使用。把 run_command 的完整报错传入。
- **claude_review**: 关键模块写完后审查。

## 标准流程

1. **理解方案**: read_file 读取 refinement/*.md 和 experiment_plan.md
2. **生成结构文档**: write_file 生成 src/structure.md
3. **查看参考代码**: list_repos 查看可参考的仓库
4. **逐模块编写**: 按依赖顺序，先核心方法后实验代码，每写一个模块更新 structure.md
5. **审查关键代码**: 对 model.py 和 loss.py 做 claude_review
6. **Quick test**: run_command 执行快速测试
7. **修复错误**: 出错则用 claude_fix_error，最多重试 3 次
8. **记录经验**: 将关键发现记录到 memory

## 注意事项
- 使用 run_command 时确保在正确的 conda 环境中
- 每次 claude_write_module 只写一个文件
- task 描述要具体，写清楚模型结构、层数、维度等
- 如果 refinement 中有数学公式，在 task 中原样引用

不要简化或妥协方案，除非 idea 本身被证明有根本性错误。遇到实现困难时，寻找解决办法而非回退到更简单的版本。"""


class ExperimentAgent(BaseAgent):
    def __init__(self, config_path="config.yaml"):
        tc = load_topic_config(config_path)
        # 构建可选的数据集和指标信息
        extra_context = ""
        if tc["dataset_names"]:
            extra_context += f"\n\n## 可用数据集\n{tc['dataset_names']}"
        if tc["metric_names"]:
            extra_context += f"\n\n## 评估指标\n{tc['metric_names']}"

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=tc["topic_title"],
        )
        if extra_context:
            system_prompt = system_prompt.replace(
                "## 核心原则",
                f"{extra_context}\n\n## 核心原则",
            )

        super().__init__(
            name="实验执行Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=30,
        )
        self.register_tool("read_file", read_file, READ_FILE_SCHEMA)
        self.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
        self.register_tool("list_directory", list_directory, LIST_DIRECTORY_SCHEMA)
        self.register_tool("run_command", run_command, RUN_COMMAND_SCHEMA)
        self.register_tool("read_tree", read_tree, READ_TREE_SCHEMA)
        self.register_tool("update_tree", update_tree, UPDATE_TREE_SCHEMA)
        self.register_tool("query_memory", query_memory, QUERY_MEMORY_SCHEMA)
        self.register_tool("add_experience", add_experience, ADD_EXPERIENCE_SCHEMA)
        self.register_tool("claude_write_module", claude_write_module, CLAUDE_WRITE_MODULE_SCHEMA)
        self.register_tool("claude_fix_error", claude_fix_error, CLAUDE_FIX_ERROR_SCHEMA)
        self.register_tool("claude_review", claude_review, CLAUDE_REVIEW_SCHEMA)
        self.register_tool("list_repos", list_repos, LIST_REPOS_SCHEMA)
