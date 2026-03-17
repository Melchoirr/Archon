"""数据获取与 EDA Agent：根据 eda_guide.md 下载纯数据、执行 EDA、生成报告"""
from .base_agent import BaseAgent
from tools.file_ops import (
    read_file, write_file, list_directory,
)
from tools.bash_exec import run_command
from tools.web_search import web_search
from tools.vlm_analysis import analyze_image, analyze_plots_dir
from tools.config_updater import update_config_section
from tools.venv_manager import setup_idea_venv
from shared.models.tool_params import (
    ReadFileParams, WriteFileParams, ListDirectoryParams,
    RunCommandParams, WebSearchParams,
    AnalyzeImageParams, AnalyzePlotsParams,
    UpdateConfigSectionParams,
    SetupVenvParams,
)

_SYSTEM_PROMPT = """你是数据工程与 EDA 执行专家。严格按 {eda_guide_path} 中的规划执行。

## 工具说明

| 工具 | 用途 | 返回格式 |
|------|------|---------|
| read_file(path) | 读文件 | 文件内容字符串 |
| write_file(path, content) | 写文件 | "OK" |
| run_command(command, timeout) | 执行 shell | "stdout:...\\nstderr:...\\nreturncode: 0" |
| web_search(query) | 搜索网页 | JSON 数组 |
| analyze_plots_dir(plots_dir, context) | VLM 分析目录下所有图片 | 每张图的文字分析 |
| update_config_section(section, data) | 更新 config.yaml | 成功消息 |
| setup_venv(idea_src_dir) | 创建/更新 venv 并安装 requirements.txt | 成功/失败消息 |

## 关键命令格式
- 下载: run_command(command='wget -q -O {data_dir}/文件名 "URL"')
- 解压: run_command(command='unzip -o {data_dir}/xx.zip -d {data_dir}/')
- 执行 Python: run_command(command='python 脚本路径', venv_path='{venv_path}')
- 判断成功: 返回中 "returncode: 0" 表示成功，其他为失败

## 依赖管理
- 如果脚本需要额外依赖（如 pyarrow, h5py, netCDF4 等），先 write_file 写 {eda_dir}/requirements.txt
- 然后调 setup_venv(idea_src_dir='{eda_dir}') 安装依赖
- 遇到 ImportError/ModuleNotFoundError 时，把缺失包追加到 requirements.txt，再调 setup_venv

## 执行流程

**Phase 1: 下载数据**
1. 调用 read_file(path='{eda_guide_path}') 读取 EDA 指南
2. 对每个数据集:
   a. run_command 执行 wget 下载到 {data_dir}/
   b. run_command(command='ls -lh {data_dir}/文件名') 验证文件存在
   c. returncode≠0 → web_search(query="数据集名 download alternative") 找替代链接，重试一次
   d. zip/gz 文件 → run_command 解压
3. 禁止 git clone

**Phase 2: 编写并执行 EDA**
4. 对每个已下载的数据集，用 write_file 写 Python 脚本到 {eda_scripts_dir}/explore_数据集名.py
5. 脚本结构要求:
   - import 在顶部; 用 try/except 包裹; 图表存到 {eda_plots_dir}/数据集名_图表类型.png
   - 统计结果 print 到 stdout; 分析方法按 eda_guide.md 指定
6. run_command(command='python 脚本路径', venv_path='{venv_path}') 执行脚本
7. returncode≠0 → 读 stderr，修改脚本后重试一次

**Phase 3: VLM 分析**
8. 调用 analyze_plots_dir(plots_dir='{eda_plots_dir}', context='课题上下文')

**Phase 4: 生成报告**
9. write_file 更新 {datasets_path}（补充实际路径、格式、规模）
10. write_file 写入 {eda_report_path}
11. update_config_section(section='datasets', data='YAML内容')

## 错误处理
- 一个数据集失败不影响其他 → 继续处理下一个
- 全部下载失败 → 仍写报告，注明失败原因
- 脚本执行失败 → 最多重试 1 次，仍失败则记录错误到报告

## 输出质量要求

**EDA 报告是后续所有 agent 的数据基础，必须详尽。**
- eda_report.md: ≥2000字
  - 每个数据集的分析 ≥400字，含：数据规模、缺失值统计、分布特征、异常值分析
  - 必须包含 VLM 对图表的分析结论（不要只贴图不分析）
  - 跨数据集对比分析: 共性/差异、对方法选择的启示
- datasets.md 更新: 补充实际数据路径、文件格式、行列数等硬事实
- EDA 脚本: 每个脚本含注释说明分析目的，print 输出含标签（如 "Missing values:"）便于解析
"""


class DataAgent(BaseAgent):
    def __init__(self, *, config_path: str, eda_guide_path: str,
                 data_dir: str, eda_dir: str,
                 eda_plots_dir: str, eda_scripts_dir: str,
                 eda_report_path: str, datasets_path: str,
                 venv_path: str = "",
                 allowed_dirs: list[str] = None):
        system_prompt = _SYSTEM_PROMPT.format(
            eda_guide_path=eda_guide_path,
            config_path=config_path,
            data_dir=data_dir,
            eda_dir=eda_dir,
            eda_scripts_dir=eda_scripts_dir,
            eda_plots_dir=eda_plots_dir,
            eda_report_path=eda_report_path,
            datasets_path=datasets_path,
            venv_path=venv_path,
        )
        super().__init__(
            name="数据EDA-Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=35,
            allowed_dirs=allowed_dirs,
        )
        self.config_path = config_path
        self.eda_guide_path = eda_guide_path
        self.data_dir = data_dir
        self.eda_dir = eda_dir
        self.eda_plots_dir = eda_plots_dir
        self.eda_scripts_dir = eda_scripts_dir
        self.eda_report_path = eda_report_path
        self.datasets_path = datasets_path
        self.venv_path = venv_path

        self.register_tool("read_file", read_file, ReadFileParams)
        self.register_tool("write_file", write_file, WriteFileParams)
        self.register_tool("list_directory", list_directory, ListDirectoryParams)
        self.register_tool("run_command", run_command, RunCommandParams)
        self.register_tool("web_search", web_search, WebSearchParams)
        self.register_tool("analyze_image", analyze_image, AnalyzeImageParams)
        self.register_tool("analyze_plots_dir", analyze_plots_dir, AnalyzePlotsParams)
        self.register_tool("update_config_section", update_config_section, UpdateConfigSectionParams)
        self.register_tool("setup_venv", setup_idea_venv, SetupVenvParams)

    def build_prompt(self) -> str:
        prompt = (
            f"请执行 EDA 流水线。\n\n"
            f"## 关键路径\n"
            f"- EDA 指南: {self.eda_guide_path}\n"
            f"- 数据目录: {self.data_dir}\n"
            f"- 脚本目录: {self.eda_scripts_dir}\n"
            f"- 图表目录: {self.eda_plots_dir}\n"
            f"- EDA 报告: {self.eda_report_path}\n"
            f"- 数据集描述: {self.datasets_path}\n"
            f"- 配置文件: {self.config_path}\n\n"
            f"## 执行步骤\n"
            f"1. 调用 read_file(path='{self.eda_guide_path}') 读取规划\n"
            f"2. 按规划下载每个数据集到 {self.data_dir}/\n"
            f"3. 为每个数据集编写 EDA 脚本到 {self.eda_scripts_dir}/\n"
            f"4. 执行脚本，图表保存到 {self.eda_plots_dir}/\n"
            f"5. 调用 analyze_plots_dir 分析图表\n"
            f"6. 写入 EDA 报告到 {self.eda_report_path}\n"
            f"7. 更新 {self.datasets_path} 和 config.yaml"
        )
        if self.venv_path:
            prompt += (
                f"\n\n## 虚拟环境\n"
                f"venv: {self.venv_path}\n"
                f"使用 run_command 时设置 venv_path=\"{self.venv_path}\"\n"
                f"需要额外依赖时先写 requirements.txt 到 {self.eda_dir}/，再调 setup_venv(idea_src_dir='{self.eda_dir}')"
            )
        return prompt
