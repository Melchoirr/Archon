# [F09] 分析与结论

## 状态
- **实现状态**：✅已完成

## 核心文件
- `agents/analysis_agent.py:84-125` — `AnalysisAgent.__init__()`，9 个工具，20 次迭代；system prompt 含工具表格+工作流
- `agents/analysis_agent.py:126-156` — `build_prompt()`，分析 prompt（单版本/总分析）
- `agents/analysis_agent.py:15-98` — system prompt（数据驱动、VLM 分析、≥1500 字符，含工具表格+8 步工作流）
- `agents/conclusion_agent.py:76-111` — `ConclusionAgent.__init__()`，5 个工具，15 次迭代；system prompt 含工具表格+工作流
- `agents/conclusion_agent.py:113-129` — `build_prompt()`，结论 prompt
- `agents/conclusion_agent.py:11-89` — system prompt（客观、6 节、≥2000 字符，含工具表格+5 步工作流）
- `tools/vlm_analysis.py:25-72` — `analyze_image()`，Qwen VL 3.5-Plus 图像分析
- `tools/vlm_analysis.py:74-98` — `analyze_plots_dir()`，批量图表分析

## 功能描述
实验后的分析与总结：

**AnalysisAgent**：
- 逐步骤逐版本独立分析：与 baseline 比较、与 experiment_plan 预期比较
- VLM 图表分析：`analyze_plots_dir()` → Qwen VL 3.5-Plus 批量分析
- 数据驱动：具体数值，非模糊判断
- 最小要求：单版本≥800 字符、跨版本≥1000 字符、总分析≥1500 字符
- 调参建议：下一版本的具体调整方向

**ConclusionAgent**：
- 读取全链路产物：proposal → refinement → src → results → analysis
- 6 必含节：Idea 评价、代码实现评价、结果总结、意外发现、预期对比、经验教训
- 客观、不美化、≥2000 字符（300+200+500+200+300+300）
- 记录经验到 `memory/experience_log.yaml`

**VLM 集成**：DashScope/Aliyun OpenAI 兼容 API，Qwen VL 3.5-Plus 模型

## 运行流程

### 触发条件
- AnalysisAgent：`analyze --idea T001-I001` 或 FSM idea_state == "analyze"
- ConclusionAgent：`conclude --idea T001-I001` 或 FSM idea_state == "conclude"

### 处理步骤（分析）
1. **上下文组装** — 收集 results/ 实验结果、experiment_plan、baselines
2. **Agent 创建** — AnalysisAgent(7 工具, 20 迭代)
3. **ReAct 循环** — 读结果 → VLM 分析图表 → 与 baseline/预期对比 → 写 analysis.md
4. **评估** — AnalysisEvaluator 结构化评估 → FSM 路由

### 处理步骤（结论）
1. **Agent 创建** — ConclusionAgent(5 工具, 15 迭代)
2. **ReAct 循环** — 读全链路 → 写 conclusion.md → 记录经验

### 输出
- AnalysisAgent → `results/*/analysis.md`
- ConclusionAgent → `ideas/*/conclusion.md`

### 依赖关系
- **上游**：F08（实验输出）、F02（FSM 触发）
- **下游**：F04（AnalysisEvaluator → FSM 路由）、F11（经验记录）

### 错误与边界情况
- VLM API 失败：跳过图表分析，仅基于数值分析
- 分析结果 tune → 返回 experiment 调参；code_bug → 返回 debug；abandon → 放弃 idea

## 测试方法
```bash
python run_research.py analyze --idea T001-I001
python run_research.py conclude --idea T001-I001
```

## 建议
（暂无）

## 变化
### [修改] 2026-03-24 01:20 — AnalysisAgent/ConclusionAgent system prompt 添加工具表格+工作流 (`d96766b`)
- **目的**：Agent system prompt 缺乏工具使用指导，LLM 不清楚何时/如何调用工具
- **改动**：`agents/analysis_agent.py` SYSTEM_PROMPT 插入可用工具表格（9 行）和 8 步工作流；`agents/conclusion_agent.py` SYSTEM_PROMPT 插入可用工具表格（5 行）和 5 步工作流
- **验证**：import 通过

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
- **目的**：实现实验分析 + 客观结论
- **改动**：新增 analysis_agent.py + conclusion_agent.py + vlm_analysis.py
- **验证**：未测试
