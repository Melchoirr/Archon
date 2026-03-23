# [F06] Idea 生成与评分

## 状态

- **实现状态**：✅已完成
- **核心文件**：
  - `agents/ideation_agent.py` — `IdeationAgent`，基于文献 gap 生成研究 idea，去重、维护 idea graph、确保原子创新点
  - `tools/idea_scorer.py` — `score_idea()`，多维评分（novelty/significance/feasibility/alignment），自动提取查询→文献验证→LLM 评分
  - `tools/idea_graph.py` — `add_idea_relationship()`、`get_idea_graph()`，Idea 关系图 CRUD（builds_on/alternative_to/complementary/combines_with）
- **功能描述**：从文献调研 gap 中生成研究 idea，每个 idea 要求原子创新点。评分工具先提取搜索查询检查 prior work，再由 LLM 从四个维度评分（自动计算 composite）。Idea 间关系以有向图形式存储在 YAML 中。
- **测试方法**：
  ```bash
  python run_research.py ideation --topic T001
  ```

## 建议

（暂无）

## 变化

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)

<details><summary>详情</summary>

**计划**：实现 Idea 生成、评分、关系管理
**代码修改**：新增 agents/ideation_agent.py、tools/idea_scorer.py、tools/idea_graph.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>
