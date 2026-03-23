# [F12] 通用工具集

## 状态
- **实现状态**：✅已完成

## 核心文件
- `tools/file_ops.py:1-31` — `read_file()`, `write_file()`, `append_file()`, `list_directory()`
- `tools/web_search.py:1-22` — `web_search()`，DuckDuckGo 搜索（免费，无 API key）
- `tools/github_repo.py:15-43` — `clone_repo()`，浅克隆 `git clone --depth 1`
- `tools/github_repo.py:44-104` — `summarize_repo()`，Claude Code 生成代码摘要（缓存）
- `tools/github_repo.py:106-118` — `list_repos()`，列出已克隆仓库
- `tools/research_tree.py:20-250` — `ResearchTreeService`，研究树 CRUD（线程安全，Pydantic 校验）
- `tools/research_tree.py:251-321` — 模块级工具函数包装（懒加载）
- `tools/config_updater.py:1-26` — `update_config_section()`，config.yaml 段更新

## 功能描述
被多个 Agent 共用的通用工具：

**文件操作**（file_ops）：读、写、追加、列目录。所有 Agent 的基础工具。

**Web 搜索**（web_search）：DuckDuckGo 封装，返回 JSON 结果。用于 elaborate、ideation、theory_check 等阶段。

**GitHub 仓库**（github_repo）：
- `clone_repo()` 浅克隆（--depth 1）到 `knowledge/repos/`
- `summarize_repo()` 调用 `claude -p` 生成 SUMMARY.md（缓存，不重复生成）
- `list_repos()` 列出已克隆仓库及摘要状态

**研究树**（ResearchTreeService）：
- 线程安全（threading.Lock）CRUD
- 操作：load/save, read_tree, update_idea_phase/status, update_survey/elaborate_status
- add_idea, update_idea_scores, add_experiment_step, update_iteration, add_relationship
- ID 生成：next_topic_id(T001...), next_idea_id(I001...), _next_step_id(S01...)
- 模块级函数包装：懒加载 ResearchTreeService 实例

**配置更新**（config_updater）：Agent 可调用 `update_config_section()` 动态更新 config.yaml 的指定 section

## 运行流程

### 触发条件
- 被各 Agent 通过 `register_tool()` 注册，在 ReAct 循环中按需调用

### 处理步骤（以 research_tree 为例）
1. **注册** — Agent `__init__` 中 `self.register_tool("read_tree", read_tree, ReadTreeParams)`
2. **LLM 调用工具** — ReAct 循环中 LLM 返回 `tool_use: read_tree`
3. **执行** — `ResearchTreeService.read_tree()` 加载 YAML → 返回 JSON 字符串
4. **结果** — 工具结果作为 `tool_result` 追加到消息历史

### 输出
- file_ops：文件内容/写入确认/目录列表
- web_search：JSON 搜索结果
- github_repo：克隆确认/SUMMARY.md/仓库列表
- research_tree：JSON 研究树/操作确认
- config_updater：更新确认

### 依赖关系
- **上游**：F03（BaseAgent 工具注册机制）
- **下游**：F05-F09（各 Agent 使用这些工具）

### 错误与边界情况
- file_ops：FileNotFoundError 返回错误信息
- web_search：DuckDuckGo 无结果返回空列表
- clone_repo：已存在目录时跳过
- research_tree：线程安全（Lock 保护），idea 不存在时打印警告

## 测试方法
```python
from tools.file_ops import read_file, list_directory
print(list_directory("."))

from tools.web_search import web_search
print(web_search("time series forecasting", max_results=3))
```

## 建议
（暂无）

## 变化
### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
<details><summary>详情</summary>

**计划**：实现通用工具集
**代码修改**：新增 file_ops.py + web_search.py + github_repo.py + research_tree.py + config_updater.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|

</details>
