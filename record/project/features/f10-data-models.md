# [F10] 数据模型与路径管理

## 状态
- **实现状态**：✅已完成

## 核心文件
- `shared/paths.py:9-288` — `PathManager`，统一路径解析（全局路径 + topic 路径 + idea 路径 + 发现方法）
- `shared/path_guard.py:43-161` — `PathGuard`，写操作安全校验（正则检测重定向/tee/mkdir/wget/cp/mv/touch）
- `shared/models/config.py:44-75` — `TopicConfig`，配置校验（含 TopicSection, LLMSection, ProjectSection, EnvironmentSection, MetricsSection）
- `shared/models/idea_registry.py` — Idea 注册表模型（Score, Relationship, TopicMeta, IdeaEntry, IdeaRegistry）— 替代已删除的 research_tree.py
- `shared/models/fsm.py` — FSM 核心模型（FSMState, 4 个 Verdict 枚举, IdeaFSMState, FSMSnapshot）— 纯恢复数据
- `shared/models/decisions.py` — 评估器决策模型（AnalysisDecision, TheoryDecision, SurveyDecision, DebugDecision + to_summary()）
- `shared/models/audit.py` — 审计记录模型（TransitionRecord，verdict_summary 替代 decision_snapshot）
- `shared/models/paper.py:8-43` — 论文模型（Author, ExternalIds, Paper, PaperIndexEntry）
- `shared/models/memory.py:10-19` — `ExperienceEntry`，经验日志条目
- `shared/models/tool_params.py:12-426` — `ToolParamsBase` + 30+ 工具参数 Pydantic 模型（含丰富 docstring：使用场景/返回格式/示例），含 `CheckLocalKnowledgeParams`
- `shared/models/enums.py` — 枚举定义（PhaseState, IdeaStatus, IdeaCategory, ExperienceType, RelationType）— PhaseName 已删除（与 FSMState 重复）
- `shared/utils/config_helpers.py:8-24` — `load_topic_config()`
- `shared/templates/experiment_infrastructure.md` — 实验代码基础设施规范

## 功能描述
系统的类型安全基础设施层：

**PathManager** — 统一路径解析，单一来源：
- 全局路径：knowledge/, papers/, repos/, memory/, topics/
- Topic 路径：config.yaml, fsm_state.yaml, idea_registry.yaml, audit_log.yaml, context.md, survey/, ideas/
- Idea 路径：proposal, refinement/, src/, results/, conclusion
- 发现方法：`find_latest_topic()`, `list_idea_ids()`

**PathGuard** — 写操作安全：
- 正则检测写目标：>, >>, tee, mkdir -p, wget -O, curl -o, cp, mv, touch
- `make_guarded_handler()` 包装工具 handler

**Pydantic 模型体系**：
- TopicConfig：配置校验 + computed properties (dataset_names, metric_names 等)
- IdeaRegistry：Idea 元数据管理（替代 ResearchTree）
- FSM 模型：状态枚举 + verdict（fsm.py）；decision 模型（decisions.py）；审计记录（audit.py）
- ToolParamsBase：30+ 工具参数模型，`to_schema()` 自动转 JSON Schema（docstring 含使用场景、返回格式、调用示例，LLM 可通过 description 字段获取完整工具指导）
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
### [实现] 2026-03-26 17:14 — PathManager 新增索引路径 + tool_params 新增注册模型 (`2db43ea`)
- **目的**：为数据集/仓库索引提供路径支持和参数模型
- **改动**：`shared/paths.py` 新增 `repo_index`（repos_dir/index.yaml）和 `dataset_index`（dataset_cards_dir/index.yaml）属性；`shared/models/tool_params.py` 更新 `CheckLocalKnowledgeParams` 支持 dataset 类型，新增 `RegisterDatasetParams`（name/url/local_path/format/description）和 `RegisterRepoParams`（repo_url/local_path/has_summary）
- **验证**：`python -c 'from shared.models.tool_params import RegisterDatasetParams, RegisterRepoParams'` 通过

### [重构] 2026-03-26 15:49 — 模型体系重组：消除 research_tree，三文件分离 (`7a63dca`)
- **目的**：消除 FSM + research_tree 双轨并行，清晰分离恢复数据/Idea 元数据/审计记录
- **改动**：
  - 新增 `shared/models/idea_registry.py`（Score, Relationship, TopicMeta, IdeaEntry, IdeaRegistry）
  - 新增 `shared/models/decisions.py`（4 个 Decision + to_summary()，从 fsm.py 分离）
  - 新增 `shared/models/audit.py`（TransitionRecord，verdict_summary 替代 decision_snapshot）
  - 精简 `shared/models/fsm.py`（删除 TransitionRecord/Decision/feedback/transition_history，新增 schema_version + topic_retry_counts）
  - 删除 `shared/models/research_tree.py`（IdeaPhases, ExperimentStep, Iteration, ResearchTree 等全部删除）
  - 删除 `shared/models/enums.py` 中 PhaseName（与 FSMState 重复）
  - `shared/models/tool_params.py` 删除旧 tree params（ReadTreeParams, UpdateIdeaPhaseParams 等），保留 ReadResearchStatusParams + AddIdeaParams
  - `shared/paths.py` 新增 idea_registry_yaml + audit_log_yaml，删除 tree_yaml
- **验证**：全部 import 通过

### [实现] 2026-03-25 19:42 — 新增 CheckLocalKnowledgeParams 参数模型 (`eeb0585`)
- **目的**：为 check_local_knowledge 工具提供 Pydantic 参数校验
- **改动**：`shared/models/tool_params.py` 新增 `CheckLocalKnowledgeParams(query, resource_type)`；`tools/__init__.py` 导出新模型
- **验证**：`CheckLocalKnowledgeParams.to_schema()` 输出正确 JSON Schema

### [修改] 2026-03-24 00:11 — 丰富 18 个工具的 docstring（使用场景/返回/示例） (`d96766b`)
- **目的**：LLM 通过 tool schema description 获取工具使用指导，原 docstring 过于简略（一句话）
- **改动**：`shared/models/tool_params.py` 为 ReadFile/WriteFile/AppendFile/ListDirectory/ReadTree/UpdateIdeaPhase/UpdateIdeaStatus/UpdateSurveyStatus/UpdateElaborateStatus/AddIdea/AddExperimentStep/UpdateIteration/QueryMemory/AddExperience/DownloadPaper/ReadPaperSection/RunCommand/AnalyzeImage/AnalyzePlots 共 18 个 Params 类补充结构化 docstring
- **验证**：`to_schema()["description"]` 验证全部包含「使用场景」「返回」「示例」

### [修改] 2026-03-23 23:05 — TheoryVerdict 增加 derivative + TheoryDecision 扩展字段 (`535b346`)
- **目的**：支持创新性评估、因果推演和跨 idea 去重
- **改动**：`shared/models/fsm.py` TheoryVerdict 新增 `derivative` 枚举值；TheoryDecision 新增 6 个字段（novelty_assessment, novelty_score, differentiation, mechanism_reasoning, mechanism_confidence, similar_ideas_in_batch）
- **验证**：`python -c "from shared.models.fsm import TheoryVerdict, TheoryDecision"` 通过

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
