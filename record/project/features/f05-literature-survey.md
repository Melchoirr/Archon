# [F05] 文献调研管道

## 状态
- **实现状态**：✅已完成

## 核心文件
- `agents/survey_helpers.py:32-152` — 搜索策略 prompt（4 阶段搜索）
- `agents/survey_helpers.py:199-227` — `make_search_agent()`，搜索 Agent 工厂（10 个工具，含 check_local_knowledge）
- `agents/survey_helpers.py:344-389` — `summarize_single_paper()`，单篇摘要（单次 LLM）
- `agents/survey_helpers.py:447-484` — `build_repo_prompt()` / `make_repo_agent()`，Repo 研究 Agent 工厂
- `tools/openalex.py:230-260` — `search_topics()`，OpenAlex topic 搜索
- `tools/openalex.py:261-345` — `search_papers()`，论文搜索（keyword/semantic/exact）
- `tools/openalex.py:347-403` — `get_paper_references()` / `get_paper_citations()`，引用图遍历
- `tools/paper_manager.py:172-273` — `_parse_pdf_zhipu()` / `_parse_pdf_mineru()`，PDF 双后端解析
- `tools/paper_manager.py:320-390` — `download_paper()`，论文下载 + 解析
- `tools/paper_manager.py:360-465` — `read_paper_section()`，论文分段阅读（模糊匹配）
- `agents/data_agent.py:84-154` — `DataAgent`，数据下载 + EDA（10 个工具含 check_local_knowledge/register_dataset，35 次迭代）

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
- 论文去重：基于 paper_id（download_paper 内置检查）+ check_local_knowledge 预检

## 测试方法
```bash
python run_research.py survey --topic T001
python run_research.py survey --topic T001 --step 4
```

## 建议
（暂无）

## 变化
### [实现] 2026-03-26 23:21 — DataAgent 支持 dataset card 生成 + 下载/仅记录双模式 (`38ea72f`)
- **目的**：所有数据集都需要 dataset card 供下游 agent 参考；大规模/需申请的数据集不应强制下载
- **改动**：`data_agent.py` prompt 重写 Phase 0/1 加入策略判断（downloaded vs card_only）、所有数据集必须 register_dataset；新增 `dataset_cards_dir` 参数；`orchestrator.py` 传入 dataset_cards_dir 到 DataAgent + allowed_dirs
- **验证**：register_dataset 两种模式测试通过，card 文件正确生成

### [重构] 2026-03-26 17:14 — DataAgent 增加数据集预检/注册 + check_local_knowledge 迁移 (`2db43ea`)
- **目的**：DataAgent 用 wget 直接下载无预检，数据集无索引无去重；check_local_knowledge 从 paper_manager 迁移到 knowledge_index
- **改动**：`data_agent.py` 新增 check_local_knowledge/register_dataset 工具注册，system prompt 增加 Phase 0 预检步骤和 Phase 1 注册步骤；`survey_helpers.py` import 改为 `from tools.knowledge_index import check_local_knowledge`
- **验证**：`python -c 'from agents.data_agent import DataAgent; from agents.survey_helpers import make_search_agent'` 通过

### [修改] 2026-03-26 10:18 — MinerU fallback 切换到 pipeline 轻量模式 (`d4e0e0a`)
- **目的**：MinerU 默认 hybrid-auto-engine 后端解析 23 页 PDF 需 26 分钟，不可用。切换到 pipeline 模式 + 关闭公式/表格解析，耗时降至 ~1 分钟
- **改动**：`tools/paper_manager.py` `_parse_pdf_mineru()` 命令行增加 `-f false -t false` 关闭公式/表格解析；超时从 600s 缩短到 180s
- **验证**：`mineru -b pipeline -m txt -d mps -f false -t false` 实测 8.4M/23 页 PDF 耗时 63 秒，输出 markdown 质量良好

### [实现] 2026-03-25 19:42 — 新增 check_local_knowledge 预检工具 (`eeb0585`)
- **目的**：让 Agent 在决策阶段就能查询本地是否已有论文/总结/代码库，避免重复下载
- **改动**：`tools/paper_manager.py` 新增 `check_local_knowledge()` 函数，检查 index.yaml + summaries + repos；`agents/survey_helpers.py` 在 3 处 Agent 工厂注册该工具
- **验证**：`check_local_knowledge("sundial")` 返回论文+总结匹配，`check_local_knowledge("chronos", resource_type="repo")` 返回代码库匹配，空查询返回"可以下载"

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
- **目的**：实现 5 步文献调研流水线
- **改动**：新增 survey_helpers.py + openalex.py + paper_manager.py + data_agent.py
- **验证**：未测试
