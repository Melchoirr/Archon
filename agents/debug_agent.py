"""Debug Agent：运行测试、修复 bug、验证代码与设计文档一致"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import extract_topic_title
from tools.file_ops import read_file, write_file, list_directory
from tools.bash_exec import run_command
from tools.claude_code import claude_fix_error
from tools.venv_manager import setup_idea_venv
from shared.models.tool_params import (
    ReadFileParams, WriteFileParams, ListDirectoryParams,
    RunCommandParams, ClaudeFixErrorParams, SetupVenvParams,
)

SYSTEM_PROMPT_TEMPLATE = """你是 AI 代码调试专家。你的任务是运行测试、修复 bug、确保代码正确实现了设计方案。

研究课题: {topic_title}

## 调试流程

### 1. 理解代码结构
- 读取 src/structure.md 了解代码组织
- 读取 experiment_plan.md 了解预期行为

### 2. 运行测试
- 用 run_command 运行测试脚本
- 如果没有现成测试，先运行快速 sanity check（import、shape 验证等）

### 3. 修复 Bug
- 解析错误信息，定位问题
- 用 claude_fix_error 修复代码
- 重新运行测试验证修复

### 4. 验证实现完整性
- 对比 structure.md 检查所有模块是否实现
- 确认代码与 refinement/model_*.md 的设计一致

### 5. 产出报告
将调试结果写入 src/debug_report.md，包含：
- 测试结果汇总（pass/fail 计数）
- 发现并修复的 bug 列表
- 未解决的问题（如有）
- 实现完整性检查结果

## 环境管理
- 如果提供了 venv_path，使用 run_command 时设置 venv_path 参数
- 如遇依赖缺失，可调用 setup_venv 工具重装依赖

## 注意事项
- 使用 run_command 时确保在正确的环境中（优先使用 venv_path 参数）
- 每次修复后都要重新运行测试验证
- 最多进行 {max_debug_cycles} 轮修复循环
- 如果问题是设计层面的（而非实现 bug），在报告中明确指出"""


class DebugAgent(BaseAgent):
    def __init__(self, topic_dir: str, max_debug_cycles: int = 5,
                 allowed_dirs: list[str] = None):
        topic_title = extract_topic_title(topic_dir)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=topic_title,
            max_debug_cycles=max_debug_cycles,
        )

        super().__init__(
            name="调试Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=35,
            allowed_dirs=allowed_dirs,
        )
        self.register_tool("read_file", read_file, ReadFileParams)
        self.register_tool("write_file", write_file, WriteFileParams)
        self.register_tool("list_directory", list_directory, ListDirectoryParams)
        self.register_tool("run_command", run_command, RunCommandParams)
        self.register_tool("claude_fix_error", claude_fix_error, ClaudeFixErrorParams)
        self.register_tool("setup_venv", setup_idea_venv, SetupVenvParams)

    def build_prompt(self, *, idea_dir: str, src_dir: str,
                     structure_path: str, plan_path: str,
                     analysis_path: str = "",
                     debug_report_path: str = "",
                     venv_path: str = "") -> str:
        self._output_paths = [src_dir]
        existing = self._scan_existing_outputs()
        prompt = existing + f"""请对以下项目代码进行测试和调试。

## 路径
- idea 目录: {idea_dir}
- 源代码: {src_dir}
- 代码结构: {structure_path}
- 实验计划: {plan_path}

请:
1. 读取代码结构文档
2. 运行测试，检查代码是否正常工作
3. 修复发现的 bug
4. 验证代码与设计文档的一致性
5. 将调试报告写入 {src_dir}/debug_report.md
"""
        if venv_path:
            prompt += f"""
## 虚拟环境
实验 venv: {venv_path}
使用 run_command 时请设置 venv_path="{venv_path}"，确保命令在正确环境中运行。
如遇依赖缺失，可调用 setup_venv 工具（idea_src_dir="{src_dir}"）重装。
"""
        if analysis_path:
            prompt += f"""
## 实验分析报告
请先用 read_file 读取 `{analysis_path}`，了解实验分析发现的具体问题（异常指标、失败原因等），针对性地调试和修复。
"""
        if debug_report_path:
            prompt += f"""
## 上一轮调试报告
请先用 read_file 读取 `{debug_report_path}`，了解上一轮调试的结果和未解决的问题，在此基础上继续调试。
"""
        return prompt
