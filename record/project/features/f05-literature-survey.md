# [F05] 文献调研管道

## 状态

- **实现状态**：✅已完成
- **核心文件**：
  - `agents/survey_helpers.py` — Agent 工厂函数：`make_search_agent()`、`make_repo_agent()`、`make_synthesis_agent()`、`make_eda_guide_agent()`、`make_code_ref_agent()`
  - `tools/openalex.py` — OpenAlex API 封装：`search_papers()`、`search_topics()`、`get_paper_references()`、`get_paper_citations()`，支持关键词/语义搜索，rate limiting
  - `tools/paper_manager.py` — 论文下载/解析/索引：`download_paper()`、`read_paper_section()`、`search_paper_index()`，PDF 解析（Zhipu/MinerU）
- **功能描述**：五步文献调研管道 — 搜索（OpenAlex 关键词+语义）→ 下载（PDF via OpenAlex）→ 解析（Zhipu API 或 MinerU）→ 代码仓库分析（GitHub clone + Claude 摘要）→ 综合（LLM 生成综述）。支持多轮调研（round_num），每轮可从指定步骤开始。论文索引存储在 `knowledge/papers/` 下。
- **测试方法**：
  ```bash
  python run_research.py survey --round 1 --step 1
  ```

## 建议

（暂无）

## 变化

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)

<details><summary>详情</summary>

**计划**：建立完整的文献调研管道
**代码修改**：新增 agents/survey_helpers.py、tools/openalex.py、tools/paper_manager.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>
