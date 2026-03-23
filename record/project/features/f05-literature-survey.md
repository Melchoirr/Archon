# [F05] 文献调研管道

## 状态
- **实现状态**：✅已完成

## 核心文件
- `agents/survey_helpers.py:32-152` — 搜索策略 prompt（4 阶段搜索）
- `agents/survey_helpers.py:199-226` — `make_search_agent()`，搜索 Agent 工厂（9 个工具）
- `agents/survey_helpers.py:344-389` — `summarize_single_paper()`，单篇摘要（单次 LLM）
- `agents/survey_helpers.py:447-484` — `build_repo_prompt()` / `make_repo_agent()`，Repo 研究 Agent 工厂
- `tools/openalex.py:230-260` — `search_topics()`，OpenAlex topic 搜索
- `tools/openalex.py:261-345` — `search_papers()`，论文搜索（keyword/semantic/exact）
- `tools/openalex.py:347-403` — `get_paper_references()` / `get_paper_citations()`，引用图遍历
- `tools/paper_manager.py:172-273` — `_parse_pdf_zhipu()` / `_parse_pdf_mineru()`，PDF 双后端解析
- `tools/paper_manager.py:305-358` — `download_paper()`，论文下载 + 解析
- `tools/paper_manager.py:360-465` — `read_paper_section()`，论文分段阅读（模糊匹配）
- `agents/data_agent.py:88-161` — `DataAgent`，数据下载 + EDA（8 个工具，35 次迭代）

## 功能描述
5 步文献调研流水线：

**Step 1 — 论文搜索**（4 阶段搜索策略）：
- Phase 0：确定 OpenAlex topic_id
- Phase 1：经典文献（显式论文 + 研究角度 + 种子关键词）
- Phase 1.5：前沿论文（2024-2025，低引用，web_search → search_papers）
- Phase 2：引用图扩展（top 论文的 references）
- Phase 3：写 paper_list.yaml（按 citation_count 排序）

**Step 2+3 — 下载 + 摘要**：PDF 下载 → Zhipu/MinerU 解析 → LLM 摘要

**Step 4 — Repo 研究**：GitHub 仓库搜索 → 浅克隆 → Claude 摘要

**Step 4a+4b — 数据 EDA**：EDA 指南生成 → DataAgent 下载数据 + 执行 + VLM 分析

**Step 5 — 综合**：survey.md + baselines.md + datasets.md + metrics.md + leaderboard.md

**关键技术**：OpenAlex API（2.71 亿篇，CC0）、PDF 双后端（Zhipu → MinerU）、polite pool rate limit

## 运行流程

### 触发条件
- `python run_research.py survey [--round N] [--step N]`
- FSM topic_state == "survey"

### 处理步骤
1. **Step 1** — `make_search_agent()` → 4 阶段搜索 → `paper_list.yaml`
2. **Step 2** — 遍历 paper_list，`download_paper()` 下载 + 双后端解析
3. **Step 3** — `summarize_single_paper()` 单次 LLM 调用生成摘要
4. **Step 4** — `make_repo_agent()` 搜索 + 克隆 + 摘要代码仓库
5. **Step 4a** — Agent 生成 `eda_guide.md`
6. **Step 4b** — `DataAgent` 下载数据 → EDA 脚本 → VLM 分析
7. **Step 5** — Agent 综合所有材料 → 写 survey.md 等

### 输出
- `survey/paper_list.yaml`、`survey/papers/summaries/*.md`
- `survey.md`、`baselines.md`、`datasets.md`、`metrics.md`、`leaderboard.md`
- `knowledge/repos/*/SUMMARY.md`、`knowledge/eda/eda_report.md`

### 依赖关系
- **上游**：F01（CLI）、F02（Orchestrator）、F07（context.md）
- **下游**：F06（ideation）、F07（refine）

### 错误与边界情况
- PDF 下载失败：标记 failed，跳过
- Zhipu 解析失败：fallback MinerU
- Rate limit：polite pool 0.15s，semantic 1s
- 论文去重：基于 paper_id

## 测试方法
```bash
python run_research.py survey --topic T001
python run_research.py survey --topic T001 --step 4
```

## 建议
（暂无）

## 变化
### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
<details><summary>详情</summary>

**计划**：实现 5 步文献调研流水线
**代码修改**：新增 survey_helpers.py + openalex.py + paper_manager.py + data_agent.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|

</details>
