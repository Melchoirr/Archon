"""数据获取 Agent：根据文献推荐下载数据、探查格式、写描述卡片、更新配置"""
from .base_agent import BaseAgent
from tools.file_ops import (
    read_file, write_file, list_directory,
    READ_FILE_SCHEMA, WRITE_FILE_SCHEMA, LIST_DIRECTORY_SCHEMA,
)
from tools.bash_exec import run_command, RUN_COMMAND_SCHEMA
from tools.config_updater import update_config_section, UPDATE_CONFIG_SECTION_SCHEMA

_SYSTEM_PROMPT_BASE = """你是数据工程专家。你的任务是根据文献调研的推荐，获取和准备实验数据集。

请先阅读 {datasets_path}，了解推荐的数据集列表。
更新配置时，使用 update_config_section 并指定 config_path="{config_path}"。

对每个数据集:
1. 找到下载来源（GitHub/HuggingFace/官网/论文附件）
2. 用 run_command 下载到 shared/data/
3. 探查数据格式：文件类型、大小、结构
4. 写入数据集描述卡片到 knowledge/dataset_cards/<name>.md
5. 用 update_config_section 更新 config.yaml 的 datasets 部分

数据集卡片需包含:
- 基本信息（来源、格式、大小）
- 数据结构描述（字段/列/维度等）
- 推荐的使用方式
- 读取代码示例

config.yaml 的 datasets section 不预设字段结构，由你根据实际数据格式决定写入哪些字段。
至少包含 path 和 description。

注意:
- 下载失败时要报告错误，不要跳过
- 每个数据集都要验证数据可以正常读取
"""


class DataAgent(BaseAgent):
    def __init__(self, config_path: str = "config.yaml", datasets_path: str = None):
        actual_datasets_path = datasets_path or "knowledge/datasets.md"
        system_prompt = _SYSTEM_PROMPT_BASE.format(
            datasets_path=actual_datasets_path,
            config_path=config_path,
        )
        super().__init__(
            name="数据获取Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=25,
        )
        self.config_path = config_path
        self.register_tool("read_file", read_file, READ_FILE_SCHEMA)
        self.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
        self.register_tool("list_directory", list_directory, LIST_DIRECTORY_SCHEMA)
        self.register_tool("run_command", run_command, RUN_COMMAND_SCHEMA)
        self.register_tool("update_config_section", update_config_section, UPDATE_CONFIG_SECTION_SCHEMA)
