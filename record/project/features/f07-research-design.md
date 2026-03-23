# [F07] 研究设计

## 状态
- **实现状态**：✅已完成

## 核心文件
- `agents/elaborate_agent.py:60-79` — `ElaborateAgent.__init__()`，3 个工具，12 次迭代
- `agents/elaborate_agent.py:81-97` — `build_prompt()`，展开研究背景
- `agents/refinement_agent.py:76-109` — `RefinementAgent.__init__()`，7 个工具，20 次迭代
- `agents/refinement_agent.py:111-155` — `build_prompt()`，理论深化 + 模块设计 + 可选 feedback
- `agents/design_agent.py:36-58` — `DesignAgent.__init__()`，7 个工具，15 次迭代（legacy）
- `agents/theory_check_agent.py:48-68` — `TheoryCheckAgent.__init__()`，6 个工具，15 次迭代
- `agents/theory_check_agent.py:69-91` — `build_prompt()`，理论交叉验证 + 创新性评估 + 因果推演

## 功能描述
研究设计全流程，从背景展开到理论验证：

**ElaborateAgent**：读 topic_spec.md → web 搜索 → 写 `context.md`（≥2000 字符：背景+问题空间+具体问题+范围）

**RefinementAgent**：输出 4 个文档到 `refinement/`：
- `theory.md`（≥2000 字符）：数学公式 + 理论推导
- `model_modular.md`（≥1500 字符）：模块拆分 + 接口定义
- `model_complete.md`（≥3000 字符）：端到端设计
- `experiment_plan.md`（≥1000 字符）：分阶段实验计划

**DesignAgent**（legacy）：5 节技术计划，≥2000 字符

**TheoryCheckAgent**：提取关键声明 → 文献交叉验证 → 创新性评估（与最相似论文对比）→ 因果推演（A→B→C 链条）→ 写 `theory_review.md`（≥1500 字符）

## 运行流程

### 触发条件
- ElaborateAgent：`elaborate` 或 FSM topic_state == "elaborate"
- RefinementAgent：`refine --idea T001-I001` 或 FSM idea_state == "refine"
- TheoryCheckAgent：FSM idea_state == "theory_check"

### 处理步骤（Refine）
1. **上下文组装** — 收集 proposal + survey 材料
2. **Agent 创建** — RefinementAgent(7 工具, 20 迭代)，附加 dataset/metric 信息
3. **ReAct 循环** — 读 proposal → 搜索文献 → 写 4 个设计文档
4. **评估** — TheoryCheckAgent → TheoryEvaluator 判定

### 输出
- ElaborateAgent → `context.md`
- RefinementAgent → `refinement/` 下 4 个设计文档
- TheoryCheckAgent → `refinement/theory_review.md`

### 依赖关系
- **上游**：F01（CLI）、F05（survey）、F06（proposal）
- **下游**：F04（TheoryEvaluator）、F08（代码编写依赖设计文档）

### 错误与边界情况
- 理论 flawed → abandon
- 理论 weak → 返回 refine（最多重试 3 次）
- 理论 derivative → 返回 refine 差异化（最多重试 3 次后 abandon）
- RefinementAgent 回退时接收上一轮 theory_check 的 feedback
- 支持并行 refine（`--idea T001`）

## 测试方法
```bash
python run_research.py elaborate --topic T001
python run_research.py refine --idea T001-I001
python run_research.py theory-check --idea T001-I001
```

## 建议
（暂无）

## 变化
### [修改] 2026-03-23 — TheoryCheckAgent 增加创新性评估 + 因果推演审查步骤，RefinementAgent 支持 feedback (`535b346`)
- **目的**：理论审查增加创新性对比和因果推演维度；refine 回退时能接收上轮评估反馈
- **改动**：`theory_check_agent.py` SYSTEM_PROMPT 增加步骤 5（创新性评估）和步骤 6（因果推演）；`refinement_agent.py` `build_prompt()` 增加 `feedback` 参数
- **验证**：import 通过

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
- **目的**：实现研究设计全流程 Agent
- **改动**：新增 elaborate_agent.py + refinement_agent.py + design_agent.py + theory_check_agent.py
- **验证**：未测试
