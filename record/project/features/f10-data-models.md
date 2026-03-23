# [F10] 数据模型与路径管理

## 状态
- **实现状态**：✅已完成

## 核心文件
- `shared/paths.py:9-288` — `PathManager`，统一路径解析（全局路径 + topic 路径 + idea 路径 + 发现方法）
- `shared/path_guard.py:43-161` — `PathGuard`，写操作安全校验（正则检测重定向/tee/mkdir/wget/cp/mv/touch）
- `shared/models/config.py:44-75` — `TopicConfig`，配置校验（含 TopicSection, LLMSection, ProjectSection, EnvironmentSection, MetricsSection）
- `shared/models/research_tree.py:10-101` — 研究树模型（Score, IdeaPhases, Iteration, ExperimentStep, Relationship, Idea, ResearchRoot, ResearchTree）
- `shared/models/fsm.py:10-128` — FSM 模型（FSMState, AnalysisVerdict, TheoryVerdict, DebugVerdict, SurveyVerdict, *Decision, TransitionRecord, IdeaFSMState, FSMSnapshot）
- `shared/models/paper.py:8-43` — 论文模型（Author, ExternalIds, Paper, PaperIndexEntry）
- `shared/models/memory.py:10-19` — `ExperienceEntry`，经验日志条目
- `shared/models/tool_params.py:12-325` — `ToolParamsBase` + 30+ 工具参数 Pydantic 模型
- `shared/models/enums.py:6-65` — 枚举定义（PhaseState, IdeaStatus, IdeaCategory, ExperienceType, RelationType, PhaseName）
- `shared/utils/config_helpers.py:8-24` — `load_topic_config()`
- `shared/templates/experiment_infrastructure.md` — 实验代码基础设施规范

## 功能描述
系统的类型安全基础设施层：

**PathManager** — 统一路径解析，单一来源：
- 全局路径：knowledge/, papers/, repos/, memory/, topics/
- Topic 路径：config.yaml, tree.yaml, fsm_state.yaml, context.md, survey/, ideas/
- Idea 路径：proposal, refinement/, src/, results/, conclusion
- 发现方法：`find_latest_topic()`, `list_idea_ids()`

**PathGuard** — 写操作安全：
- 正则检测写目标：>, >>, tee, mkdir -p, wget -O, curl -o, cp, mv, touch
- `make_guarded_handler()` 包装工具 handler

**Pydantic 模型体系**：
- TopicConfig：配置校验 + computed properties (dataset_names, metric_names 等)
- ResearchTree：层级追踪（topic → idea → phase → step → iteration）
- FSM 模型：状态枚举 + verdict + decision + snapshot
- ToolParamsBase：30+ 工具参数模型，`to_schema()` 自动转 JSON Schema
- Score：4 维评分 + 加权 composite（Novelty×0.35 + Significance×0.35 + Feasibility×0.20 + Alignment×0.10）

**实验代码模板**：标准化目录结构、YAML 配置系统、Trainer/Evaluator 规范、Ablation 支持、可视化模块

## 运行流程

### 触发条件
- PathManager：Orchestrator/Agent 初始化时创建
- Pydantic 模型：数据读写时自动校验
- PathGuard：BaseAgent 注册工具时包装

### 处理步骤
1. **PathManager 初始化** — `PathManager(project_root, topic_dir)` 设置根目录
2. **路径解析** — 调用属性方法（如 `paths.idea_dir(idea_id)`）获取绝对路径
3. **模型校验** — 数据加载时 `Model.model_validate(data)` 自动校验
4. **工具安全** — `make_guarded_handler()` 在工具执行前检查路径合法性

### 输出
- 类型安全的路径字符串
- 校验后的 Pydantic 模型实例
- PathGuard 校验结果 (bool, error_msg)

### 依赖关系
- **上游**：无（基础设施层）
- **下游**：F01-F12 所有模块依赖 PathManager 和 Pydantic 模型

### 错误与边界情况
- idea_dir() 支持 "T001-I001" 和 "I001" 两种格式
- PathGuard 违规：返回错误消息，不阻止 Agent 循环
- config.yaml 缺少字段：Pydantic 默认值填充

## 测试方法
```python
from shared.paths import PathManager
pm = PathManager("/project/root", "topics/T001_test")
print(pm.config_yaml)  # topics/T001_test/config.yaml
```

## 建议
（暂无）

## 变化
### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
- **目的**：实现类型安全基础设施
- **改动**：新增 shared/ 目录，含 paths.py + path_guard.py + models/ + templates/
- **验证**：未测试

### [重构] 2026-03-17 10:38 — FSM 模型 + 评估器决策模型 (`b6b5ff6`)
- **目的**：新增 FSM 状态和决策 Pydantic 模型
- **改动**：新增 shared/models/fsm.py
- **验证**：未测试

### [修改] 2026-03-17 10:46 — 移除 author 配置字段 (`68c6db0`)
- **目的**：TopicConfig 移除硬编码 author 字段
- **改动**：config.py 中 ProjectSection 不再包含 author
- **验证**：未测试
