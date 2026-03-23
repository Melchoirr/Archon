# [F11] 知识管理与上下文

## 状态

- **实现状态**：✅已完成
- **核心文件**：
  - `tools/knowledge_base.py` — `KnowledgeBaseManager`，智谱知识库管理（创建/列表/删除）+ 文件上传（doc/pdf/csv 等）
  - `tools/memory.py` — `query_memory()`、`add_experience()`，研究经验日志 CRUD（insight/success/failure/observation），YAML 存储
  - `tools/context_manager.py` — `ContextManager`，按阶段自动注入上下文文件（ideation 需 survey；code 需 infra template 等），管理上下文大小限制
  - `tools/embedding.py` — `get_embeddings()`，智谱 Embedding-3 批量文本嵌入 + 语义相似度计算
- **功能描述**：知识生命周期管理 — KnowledgeBase 通过智谱 API 管理外部知识库；Memory 以结构化 YAML 记录研究经验供后续阶段查询；ContextManager 根据当前研究阶段自动组装上下文（如 ideation 阶段注入 survey 综述 + baseline 信息）；Embedding 支持语义搜索。每个 Agent 自动拥有 `search_knowledge_base` 工具。
- **测试方法**：
  ```bash
  python run_research.py memory --tags "insight" --phase "survey"
  ```

## 建议

（暂无）

## 变化

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)

<details><summary>详情</summary>

**计划**：建立知识管理和上下文注入系统
**代码修改**：新增 knowledge_base.py、memory.py、context_manager.py、embedding.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>
