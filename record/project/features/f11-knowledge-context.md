# [F11] 知识管理与上下文

## 状态
- **实现状态**：✅已完成

## 核心文件
- `tools/knowledge_base.py:16-186` — `KnowledgeBaseManager`，智谱知识库 API（创建/上传/检索/混合召回）
- `tools/knowledge_base.py:188-223` — `search_knowledge_base()`，全局 KB 搜索（scope 过滤）
- `tools/memory.py:8-16` — `_resolve_log_path()`，统一解析日志文件路径（log_path 优先，否则 memory_dir 拼接）
- `tools/memory.py:19-25` — `_load_experiences()`，YAML 经验日志读取（支持 log_path 直传）
- `tools/memory.py:28-32` — `_save_experiences()`，YAML 经验日志写入（支持 log_path 直传）
- `tools/memory.py:35-60` — `query_memory()`，按 tags/phase/idea/topic 过滤经验（新增 log_path 参数）
- `tools/memory.py:63-103` — `add_experience()`，记录经验（insight/success/failure/observation，去重，新增 log_path 参数）
- `tools/context_manager.py:45-199` — `ContextManager`，自动上下文组装
- `tools/embedding.py:18-60` — `get_embeddings()`，智谱 Embedding-3 批量编码（max 16/request）
- `tools/embedding.py:62-70` — `cosine_similarity()`
- `tools/embedding.py:73-104` — `compute_max_similarity()`，最大相似度查找
- `tools/phase_logger.py:12-273` — 阶段日志（before/after 快照 + 产物上传 KB）

## 功能描述
知识积累与上下文管理三大机制：

**智谱知识库**（KnowledgeBaseManager）：
- 创建/删除知识库，上传文档（txt/md/pdf/doc/xls/ppt）
- 混合召回：embedding + keyword，支持 scope 过滤（topic/phase）
- 每阶段产物自动上传，后续阶段可检索

**经验日志**（memory）：
- `experience_log.yaml` 存储经验条目（ExperienceEntry 模型）
- 支持 4 种类型：insight, success, failure, observation
- 按 tags/phase/idea/topic 过滤查询
- 去重：同一 phase+topic+type+idea 不重复
- 支持 `log_path` 直传文件路径，消除硬编码路径拼接

**上下文组装**（ContextManager）：
- 按阶段规则自动收集上下文文件（PHASE_CONTEXT_RULES, IDEA_CONTEXT_RULES, GLOBAL_CONTEXT_RULES）
- `build_context(phase, idea_id, ref_ideas, ref_topics, max_tokens)` 组装完整上下文
- 支持跨 idea/topic 引用
- 自动截断超长内容

**Embedding**：
- 智谱 Embedding-3 API，支持 256/512/1024/2048 维
- 批量编码（每批 max 16 条）
- 用于 idea_scorer 的查重检测

**阶段日志**（phase_logger）：
- `log_phase_start()` — 保存研究树 before 快照
- `log_phase_end()` — 保存 after 快照 + 摘要 + 上传产物到 KB

## 运行流程

### 触发条件
- ContextManager：每个阶段执行前由 Orchestrator 调用 `build_context()`
- KnowledgeBase：Agent 运行时可调用 `search_knowledge_base()` 工具
- Memory：Agent 可调用 `query_memory()` / `add_experience()` 工具
- PhaseLogger：Orchestrator 在阶段前后调用 log_phase_start/end

### 处理步骤（上下文组装）
1. **收集 topic 文件** — 按 phase 规则收集（context.md, survey.md 等）
2. **收集 idea 文件** — 按 idea_id 收集（proposal.md, refinement/ 等）
3. **收集全局文件** — 经验日志、失败 idea 等
4. **引用处理** — `_collect_ref_ideas()` / `_collect_ref_topics()` 收集跨引用
5. **截断 + 拼接** — 按 max_tokens 截断，拼接为完整上下文字符串

### 输出
- 上下文字符串（传入 Agent prompt）
- KB 检索结果（传入 Agent 工具结果）
- 经验日志（持久化到 YAML）

### 依赖关系
- **上游**：F10（PathManager 提供路径）
- **下游**：F03-F09（所有 Agent 使用上下文和工具）

### 错误与边界情况
- 无 ZHIPU_API_KEY：KB 功能禁用，`enabled` 返回 False
- 文件不存在：`_read_file_safe()` 静默返回空字符串
- 上下文过长：按 max_tokens 截断

## 测试方法
```python
from tools.memory import query_memory
print(query_memory(phase="experiment"))

from tools.knowledge_base import search_knowledge_base
# 需配置 ZHIPU_API_KEY
```

## 建议
（暂无）

## 变化
### [重构] 2026-03-26 16:47 — memory.py 消除硬编码路径拼接 (`58ea907`)
- **目的**：让 query_memory/add_experience 支持直接传入日志文件路径，避免调用方必须拆分为 memory_dir
- **改动**：新增 `_resolve_log_path()` 统一路径解析；`_load_experiences`/`_save_experiences`/`query_memory`/`add_experience` 均新增可选 `log_path` 参数，提供时直接使用，否则保持原有 memory_dir 拼接行为
- **验证**：`python -c "from tools.memory import query_memory, add_experience"` 通过

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
- **目的**：实现知识库、经验日志、上下文管理、embedding
- **改动**：新增 knowledge_base.py + memory.py + context_manager.py + embedding.py + phase_logger.py
- **验证**：未测试
