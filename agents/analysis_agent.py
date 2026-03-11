"""分析决策 Agent：逐步逐版本分析实验结果（增强版：预期对比、VLM、微调建议）"""
from .base_agent import BaseAgent
from shared.utils.config_helpers import load_topic_config
from tools.file_ops import read_file, write_file, list_directory, READ_FILE_SCHEMA, WRITE_FILE_SCHEMA, LIST_DIRECTORY_SCHEMA
from tools.research_tree import read_tree, update_tree, READ_TREE_SCHEMA, UPDATE_TREE_SCHEMA
from tools.memory import query_memory, add_experience, QUERY_MEMORY_SCHEMA, ADD_EXPERIENCE_SCHEMA
from tools.vlm_analysis import analyze_image, analyze_plots_dir, ANALYZE_IMAGE_SCHEMA, ANALYZE_PLOTS_SCHEMA

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

## 意外发现

注意实验中的意外现象，单独记录到 memory/insights.md:
- 预期之外的好结果
- 某些设置的异常表现
- 值得进一步探索的方向

不要简化或妥协方案，除非 idea 本身被证明有根本性错误。遇到实现困难时，寻找解决办法而非回退到更简单的版本。"""


class AnalysisAgent(BaseAgent):
    def __init__(self, config_path="config.yaml"):
        tc = load_topic_config(config_path)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            topic_title=tc["topic_title"],
            metric_names=tc["metric_names"],
        )

        super().__init__(
            name="分析决策Agent",
            system_prompt=system_prompt,
            tools=[],
            max_iterations=25,
        )
        self.register_tool("read_file", read_file, READ_FILE_SCHEMA)
        self.register_tool("write_file", write_file, WRITE_FILE_SCHEMA)
        self.register_tool("list_directory", list_directory, LIST_DIRECTORY_SCHEMA)
        self.register_tool("read_tree", read_tree, READ_TREE_SCHEMA)
        self.register_tool("update_tree", update_tree, UPDATE_TREE_SCHEMA)
        self.register_tool("query_memory", query_memory, QUERY_MEMORY_SCHEMA)
        self.register_tool("add_experience", add_experience, ADD_EXPERIENCE_SCHEMA)
        self.register_tool("analyze_image", analyze_image, ANALYZE_IMAGE_SCHEMA)
        self.register_tool("analyze_plots_dir", analyze_plots_dir, ANALYZE_PLOTS_SCHEMA)
