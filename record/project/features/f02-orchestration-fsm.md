# [F02] 编排引擎与 FSM 状态机

## 状态

- **实现状态**：✅已完成
- **核心文件**：
  - `agents/orchestrator.py:39` — `ResearchOrchestrator`，管理研究阶段流转、Agent 实例化、检查点
  - `agents/fsm_engine.py:77` — `ResearchFSM`，有限状态机引擎（topic 级 + idea 级状态流转）
  - `shared/models/fsm.py:10` — `FSMState` 枚举（14 个状态）+ 各类 Verdict/Decision 模型 + `FSMSnapshot` 持久化
- **功能描述**：三层分离架构 — 工作 Agent（执行任务）→ 评估 Agent（做判断）→ FSM 引擎（路由 + 持久化）。Topic 级线性流转（elaborate→survey→ideation），Idea 级条件流转（refine→theory_check→code_reference→code→debug→experiment→analyze→conclude）。支持回退（analyze→refine）、abandon、用户确认转换。状态持久化到 `fsm_state.yaml`。
- **测试方法**：
  ```bash
  python run_research.py fsm status
  python run_research.py fsm run --topic T001
  python run_research.py fsm run --idea T001-I001
  python run_research.py fsm history
  ```

## 建议

（暂无）

## 变化

### [修复] 2026-03-21 11:07 — FSM 跨状态回退死循环修复 (`f4aaf7a`)

<details><summary>详情</summary>

**计划**：修复 retry_counts 无条件递增导致的死循环 + step() 补齐
**代码修改**：修复 fsm_engine.py 中 retry_counts 逻辑和 step() 方法
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>

### [重构] 2026-03-17 10:38 — FSM 引擎重构、评估器独立 (`b6b5ff6`)

<details><summary>详情</summary>

**计划**：将评估逻辑从 FSM 引擎中分离到独立评估器
**代码修改**：重构 fsm_engine.py，新增 evaluators/ 目录，状态转换表重新设计
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)

<details><summary>详情</summary>

**计划**：实现编排引擎和 FSM 状态机
**代码修改**：新增 orchestrator.py、fsm_engine.py、shared/models/fsm.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>
