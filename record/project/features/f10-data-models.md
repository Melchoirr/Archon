# [F10] 数据模型与路径管理

## 状态

- **实现状态**：✅已完成
- **核心文件**：
  - `shared/models/config.py` — `TopicConfig` + 子模型（TopicSection/LLMSection/EnvironmentSection/MetricsSection 等），对应 config.yaml 结构
  - `shared/models/fsm.py` — FSM 状态枚举 + Verdict/Decision 模型 + FSMSnapshot 持久化模型
  - `shared/models/enums.py` — 全局枚举（PhaseState/IdeaStatus/IdeaCategory/ExperienceType/RelationType/PhaseName）
  - `shared/models/research_tree.py` — `ResearchTree` 及子模型（Score/IdeaPhases/Iteration/ExperimentStep/Idea），computed fields
  - `shared/models/paper.py` — 论文数据模型（Author/ExternalIds/Paper/PaperIndexEntry）
  - `shared/models/memory.py` — `ExperienceEntry`，经验日志 Pydantic 模型
  - `shared/models/tool_params.py` — `ToolParamsBase` + 所有工具参数模型，`to_schema()` 桥接 Agent 工具定义
  - `shared/paths.py` — `PathManager`，所有项目路径的唯一来源（全局：knowledge/memory/；topic：ideas/results/等）
  - `shared/path_guard.py` — `PathGuard`，写操作路径白名单校验
  - `shared/utils/config_helpers.py` — `load_topic_config()`，加载 config.yaml 到 TopicConfig 模型
- **功能描述**：全链路 Pydantic 类型校验。所有数据流经 Pydantic 模型验证格式和类型。PathManager 统一管理路径（避免硬编码）。PathGuard 保护写操作不越界。tool_params 的 `to_schema()` 将 Pydantic 模型转换为 Agent 可用的 JSON Schema。
- **测试方法**：
  ```python
  from shared.models.config import TopicConfig
  config = TopicConfig()  # 验证默认值
  from shared.paths import PathManager
  pm = PathManager("/project/root", "topics/T001_test")
  ```

## 建议

（暂无）

## 变化

### [修改] 2026-03-17 10:46 — 移除硬编码 author 字段 (`68c6db0`)

<details><summary>详情</summary>

**计划**：清理 ProjectSection 中硬编码的 author 字段
**代码修改**：修改 shared/models/config.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)

<details><summary>详情</summary>

**计划**：建立 Pydantic 数据模型体系和路径管理
**代码修改**：新增 shared/ 目录全部文件
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>
