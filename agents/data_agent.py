"""数据获取与 EDA Agent：根据 eda_guide.md 下载纯数据、执行 EDA、生成报告"""
from .base_agent import BaseAgent
from tools.file_ops import (
    read_file, write_file, list_directory,
)
from tools.bash_exec import run_command
from tools.web_search import web_search
from tools.vlm_analysis import analyze_image, analyze_plots_dir
from tools.venv_manager import setup_idea_venv
from tools.knowledge_index import check_local_knowledge, register_dataset
from shared.models.tool_params import (
    ReadFileParams, WriteFileParams, ListDirectoryParams,
    RunCommandParams, WebSearchParams,
    AnalyzeImageParams, AnalyzePlotsParams,
    SetupVenvParams,
    CheckLocalKnowledgeParams, RegisterDatasetParams,
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
| setup_venv(idea_src_dir) | 创建/更新 venv 并安装 requirements.txt | 成功/失败消息 |
| check_local_knowledge(query, resource_type) | 检查本地是否已有资源 | 匹配结果描述 |
| register_dataset(...) | 注册数据集（含生成 dataset card） | 确认消息 |

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

**Phase 0: 预检与策略判断**
0. 调用 read_file(path='{eda_guide_path}') 读取 EDA 指南
1. 对每个数据集，判断获取策略:
   a. check_local_knowledge(query=数据集名, resource_type="dataset") 检查是否已注册/下载
   b. 已存在且文件完好 → 跳过下载，直接进入 Phase 2
   c. 根据以下规则决定 **下载** 还是 **仅记录**:
      - **下载**（access_mode="downloaded"）: 有直链、文件小（通常 <500MB）、格式标准（csv/parquet/zip）
      - **仅记录**（access_mode="card_only"）: 以下任一情况
        · 数据集过大（>1GB 或描述中提到 TB 级）
        · 需要注册/申请才能下载（如 PhysioNet、MIMIC）
        · 需要 API 访问（如 Weather API、实时数据源）
        · 仅提供代码生成方式（需运行脚本生成数据）
        · 是商业数据集或有使用限制
        · 找不到可用的直链下载地址

**Phase 1: 获取数据**
2. 对每个**需要下载**的数据集:
   a. run_command 执行 wget 下载到 {data_dir}/
   b. run_command(command='ls -lh {data_dir}/文件名') 验证文件存在
   c. returncode≠0 → web_search(query="数据集名 download alternative") 找替代链接，重试一次
   d. zip/gz 文件 → run_command 解压
   e. 调用 register_dataset(name=数据集名, url=下载URL, local_path=本地路径, format=格式, access_mode="downloaded", size_info="实际文件大小", description="数据集描述")
3. 对每个**仅记录**的数据集:
   a. 调用 register_dataset(name=数据集名, url=官方页面, access_mode="card_only", size_info="规模描述", description="数据集描述", access_note="说明如何获取: 需要去哪里注册/申请/下载/运行什么命令")
4. **所有数据集都必须调用 register_dataset**，无论是否下载
5. 禁止 git clone

**Phase 2: 编写并执行 EDA**
6. 对每个**已下载**的数据集，用 write_file 写 Python 脚本到 {eda_scripts_dir}/explore_数据集名.py
7. 脚本结构要求:
   - import 在顶部; 用 try/except 包裹; 图表存到 {eda_plots_dir}/数据集名_图表类型.png
   - 统计结果 print 到 stdout; 分析方法按 eda_guide.md 指定
8. run_command(command='python 脚本路径', venv_path='{venv_path}') 执行脚本
9. returncode≠0 → 读 stderr，修改脚本后重试一次
（仅记录的数据集跳过 EDA，但在报告中说明其特点和预期用途）

**Phase 3: VLM 分析**
10. 调用 analyze_plots_dir(plots_dir='{eda_plots_dir}', context='课题上下文')

**Phase 4: 生成报告**
11. 先 read_file(path='{datasets_path}') 读取已有内容，在其基础上**追加**实际数据路径、文件格式、行列数等信息（不要覆盖已有的论文使用情况描述，只补充硬事实）
12. write_file 写入 {eda_report_path}
    - 已下载数据集: 完整 EDA 分析
    - 仅记录数据集: 写明获取方式、预期特征、在实验中的使用建议

## 错误处理
- 一个数据集失败不影响其他 → 继续处理下一个
- 下载失败时：如果重试也失败，将该数据集改为 card_only 模式注册，注明失败原因
- 全部下载失败 → 仍写报告，注明失败原因
- 脚本执行失败 → 最多重试 1 次，仍失败则记录错误到报告

## 输出质量要求

**EDA 报告是后续所有 agent 的数据基础，必须详尽。**
- eda_report.md: ≥2000字
  - 每个已下载数据集的分析 ≥400字，含：数据规模、缺失值统计、分布特征、异常值分析
  - 每个仅记录数据集 ≥150字，含：数据集特点、预期特征、获取方式、在实验中的使用建议
  - 必须包含 VLM 对图表的分析结论（不要只贴图不分析）
  - 跨数据集对比分析: 共性/差异、对方法选择的启示
- datasets.md 更新: 补充实际数据路径、文件格式、行列数等硬事实
- Dataset cards: 所有数据集都自动生成到 {dataset_cards_dir}/（由 register_dataset 完成）
- EDA 脚本: 每个脚本含注释说明分析目的，print 输出含标签（如 "Missing values:"）便于解析
"""


class DataAgent(BaseAgent):
    def __init__(self, *, eda_guide_path: str,
                 data_dir: str, eda_dir: str,
                 eda_plots_dir: str, eda_scripts_dir: str,
                 eda_report_path: str, datasets_path: str,
                 dataset_cards_dir: str = "",
                 venv_path: str = "",
                 allowed_dirs: list[str] = None):
        system_prompt = _SYSTEM_PROMPT.format(
            eda_guide_path=eda_guide_path,
            data_dir=data_dir,
            eda_dir=eda_dir,
            eda_scripts_dir=eda_scripts_dir,
            eda_plots_dir=eda_plots_dir,
            eda_report_path=eda_report_path,
            datasets_path=datasets_path,
            dataset_cards_dir=dataset_cards_dir,
            venv_path=venv_path,
        )
        super().__init__(
            name="数据EDA-Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=35,
            allowed_dirs=allowed_dirs,
        )
        self.eda_guide_path = eda_guide_path
        self.data_dir = data_dir
        self.eda_dir = eda_dir
        self.eda_plots_dir = eda_plots_dir
        self.eda_scripts_dir = eda_scripts_dir
        self.eda_report_path = eda_report_path
        self.datasets_path = datasets_path
        self.dataset_cards_dir = dataset_cards_dir
        self.venv_path = venv_path

        self.register_tool("read_file", read_file, ReadFileParams)
        self.register_tool("write_file", write_file, WriteFileParams)
        self.register_tool("list_directory", list_directory, ListDirectoryParams)
        self.register_tool("run_command", run_command, RunCommandParams)
        self.register_tool("web_search", web_search, WebSearchParams)
        self.register_tool("analyze_image", analyze_image, AnalyzeImageParams)
        self.register_tool("analyze_plots_dir", analyze_plots_dir, AnalyzePlotsParams)
        self.register_tool("setup_venv", setup_idea_venv, SetupVenvParams)
        self.register_tool("check_local_knowledge", check_local_knowledge, CheckLocalKnowledgeParams)
        self.register_tool("register_dataset", register_dataset, RegisterDatasetParams)

        self._output_paths = [
            eda_report_path, datasets_path, data_dir,
            eda_scripts_dir, eda_plots_dir,
        ]
        if dataset_cards_dir:
            self._output_paths.append(dataset_cards_dir)

    def build_prompt(self) -> str:
        existing = self._scan_existing_outputs()
        prompt = existing + (
            f"请执行 EDA 流水线。\n\n"
            f"## 关键路径\n"
            f"- EDA 指南: {self.eda_guide_path}\n"
            f"- 数据目录: {self.data_dir}\n"
            f"- 脚本目录: {self.eda_scripts_dir}\n"
            f"- 图表目录: {self.eda_plots_dir}\n"
            f"- EDA 报告: {self.eda_report_path}\n"
            f"- 数据集描述: {self.datasets_path}\n"
            f"- Dataset Cards: {self.dataset_cards_dir}\n"
            f"\n"
            f"## 执行步骤\n"
            f"1. 调用 read_file(path='{self.eda_guide_path}') 读取规划\n"
            f"2. 对每个数据集判断获取策略（下载 vs 仅记录）\n"
            f"3. 下载可下载的数据集到 {self.data_dir}/\n"
            f"4. 所有数据集调用 register_dataset 注册（自动生成 dataset card）\n"
            f"5. 为已下载数据集编写 EDA 脚本到 {self.eda_scripts_dir}/\n"
            f"6. 执行脚本，图表保存到 {self.eda_plots_dir}/\n"
            f"7. 调用 analyze_plots_dir 分析图表\n"
            f"8. 写入 EDA 报告到 {self.eda_report_path}\n"
            f"9. 更新 {self.datasets_path}"
        )
        if self.venv_path:
            prompt += (
                f"\n\n## 虚拟环境\n"
                f"venv: {self.venv_path}\n"
                f"使用 run_command 时设置 venv_path=\"{self.venv_path}\"\n"
                f"需要额外依赖时先写 requirements.txt 到 {self.eda_dir}/，再调 setup_venv(idea_src_dir='{self.eda_dir}')"
            )
        return prompt
