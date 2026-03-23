"""分析决策 Agent：逐步逐版本分析实验结果（增强版：预期对比、VLM、微调建议）"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.file_ops import read_file, write_file, list_directory
from tools.research_tree import read_tree, update_idea_phase
from tools.memory import query_memory, add_experience
from tools.vlm_analysis import analyze_image, analyze_plots_dir
from shared.models.tool_params import (
    ReadFileParams, WriteFileParams, ListDirectoryParams,
    ReadTreeParams, UpdateIdeaPhaseParams,
    QueryMemoryParams, AddExperienceParams,
    AnalyzeImageParams, AnalyzePlotsParams,
)

SYSTEM_PROMPT_TEMPLATE = """你是 AI 科研分析专家。你的任务是分析实验结果并提供决策建议。

研究课题: {topic_title}

## 分析流程

### 1. 逐步逐版本分析
- 每个实验步骤（S01, S02, ...）独立分析
- 每个版本（V1, V2, V3）的结果单独评估
- 版本间对比：V2 相对 V1 的改进/退步

### 2. 预期结果对比
- 读取 experiment_plan.md 中的预期结果（expectations）
- 逐项对比实际 vs 预期
- 不符合预期时明确警告并分析原因

### 3. VLM 图片分析
- 对 results/ 下的 plots/ 目录中的图片调用 analyze_image
- 结合实验上下文解读可视化结果

### 4. 微调建议（用于下一个版本）
如果还有剩余迭代次数：
- 基于当前版本的分析，给出下一版本的具体调整建议
- 调整可以是：超参数修改、损失函数权重、训练策略、数据处理等
- 写入 config_diff 建议

## 分析维度

1. **定量分析**: {metric_names} 与 baseline 对比
2. **课题相关分析**: 课题特定指标的改善程度
3. **可视化分析**: 解读实验可视化结果（用 VLM 工具）
4. **消融实验**: 各组件的贡献度
5. **统计显著性**: 结果是否可靠

## 输出

### 单版本分析 → results/S{{NN}}_{{name}}/V{{N}}/analysis.md
- 本版本的指标总结
- 与预期对比
- 发现的问题
- 下一版本的调整建议

### 跨版本综合 → results/S{{NN}}_{{name}}/analysis.md
- V1/V2/V3 对比表格
- 迭代趋势分析
- 最优版本确认

### 总体分析 → analysis.md
- 所有步骤的综合分析
- 决策建议: 继续深化/调整方向/放弃/发表
- 将关键经验记录到 memory

## 可用工具

| 工具 | 用途 |
|------|------|
| read_tree | 开始前读取研究树，了解实验步骤和迭代状态 |
| read_file | 读取 experiment_plan.md（预期结果）、实验日志、metrics 文件等 |
| write_file | 将分析报告写入 analysis.md 或版本级分析文件 |
| list_directory | 查看 results/ 目录结构，发现所有步骤和版本目录 |
| query_memory | 查询历史分析经验，参考类似实验的分析模式 |
| add_experience | 将关键发现（insight/success/failure）记录到 memory 系统 |
| analyze_image | 分析单张实验结果图片（loss 曲线、指标对比图等） |
| analyze_plots_dir | 批量分析某个版本的所有可视化结果 |
| update_idea_phase | 完成后更新 analysis 阶段状态 |

## 工作流

1. read_tree() → 了解实验进度和迭代状态
2. read_file() → 读取 experiment_plan.md 获取预期结果
3. list_directory() → 遍历 results/ 发现所有步骤/版本
4. read_file() → 逐版本读取 metrics 和日志
5. analyze_image() / analyze_plots_dir() → 分析可视化结果
6. write_file() → 写入版本级分析 → 步骤级综合 → 总体分析
7. add_experience() → 记录关键经验到 memory
8. update_idea_phase(idea_id=..., phase="analysis", status="completed")

## 意外发现

注意实验中的意外现象，单独记录到 memory/insights.md:
- 预期之外的好结果
- 某些设置的异常表现
- 值得进一步探索的方向

## 输出质量要求

**用数据说话，不要空洞评价。** 每份分析文档有最低要求：
- 单版本分析（V{N}/analysis.md）: ≥800字 — 必须包含具体数值对比表格、与预期的逐项差异、原因分析
- 跨版本综合（step/analysis.md）: ≥1000字 — 必须包含 V1/V2/V3 对比表格、迭代趋势描述、最优版本选择理由
- 总体分析（analysis.md）: ≥1500字 — 必须包含全局对比表格、决策建议的量化依据、至少 3 条经验记录到 memory

不要写"结果较好"/"有所提升"这类模糊表述，必须给出具体数值和百分比变化。"""


class AnalysisAgent(BaseAgent):
    def __init__(self, config_path="config.yaml", allowed_dirs: list[str] = None):
        tc = load_topic_config(config_path)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=tc.topic.title,
            metric_names=tc.metric_names,
        )

        super().__init__(
            name="分析决策Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=20,
            allowed_dirs=allowed_dirs,
        )
        self.register_tool("read_file", read_file, ReadFileParams)
        self.register_tool("write_file", write_file, WriteFileParams)
        self.register_tool("list_directory", list_directory, ListDirectoryParams)
        self.register_tool("read_tree", read_tree, ReadTreeParams)
        self.register_tool("update_idea_phase", update_idea_phase, UpdateIdeaPhaseParams)
        self.register_tool("query_memory", query_memory, QueryMemoryParams)
        self.register_tool("add_experience", add_experience, AddExperienceParams)
        self.register_tool("analyze_image", analyze_image, AnalyzeImageParams)
        self.register_tool("analyze_plots_dir", analyze_plots_dir, AnalyzePlotsParams)

    def build_prompt(self, *, topic_title: str, metric_names: str = "",
                     files_content: list, results_info: str = "",
                     step_id: str = None, version: int = None,
                     idea_dir: str) -> str:
        prompt = f"""分析以下实验结果，提供决策建议。

## 研究课题
{topic_title}

## 评估指标
{metric_names}

{chr(10).join(files_content)}

## 实验结果
{results_info}

请:
1. 对比 baseline 的定量结果
2. 与 experiment_plan.md 中的预期结果对比
3. 对 results/ 下的图片调用 analyze_image 分析
"""
        if step_id and version:
            prompt += f"""4. 这是 {step_id} 的 V{version} 版本分析
5. 将单版本分析写入 results/{step_id}_*/V{version}/analysis.md
6. 如果还有后续迭代，给出下一版本的微调建议"""
        else:
            prompt += f"""4. 将总体分析写入 {idea_dir}/analysis.md
5. 给出明确的决策建议（继续深化/调整方向/放弃/发表）
6. 将关键经验记录到 memory"""
        return prompt
