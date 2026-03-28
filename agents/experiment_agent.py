"""实验执行 Agent：MiniMax 拆解任务，claude -p 逐模块编写代码（增强版：结构文档、代码拆分、参考代码）"""
import os

from .base_agent import BaseAgent
from shared.utils.config_helpers import extract_topic_title
from tools.file_ops import read_file, write_file, list_directory
from tools.bash_exec import run_command
from tools.idea_registry import read_research_status
from tools.memory import query_memory, add_experience
from tools.claude_code import (
    claude_write_module, claude_fix_error, claude_review,
)
from tools.github_repo import list_repos
from tools.venv_manager import setup_idea_venv
from shared.models.tool_params import (
    ReadFileParams, WriteFileParams, ListDirectoryParams,
    RunCommandParams, ReadResearchStatusParams,
    QueryMemoryParams, AddExperienceParams,
    ClaudeWriteModuleParams, ClaudeFixErrorParams, ClaudeReviewParams,
    ListReposParams, SetupVenvParams,
)


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

## 实验基础设施（MANDATORY）

所有实验代码必须遵循 shared/templates/experiment_infrastructure.md 中的规范。
关键要求：
1. YAML 配置系统 — 所有超参数通过 configs/default.yaml 管理，stage/ablation 通过覆盖文件
2. 统一入口 — run.py 支持 --stage / --ablation / --override / --tag
3. 配置加载 — Pydantic 验证 + 层叠合并（default <- stage <- ablation <- CLI）
4. Trainer — tqdm 进度条 + 时间戳日志 + JSON 历史 + early stopping
5. Evaluator — 独立评估器，采样生成 + 全指标
6. 消融支持 — 模型 enable_* 开关 + configs/ablations/*.yaml
7. Bash 脚本 — scripts/run_stage.sh 等批量运行脚本
8. 可视化 — visualize/ 下 5 个标准模块（training_curves, trajectory_plots, variance_analysis, ablation_table, sensitivity_heatmap）

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

## 依赖管理
- 编写代码模块时，同时维护 src/requirements.txt
- 每当引入新的第三方库，立即更新 requirements.txt
- requirements.txt 放在 src/ 目录下

## 注意事项
- 使用 run_command 时确保在正确的环境中（优先使用 venv_path 参数）
- 每次 claude_write_module 只写一个文件
- task 描述要具体，写清楚模型结构、层数、维度等
- 如果 refinement 中有数学公式，在 task 中原样引用

不要简化或妥协方案，除非 idea 本身被证明有根本性错误。遇到实现困难时，寻找解决办法而非回退到更简单的版本。"""


class ExperimentAgent(BaseAgent):
    def __init__(self, topic_dir: str, allowed_dirs: list[str] = None):
        topic_title = extract_topic_title(topic_dir)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=topic_title,
        )

        super().__init__(
            name="实验执行Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=40,
            allowed_dirs=allowed_dirs,
        )
        self.register_tool("read_file", read_file, ReadFileParams)
        self.register_tool("write_file", write_file, WriteFileParams)
        self.register_tool("list_directory", list_directory, ListDirectoryParams)
        self.register_tool("run_command", run_command, RunCommandParams)
        self.register_tool("read_research_status", read_research_status, ReadResearchStatusParams)
        self.register_tool("query_memory", query_memory, QueryMemoryParams)
        self.register_tool("add_experience", add_experience, AddExperienceParams)
        self.register_tool("claude_write_module", claude_write_module, ClaudeWriteModuleParams)
        self.register_tool("claude_fix_error", claude_fix_error, ClaudeFixErrorParams)
        self.register_tool("claude_review", claude_review, ClaudeReviewParams)
        self.register_tool("list_repos", list_repos, ListReposParams)
        self.register_tool("setup_venv", setup_idea_venv, SetupVenvParams)

    def _load_infra_template(self) -> str:
        """读取实验基础设施规范模板"""
        tpl_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "shared", "templates", "experiment_infrastructure.md",
        )
        if os.path.exists(tpl_path):
            with open(tpl_path, "r", encoding="utf-8") as f:
                return f.read()
        return ""

    def build_code_prompt(self, *, design_content: str, plan: str,
                          context: str = "", past_exp: str = "",
                          idea_dir: str,
                          debug_report_path: str = "") -> str:
        infra_template = self._load_infra_template()
        infra_section = ""
        if infra_template:
            infra_section = f"""

## 实验基础设施规范（MANDATORY — 必须严格遵循）
{infra_template}
"""
        prompt = f"""根据设计方案和实验计划，实现代码。

## 技术方案
{design_content}

## 实验计划
{plan}

{context}

## 历史经验
{past_exp}
{infra_section}
代码放在 {idea_dir}/src/（model/ 和 experiment/ 子目录），
先生成 {idea_dir}/src/structure.md 记录代码结构。
同时生成 {idea_dir}/src/requirements.txt，列出所有第三方依赖（每行一个包名）。"""
        if debug_report_path:
            prompt += f"""

## 调试报告（代码重写原因）
请先用 read_file 读取 `{debug_report_path}`，了解上一轮调试发现的问题。重写代码时需针对性地解决这些问题。"""
        return prompt

    def build_experiment_prompt(self, *, step_id: str, version: int,
                                plan: str, structure: str,
                                prev_analysis: str = "",
                                results_dir: str,
                                venv_path: str = "") -> str:
        self._output_paths = [results_dir]
        existing = self._scan_existing_outputs()
        prompt = existing + f"""运行实验步骤 {step_id}，版本 V{version}。

## 实验计划
{plan}

## 代码结构
{structure}
"""
        if prev_analysis:
            prompt += f"""
## 前版本 (V{version-1}) 分析结果
{prev_analysis}

请根据上述分析结果，微调实验设置后重新运行。
将配置差异记录到 config_diff.md。
"""

        prompt += f"""
结果存储到 {results_dir}/{step_id}_*/V{version}/
包含: metrics.json, plots/, log.txt"""
        if version > 1:
            prompt += ", config_diff.md"

        if venv_path:
            prompt += f"""

## 虚拟环境
实验 venv: {venv_path}
使用 run_command 时请设置 venv_path="{venv_path}"，确保命令在正确环境中运行。
如需重装依赖，可调用 setup_venv 工具。"""

        return prompt
