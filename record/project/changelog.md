# 变更日志

## 格式说明

每条记录包含：日期、变更类型标签、变更描述、影响范围。

类型标签：`[新增]` `[修改]` `[修复]` `[重构]` `[删除]`

---

## 2026-03-21

- `[修复]` fsm_engine.py — 修复 FSM 跨状态回退死循环 Bug
  - `retry_counts` 改为无条件递增（原来仅 same-state 转换递增，跨状态回退计数永远为 0）
  - `step()` 方法补充 retry_counts 更新和完整 feedback 提取逻辑
  - MAX_RETRIES 各值 +1 补偿首次进入计数
  - 影响范围：FSM 状态转移（refine↔theory_check、experiment↔analyze、debug↔code 等回退循环）

## 2026-03-19 — 当前未提交变更（feat/supervisor-agent 分支）

- `[修改]` fsm_engine.py — 扩展 FSM 引擎功能（+33 行）
  - 影响范围：状态转移逻辑
- `[修改]` ideation_agent.py — 小幅调整创意生成逻辑
  - 影响范围：Ideation 阶段
- `[修改]` orchestrator.py — 增强编排器功能（+16 行）
  - 影响范围：全局流程控制
- `[重构]` survey_helpers.py — 重构 survey 辅助函数（186 行大幅改动）
  - 影响范围：Survey 阶段所有步骤
- `[修改]` requirements.txt — 调整依赖
  - 影响范围：项目环境
- `[新增]` shared/models/config.py — 新增配置字段
  - 影响范围：TopicConfig 模型
- `[修改]` tools/context_manager.py — 调整上下文注入规则
  - 影响范围：各阶段上下文
- `[修改]` tools/idea_scorer.py — 大幅增强想法评分器（+155 行）
  - 影响范围：Ideation 阶段评分和去重
- `[新增]` tools/embedding.py — 新增嵌入向量工具模块
  - 影响范围：相似度计算

## 2026-03-17

### 68c6db0 — Remove hardcoded author field from project config

- `[删除]` 移除项目配置中硬编码的 author 字段
  - 影响范围：shared/models/config.py

### b6b5ff6 — Refactor: FSM engine, evaluators, venv isolation, and EDA env support

- `[重构]` FSM 引擎重构，引入有限状态机管理研究流程
- `[新增]` Evaluator 体系（AnalysisEvaluator, TheoryEvaluator, SurveyEvaluator）
- `[新增]` venv 隔离机制，每个想法独立虚拟环境
- `[新增]` EDA 环境支持
  - 影响范围：agents/, tools/, shared/

## 2026-03-11

### 969dd1c — Initial commit: Archon — AI-driven research automation system

- `[新增]` 项目初始化
  - 11 个 Worker Agent + BaseAgent
  - 20 个工具模块
  - Pydantic 数据模型体系
  - ReAct 循环 Agent 框架
  - 研究 10+ 阶段流水线
  - 知识库和经验系统
  - 影响范围：全部
