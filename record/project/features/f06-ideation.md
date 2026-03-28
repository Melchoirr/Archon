# [F06] Idea 生成与评分

## 状态
- **实现状态**：✅已完成

## 核心文件
- `agents/ideation_agent.py:80-109` — `IdeationAgent.__init__(topic_dir)`，11 个工具（含 check_local_knowledge），40 次迭代，`partial` 绑定 topic_dir 到 idea_graph 工具
- `agents/ideation_agent.py:111-155` — `build_prompt()`，组装 ideation prompt（含最低 3 个 idea 要求）
- `agents/ideation_agent.py:21-77` — system prompt（3+ 搜索/idea、去重、原子性、≥800 字符、≥3 idea 数量要求、注册要求强调）
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
### [修复] 2026-03-28 11:00 — idea_scorer 兼容 ThinkingBlock 响应 (`2905565`)
- **目的**：LLM 响应含 ThinkingBlock 时 `resp.content[0].text` 报 AttributeError，导致评分整体失败
- **改动**：`tools/idea_scorer.py` — 新增 `_extract_text(resp)` 辅助函数，遍历 `resp.content` 找第一个有 `.text` 属性的 block；替换全部 3 处 `resp.content[0].text` 调用
- **验证**：import 通过

### [修复] 2026-03-28 00:57 — IdeationAgent 迭代不足+idea 未注册导致评分跳过 (`b8e512e`)
- **目的**：修复 ideation 阶段只生成 1 个 idea 且评分被跳过的问题：(1) max_iterations=20 太少，每个 idea 需 ~5 轮，只够 2-3 个；(2) system prompt 无最低数量要求；(3) LLM 写了 proposal.md 但没调 add_idea 注册，导致 registry 为空评分跳过
- **改动**：
  - `agents/ideation_agent.py` — max_iterations 20→40；system prompt 新增「数量要求」（≥3 个）和「注册要求」（write_file+add_idea 成对）；build_prompt 强化数量和注册指令
  - `agents/orchestrator.py` — 新增 `_backfill_unregistered_ideas()` 兜底方法，评分前扫描 ideas 目录，自动补注册有 proposal.md 但未在 registry 中的 idea
- **验证**：import 通过

### [修改] 2026-03-25 19:42 — IdeationAgent 注册 check_local_knowledge 工具 (`eeb0585`)
- **目的**：Idea 生成时可预检本地知识库已有资源，避免搜索/引用重复内容
- **改动**：`agents/ideation_agent.py` 新增 import 和 register_tool
- **验证**：import 通过

### [修复] 2026-03-23 22:15 — idea_graph 绑定 topic_dir (`d081a7c`)
- **目的**：修复 idea_graph 工具的 topic_dir 默认值为 "."，导致 idea_graph.yaml 写到项目根目录而非 topic 目录
- **改动**：IdeationAgent 新增 topic_dir 参数，用 `functools.partial` 绑定 `add_idea_relationship` 和 `get_idea_graph` 的 topic_dir；orchestrator.py 传入 `self.topic_dir`
- **验证**：未测试

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
- **目的**：实现 Idea 生成 + 多维评分 + 关系图
- **改动**：新增 ideation_agent.py + idea_scorer.py + idea_graph.py
- **验证**：未测试
