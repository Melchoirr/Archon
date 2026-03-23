# [F06] Idea 生成与评分

## 状态
- **实现状态**：✅已完成

## 核心文件
- `agents/ideation_agent.py:79-108` — `IdeationAgent.__init__(topic_dir)`，10 个工具，20 次迭代，`partial` 绑定 topic_dir 到 idea_graph 工具
- `agents/ideation_agent.py:110-144` — `build_prompt()`，组装 ideation prompt
- `agents/ideation_agent.py:19-75` — system prompt（3+ 搜索/idea、去重、原子性、≥800 字符）
- `tools/idea_scorer.py:62-88` — `extract_search_queries()`，LLM 提取搜索查询
- `tools/idea_scorer.py:89-119` — `search_prior_work()`，去重论文搜索
- `tools/idea_scorer.py:121-175` — `_compute_embedding_similarity()`，embedding 相似度检测
- `tools/idea_scorer.py:177-281` — `score_idea()`，LLM 4 维评分
- `tools/idea_scorer.py:331-428` — `score_all_ideas()`，批量评分 + 排名
- `tools/idea_graph.py:27-54` — `add_idea_relationship()`，idea 关系记录
- `tools/idea_graph.py:55-77` — `get_idea_graph()`，关系图渲染

## 功能描述
两阶段 Idea 管理：生成 + 评分。

**Idea 生成**（IdeationAgent）：
- 阅读全部调研材料 → ReAct 循环（≥3 次搜索/idea）
- 每个 idea 写 `proposal.md`（≥800 字符）→ `add_idea_to_tree()` + `add_idea_relationship()`
- 原子性：1 核心创新/idea

**Idea 评分**（score_all_ideas）：
- 查重：LLM 提取搜索查询 → OpenAlex 搜索 → embedding 相似度（≥0.85 高相似，≥0.75 中相似）
- LLM 4 维评分：Novelty(0.35) + Significance(0.35) + Feasibility(0.20) + Alignment(0.10)
- 排名 + 写 review.md → 更新研究树 scores + status

**关系图**：4 种关系（builds_on, alternative_to, complementary, combines_with）+ `suggest_combinations()`

## 运行流程

### 触发条件
- `python run_research.py ideation --topic T001`
- FSM topic_state == "ideation"

### 处理步骤
1. **上下文组装** — 收集 survey 产物
2. **Idea 生成** — IdeationAgent ReAct 循环，写 proposal.md + 注册研究树
3. **评分流水线** — 对每个 idea：搜索查询提取 → 查重 → embedding 相似度 → LLM 评分
4. **排名 + 状态更新** — composite 分降序排名，≥3.5 recommended，<3.5 deprioritized

### 输出
- `ideas/IXXX_shortname/proposal.md` + `review.md`
- `idea_graph.yaml`
- 研究树 scores + status 更新

### 依赖关系
- **上游**：F05（survey 产物）、F11（context_manager）
- **下游**：F07（refine 处理 recommended ideas）

### 错误与边界情况
- 高相似度（≥0.85）：Novelty 低分
- 无 ZHIPU_API_KEY：跳过 embedding 检测
- OpenAlex 无结果：仍进行 LLM 评分

## 测试方法
```bash
python run_research.py ideation --topic T001
python run_research.py status --topic T001
```

## 建议
（暂无）

## 变化
### [修复] 2026-03-23 22:15 — idea_graph 绑定 topic_dir (`d081a7c`)
- **目的**：修复 idea_graph 工具的 topic_dir 默认值为 "."，导致 idea_graph.yaml 写到项目根目录而非 topic 目录
- **改动**：IdeationAgent 新增 topic_dir 参数，用 `functools.partial` 绑定 `add_idea_relationship` 和 `get_idea_graph` 的 topic_dir；orchestrator.py 传入 `self.topic_dir`
- **验证**：未测试

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
- **目的**：实现 Idea 生成 + 多维评分 + 关系图
- **改动**：新增 ideation_agent.py + idea_scorer.py + idea_graph.py
- **验证**：未测试
