# [F12] 通用工具集

## 状态

- **实现状态**：✅已完成
- **核心文件**：
  - `tools/file_ops.py` — `read_file()`、`write_file()`、`append_file()`、`list_directory()`，基础文件 I/O + 自动创建目录
  - `tools/web_search.py` — `web_search()`，DuckDuckGo 免费搜索（无 API key）
  - `tools/github_repo.py` — `clone_repo()`、`summarize_repo()`、`list_repos()`，浅克隆 + Claude Code 代码摘要
  - `tools/research_tree.py` — `ResearchTreeService`，线程安全的 research_tree.yaml CRUD（Pydantic 验证）
  - `tools/phase_logger.py` — `log_phase_start()`、`log_phase_end()`，阶段快照（审计追踪）
  - `tools/config_updater.py` — `update_config_section()`，YAML 配置节更新
- **功能描述**：供所有 Agent 和编排器使用的基础工具。file_ops 是最底层的文件操作；web_search 提供无依赖的网页搜索；github_repo 管理参考代码仓库；research_tree 是研究树的持久化层（线程安全）；phase_logger 在阶段开始/结束时快照状态；config_updater 安全更新 YAML 配置。
- **测试方法**：
  ```python
  from tools.file_ops import read_file, write_file
  from tools.web_search import web_search
  result = web_search("test query", max_results=3)
  ```

## 建议

（暂无）

## 变化

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)

<details><summary>详情</summary>

**计划**：建立通用工具集
**代码修改**：新增 file_ops.py、web_search.py、github_repo.py、research_tree.py、phase_logger.py、config_updater.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>
