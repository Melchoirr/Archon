# [F07] 研究设计（展开/细化/理论验证）

## 状态

- **实现状态**：✅已完成
- **核心文件**：
  - `agents/elaborate_agent.py` — `ElaborateAgent`，展开研究问题空间（多视角、保持开放性），产出 `context.md`（≥2000字符）
  - `agents/refinement_agent.py` — `RefinementAgent`，细化 idea（理论推导+模块化模型设计+分阶段实验计划），产出 theory.md / model_modular.md / model_complete.md / experiment_plan.md
  - `agents/design_agent.py` — `DesignAgent`，展开为详细技术设计（问题形式化/方法描述/基线对比/实验计划/风险评估），产出 design.md
  - `agents/theory_check_agent.py` — `TheoryCheckAgent`，交叉验证理论声明 vs 文献，标记逻辑不一致，产出 theory_review.md
- **功能描述**：覆盖研究前半段（Topic→Idea 设计）。Elaborate 展开问题空间保持广度；Refinement 将 idea 细化为可执行方案；Design 产出完整技术设计；TheoryCheck 验证理论站得住脚。产出文件存储在 topic/idea 目录下。
- **测试方法**：
  ```bash
  python run_research.py elaborate --topic T001
  python run_research.py refine --idea T001-I001
  python run_research.py theory-check --idea T001-I001
  ```

## 建议

（暂无）

## 变化

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)

<details><summary>详情</summary>

**计划**：建立研究设计阶段的完整 Agent 链
**代码修改**：新增 elaborate_agent.py、refinement_agent.py、design_agent.py、theory_check_agent.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>
