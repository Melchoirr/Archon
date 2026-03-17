# Archon — AI 驱动的端到端科研自动化系统

## 第一部分：项目概述与设计理念

### 1.1 系统定位

Archon 是一个 **AI 驱动的端到端科研自动化系统**，专注于时序预测领域的学术研究。它将科研过程抽象为 10 个可编排的阶段，由多个专用 Agent 协作完成从课题定义到论文结论的全链路自动化。

### 1.2 核心设计思想

**多 Agent 协作**：系统采用"编排器 + 专用 Agent"架构。`ResearchOrchestrator` 作为中央编排器，根据研究阶段派发任务给 10 个专用 Agent（ElaborateAgent、LiteratureAgent、IdeationAgent 等）。每个 Agent 只关注自己的领域，通过工具注册机制获得所需能力。

**ReAct 推理循环**：所有 Agent 继承自 `BaseAgent`，采用 ReAct（Reasoning + Acting）循环模式 — 推理→调用工具→观察结果→继续推理，直到任务完成或达到最大迭代次数。这使 Agent 能自主决策调用什么工具、按什么顺序操作。

**知识积累**：系统通过三个机制持续积累知识：
- **智谱知识库**（`KnowledgeBaseManager`）：每阶段产出物自动上传到云端向量知识库，后续阶段可检索
- **经验日志**（`memory/experience_log.yaml`）：记录关键发现和教训，避免重复犯错
- **研究树**（`research_tree.yaml`）：树状结构追踪所有 idea 的状态和实验进展

### 1.3 技术栈

| 组件 | 技术选型 | 说明 |
|------|---------|------|
| LLM | MiniMax M2.5 | 通过 Anthropic 兼容接口调用，200K context |
| LLM SDK | `anthropic` Python SDK | MiniMax 提供 Anthropic 协议兼容的 API |
| 学术搜索 | OpenAlex API | 免费开放，2.71 亿篇论文，CC0 许可 |
| PDF 解析 | 智谱 API（优先）+ MinerU（fallback） | 双后端策略，确保解析成功率 |
| 知识库 | 智谱知识库 API | Embedding-3-pro 向量检索，支持混合召回 |
| 代码编写 | Claude Code（`claude -p`） | 通过子进程调用，实现模块级代码生成 |
| Web 搜索 | DuckDuckGo | 补充最新信息和代码仓库搜索 |
| VLM | MiniMax M2.5（多模态） | 分析实验结果可视化图表 |

---

## 第二部分：系统架构总览

### 2.1 三层架构

```
┌─────────────────────────────────────────────────┐
│                   入口层                          │
│  run_research.py (CLI)                           │
│  命令: init/elaborate/survey/ideation/...        │
├─────────────────────────────────────────────────┤
│                   编排层                          │
│  ResearchOrchestrator                            │
│  - 阶段流转控制                                   │
│  - 上下文组装 (ContextManager)                    │
│  - 知识库管理 (KnowledgeBaseManager)              │
│  - 研究树维护                                     │
│  - 阶段日志记录                                   │
├─────────────────────────────────────────────────┤
│                   执行层                          │
│  ┌──────────┬──────────┬──────────┬───────────┐  │
│  │Elaborate │Literature│Ideation  │Refinement │  │
│  │Agent     │Agent     │Agent     │Agent      │  │
│  ├──────────┼──────────┼──────────┼───────────┤  │
│  │Design    │Experiment│Analysis  │Conclusion │  │
│  │Agent     │Agent     │Agent     │Agent      │  │
│  ├──────────┼──────────┼──────────┼───────────┤  │
│  │Data      │Survey Helper Agents (x3)        │  │
│  │Agent     │Search / Repo / Synthesis        │  │
│  └──────────┴──────────────────────────────────┘  │
│                                                   │
│  工具层 (16 个模块)                                │
│  openalex / paper_manager / knowledge_base /      │
│  context_manager / research_tree / idea_scorer /  │
│  vlm_analysis / claude_code / bash_exec / ...     │
└─────────────────────────────────────────────────┘
```

### 2.2 数据流

```
Topic MD --> init --> topic 目录结构
               |
          elaborate --> context.md
               |
          survey (5步流水线) --> survey/*.md + baselines.md + datasets.md + metrics.md
               |
          ideation --> ideas/I001_xxx/proposal.md + review.md (评分)
               |
          refine --> refinement/{theory,model_modular,model_complete}.md + experiment_plan.md
               |
          code-ref --> 参考代码仓库 clone + 摘要
               |
          code --> src/{model/,experiment/} + structure.md
               |
          experiment --> results/S01_xxx/V1/{metrics,logs,plots}
               |  (可迭代 V2, V3...)
          analyze --> analysis.md
               |
          conclude --> conclusion.md + memory 经验记录
```

### 2.3 目录结构

```
self/
├── run_research.py          # CLI 入口
├── agents/                  # Agent 层
│   ├── base_agent.py        # BaseAgent (ReAct 循环)
│   ├── orchestrator.py      # 编排器
│   ├── elaborate_agent.py   # 背景展开
│   ├── literature_agent.py  # 文献调研
│   ├── survey_helpers.py    # Survey 子 Agent 工厂
│   ├── data_agent.py        # 数据集管理
│   ├── ideation_agent.py    # Idea 生成
│   ├── refinement_agent.py  # 方案细化
│   ├── design_agent.py      # 方案设计
│   ├── experiment_agent.py  # 代码编写/实验执行
│   ├── analysis_agent.py    # 结果分析
│   └── conclusion_agent.py  # 结论总结
├── tools/                   # 工具层 (16 模块)
│   ├── openalex.py          # OpenAlex 学术搜索
│   ├── paper_manager.py     # 论文下载/解析/索引
│   ├── knowledge_base.py    # 智谱知识库
│   ├── context_manager.py   # 上下文注入
│   ├── research_tree.py     # 研究树 CRUD
│   ├── idea_scorer.py       # Idea 评分
│   ├── idea_graph.py        # Idea 关系图
│   ├── vlm_analysis.py      # VLM 图片分析
│   ├── claude_code.py       # Claude Code 子进程调用
│   ├── phase_logger.py      # 阶段日志
│   ├── file_ops.py          # 文件操作
│   ├── bash_exec.py         # Shell 命令执行
│   ├── web_search.py        # DuckDuckGo 搜索
│   ├── github_repo.py       # GitHub 仓库管理
│   ├── memory.py            # 经验记忆
│   └── config_updater.py    # 配置更新
├── shared/utils/            # 共享工具
│   └── config_helpers.py    # 配置加载
├── knowledge/               # 全局知识
│   ├── papers/{pdf,parsed,summaries}
│   ├── repos/
│   └── dataset_cards/
├── memory/                  # 经验系统
│   ├── experience_log.yaml
│   ├── insights.md
│   └── failed_ideas.md
└── topics/                  # 课题目录
    └── T001_mean_reversion/
        ├── config.yaml
        ├── topic_spec.md
        ├── context.md
        ├── research_tree.yaml
        ├── survey/
        ├── ideas/
        └── phase_logs/
```

---

## 第三部分：研究流水线（10 阶段）

### 3.1 init — 项目初始化

```bash
python run_research.py init --topic mean_reversion.md
```

**输入**：`topics/` 下的 Markdown 课题描述文件（含标题、领域、关键词、描述、范围）

**处理**：
1. 创建全局目录结构（`knowledge/`, `memory/`, `shared/`）
2. 解析 MD 文件提取结构化信息（`_parse_topic_md`）
3. 分配 Topic 编号（T001, T002...）
4. 生成 `config.yaml`（LLM、搜索、环境配置）
5. 初始化 `research_tree.yaml`
6. 验证环境（API key、依赖库、LLM 连通性）

**产出**：`topics/T001_mean_reversion/` 目录，含 `config.yaml`、`topic_spec.md`、`research_tree.yaml`

### 3.2 elaborate — 背景展开

```bash
python run_research.py elaborate --topic T001
```

**输入**：`topic_spec.md`（用户原始课题描述）

**处理**：`ElaborateAgent` 以原始描述为线索，自主探索问题空间，生成更全面深入的研究背景文档。明确告知 Agent "不要局限于上述描述的方向"。

**产出**：`context.md` — 后续所有阶段的基础上下文

### 3.3 survey — 文献调研（5 步流水线）

```bash
python run_research.py survey --round 1 --step 1
```

这是系统中最复杂的阶段，采用 **5 步流水线** 设计，支持断点恢复（通过 `progress.yaml` 追踪状态）：

| 步骤 | 名称 | Agent | 处理方式 | 产出 |
|------|------|-------|---------|------|
| Step 1 | 搜索论文 | 论文搜索 Agent | 按关键词在 OpenAlex 搜索 + 引用链展开 | `paper_list.yaml` |
| Step 2+3 | 下载+总结 | 确定性并行 | 多线程并行下载 PDF → 智谱/MinerU 解析 → LLM 单次调用总结 | `knowledge/papers/summaries/*.md` |
| Step 4 | 代码仓库 | 代码仓库 Agent | 搜索论文对应的 GitHub 仓库，clone 并摘要 | `repos_summary.md` |
| Step 5 | 综合整理 | 综合整理 Agent | 读取所有总结，生成综述和推荐 | `survey.md`, `leaderboard.md`, `baselines.md`, `datasets.md`, `metrics.md` |

后处理：
- 更新全局论文索引（`index.yaml`）
- `DataAgent` 自动下载推荐数据集并生成 dataset cards
- 更新 `config.yaml` 中的数据集信息

**设计亮点**：Step 2+3 采用**确定性并行**而非 Agent 循环 — 直接多线程处理每篇论文（下载→解析→总结），避免 Agent 循环的不确定性。每 3 篇保存一次进度，崩溃安全。

### 3.4 ideation — Idea 生成

```bash
python run_research.py ideation --topic T001
```

**输入**：`context.md` + `survey.md` + `baselines.md` + `datasets.md` + `metrics.md` + `failed_ideas.md`

**处理**：`IdeationAgent` 执行 ReAct 循环：
1. Think — 基于 survey gap 思考方向
2. Search（至少 3 次） — `search_papers` + `web_search` 验证新颖性
3. Refine — 根据搜索结果调整
4. Generate — 写入 `proposal.md`

**约束**：
- 去重检查（`read_tree` + `list_directory`）
- 原子性约束：每个 idea 只允许一个核心创新点
- 用 `add_idea_relationship` 记录 idea 间关系（互补/替代/组合）

**后处理**：`idea_scorer.py` 自动评分 — 对每个 idea 提取搜索查询 → 检索相关工作 → LLM 结构化评分（Novelty 0.35 + Significance 0.35 + Feasibility 0.20 + Alignment 0.10），生成 `review.md` 和排名。

**产出**：`ideas/I001_xxx/proposal.md` + `review.md`，研究树中注册并评分

### 3.5 refine — 方案细化

```bash
python run_research.py refine --idea T001-I001
```

**输入**：`proposal.md` + `survey.md`（通过 ContextManager 注入）

**处理**：`RefinementAgent` 将 idea 展开为完整技术方案

**产出**（3 份文档 + 1 份计划）：
- `refinement/theory.md` — 数学形式化定义、理论推导、收敛性分析
- `refinement/model_modular.md` — 创新/沿用部分分离的模块化设计
- `refinement/model_complete.md` — 端到端完整模型描述、数据流图
- `experiment_plan.md` — 分步实验计划，含预期结果数值范围

**支持并行**：`--idea T001` 可并行 refine 该 topic 下所有 idea

### 3.6 code-ref — 代码参考获取

```bash
python run_research.py code-ref --idea T001-I001
```

**输入**：`refinement/theory.md` + `refinement/model_modular.md`

**处理**：`LiteratureAgent` 搜索相关论文的 GitHub 仓库 → `clone_repo` → `summarize_repo`

**产出**：`knowledge/repos/` 下的参考代码仓库及摘要

### 3.7 code — 代码编写

```bash
python run_research.py code --idea T001-I001
```

**输入**：`refinement/*.md` + `experiment_plan.md` + 参考代码仓库

**处理**：`ExperimentAgent` 采用**项目经理模式** — 自己拆解任务，通过 `claude_write_module` 调用 Claude Code 逐模块编写代码。流程：
1. 读取设计方案 → 理解要实现什么
2. 生成 `src/structure.md` → 记录代码结构
3. 逐模块调用 `claude_write_module` → 每次一个文件
4. `run_command` 运行测试 → `claude_fix_error` 修复错误
5. `claude_review` 审查关键代码

**产出**：`ideas/I001_xxx/src/` 目录下的完整实现代码

### 3.8 experiment — 实验运行

```bash
python run_research.py experiment --idea T001-I001 --max-iter 3
```

**输入**：代码 + `experiment_plan.md`

**处理**：支持两种模式：
- 单次运行：指定 `--step S01 --version V1`
- 迭代循环：`--max-iter 3` 自动执行 V1→分析→调整→V2→分析→调整→V3

每次实验后，`AnalysisAgent` 分析结果并生成下一版本的调整建议（`config_diff`）。

**产出**：`results/S01_quick_test/V1/` 下的指标、日志、图表

### 3.9 analyze — 结果分析

```bash
python run_research.py analyze --idea T001-I001
```

**输入**：`experiment_plan.md`（预期结果）+ `results/`（实际结果）

**处理**：`AnalysisAgent` 进行多维分析：
- 逐步逐版本定量分析
- 预期 vs 实际对比
- VLM 分析实验图表（`analyze_image`）
- 跨版本趋势分析

**产出**：`analysis.md` — 综合分析报告，含决策建议（继续/调整/放弃/发表）

### 3.10 conclude — 结论总结

```bash
python run_research.py conclude --idea T001-I001
```

**输入**：idea 全链路文档（proposal → refinement → code → results → analysis）

**处理**：`ConclusionAgent` 进行**完全客观**的总结 — 不美化结果、不回避失败

**产出**：`conclusion.md`（设计评估、实现评估、结果总结、意外发现、经验教训）+ 经验写入 memory

### 补充：auto 模式

```bash
python run_research.py auto --idea T001-I001 --start refine --max-iter 3
```

自动串联 refine → code-ref → code → experiment_loop → analyze → conclude，一键执行 idea 的全流程。

---

## 第四部分：Agent 体系设计

### 4.1 BaseAgent ReAct 循环

`BaseAgent`（`agents/base_agent.py`）是所有 Agent 的基类，实现核心 ReAct 循环：

```python
class BaseAgent:
    def __init__(self, name, system_prompt, tools=[], max_iterations=20):
        self.client = anthropic.Anthropic(api_key=..., base_url=...)  # MiniMax
        self.model = "MiniMax-M2.5"
        self.tools = []
        self.tool_handlers = {}
        # 自动注册全局知识库搜索工具
        self.register_tool("search_knowledge_base", ...)

    def run(self, user_prompt) -> str:
        for i in range(max_iterations):
            self._compress_messages()       # 压缩过长历史
            response = llm_call_with_retry(...)  # 带重试的 LLM 调用
            # 解析 response -> text_parts + tool_uses
            if not tool_uses:
                return text  # 无工具调用 -> 完成
            # 执行工具（多工具并行）
            for tool_use in tool_uses:
                result = self.tool_handlers[tool_use.name](**tool_use.input)
            # 注入剩余轮次警告（<=5 轮时）
```

**关键机制**：

1. **工具注册**：`register_tool(name, handler, schema)` — 每个 Agent 按需注册工具，tool schema 直接传给 LLM 的 function calling

2. **消息压缩**：当历史消息超过 150K 字符（~37K tokens）时，保留首条 + 最近 12 条消息，中间部分压缩为工具调用摘要。充分利用 MiniMax M2.5 的 200K context。

3. **重试策略**：`llm_call_with_retry` — 对 APIConnectionError、RateLimitError、InternalServerError 进行指数退避重试（2s → 4s → 8s），最多 3 次。

4. **并行工具执行**：单轮多个工具调用时，使用 `ThreadPoolExecutor` 并行执行。

5. **紧迫性提示**：剩余 <=5 轮时注入系统提示，<=2 轮时加警告，确保 Agent 在迭代限制内完成工作。

### 4.2 专用 Agent 一览

| Agent | 文件 | max_iter | 核心工具 | 职责 |
|-------|------|----------|---------|------|
| ElaborateAgent | elaborate_agent.py | 20 | file_ops, web_search, search_papers | 展开课题背景 |
| LiteratureAgent | literature_agent.py | 40 | openalex, paper_manager, github_repo, web_search | 文献调研（完整版） |
| 论文搜索 Agent | survey_helpers.py | 20 | openalex, web_search, paper_index | Survey Step 1: 搜索论文列表 |
| 代码仓库 Agent | survey_helpers.py | 10 | github_repo, web_search | Survey Step 4: 仓库调研 |
| 综合整理 Agent | survey_helpers.py | 8 | file_ops | Survey Step 5: 生成综述 |
| DataAgent | data_agent.py | 15 | file_ops, bash_exec, config_updater | 数据集下载和准备 |
| IdeationAgent | ideation_agent.py | 25 | file_ops, research_tree, memory, openalex, web_search, idea_graph | Idea 生成与去重 |
| RefinementAgent | refinement_agent.py | 25 | file_ops, research_tree, memory, openalex, paper_manager | 方案细化 |
| DesignAgent | design_agent.py | 20 | file_ops, research_tree, memory, openalex | 方案设计（备用） |
| ExperimentAgent | experiment_agent.py | 30 | file_ops, bash_exec, research_tree, memory, claude_code, repos | 代码编写和实验 |
| AnalysisAgent | analysis_agent.py | 25 | file_ops, research_tree, memory, vlm_analysis | 结果分析 |
| ConclusionAgent | conclusion_agent.py | 20 | file_ops, memory | 结论总结 |

**所有 Agent 自动继承一个全局工具**：`search_knowledge_base` — 可随时检索知识库中的历史产出。

### 4.3 Survey 流水线的混合策略

Survey 阶段是"Agent 循环 + 确定性并行"的混合设计：
- Step 1（搜索）和 Step 4（仓库）、Step 5（综合）使用 Agent 循环 — 需要自主决策
- Step 2+3（下载+总结）使用确定性并行 — 每篇论文独立流水线，`ThreadPoolExecutor` 3 路并发

单篇论文总结使用 `summarize_single_paper`（`survey_helpers.py`）— 单次 LLM 调用，无工具循环，`max_tokens=16384`，确保深度分析。区分全文总结和摘要总结两个模板。

---

## 第五部分：工具层详解

### 5.1 工具模块一览（16 个）

| 模块 | 文件 | 核心功能 |
|------|------|---------|
| **OpenAlex** | `openalex.py` | 学术论文搜索、引用/被引查询 |
| **Paper Manager** | `paper_manager.py` | PDF 下载、解析（智谱/MinerU）、章节阅读、全局索引 |
| **Knowledge Base** | `knowledge_base.py` | 智谱知识库 CRUD + 向量检索 |
| **Context Manager** | `context_manager.py` | 按阶段规则自动组装上下文 |
| **Research Tree** | `research_tree.py` | 研究树状态管理、编号分配、实验迭代追踪 |
| **Idea Scorer** | `idea_scorer.py` | LLM 驱动的 idea 评分（检索+评审） |
| **Idea Graph** | `idea_graph.py` | Idea 关系图记录与可视化 |
| **VLM Analysis** | `vlm_analysis.py` | 多模态图片分析（实验图表） |
| **Claude Code** | `claude_code.py` | 调用 `claude -p` 子进程编写/修复/审查代码 |
| **Phase Logger** | `phase_logger.py` | 阶段前后状态快照 + 知识库自动上传 |
| **File Ops** | `file_ops.py` | 文件读写、目录列表 |
| **Bash Exec** | `bash_exec.py` | Shell 命令执行 |
| **Web Search** | `web_search.py` | DuckDuckGo 网页搜索 |
| **GitHub Repo** | `github_repo.py` | 仓库 clone、摘要、列表 |
| **Memory** | `memory.py` | 经验查询和记录 |
| **Config Updater** | `config_updater.py` | YAML 配置动态更新 |

### 5.2 关键设计详解

#### OpenAlex（`openalex.py`）

替代 Semantic Scholar 的学术搜索后端。关键设计：
- **Polite pool**：通过 `mailto` 参数获得 10 req/s 速率
- **限流**：全局 `_rate_limit()` 确保请求间隔 >=150ms
- **指数退避重试**：429/网络错误自动重试 3 次
- **格式标准化**：`_normalize_work()` 将 OpenAlex 返回格式转为与 S2 兼容的统一格式（paperId, title, citationCount, externalIds 等）
- **ArXiv ID 提取**：三种策略依次尝试（DOI、locations、primary_location）
- **失败 fallback 提示**：3 次重试后，错误信息建议 Agent 改用 `web_search` 搜索 arxiv.org

提供 3 个核心函数：`search_papers`（关键词搜索，支持引用数/年份过滤）、`get_paper_references`（参考文献）、`get_paper_citations`（被引论文）。

#### Paper Manager（`paper_manager.py`）

论文全生命周期管理：
- **双后端 PDF 解析**：`PARSE_BACKEND` 环境变量控制，默认智谱 API（异步轮询，最多 3 分钟），失败自动 fallback 到 MinerU
- **线程安全索引**：`_index_lock`（`threading.Lock`）保护 `index.yaml` 的并发读写，`_update_index` 实现原子更新
- **章节级阅读**：`read_paper_section` 支持模糊匹配（别名映射 + `SequenceMatcher`）和关键词搜索，截断到 3000 字符
- **批量处理**：`batch_download_papers` 支持批量下载，间隔 2s 避免 429
- **全局索引**：`search_paper_index` 支持按关键词/topic 搜索已有论文，避免重复调研

#### Knowledge Base（`knowledge_base.py`）

基于智谱 API 的向量知识库：
- **单一全局库设计**：所有产出物存入 `archon_research` 知识库，通过 `scope` 参数按文件名前缀过滤
- **幂等创建**：`get_or_create_kb` 先查后建
- **去重上传**：`skip_if_exists` 按文件名检查
- **混合召回**：`retrieve` 支持 embedding / keyword / mixed 三种模式
- **Agent 全局可用**：`search_knowledge_base` 在 `BaseAgent.__init__` 中自动注册

#### Context Manager（`context_manager.py`）

每阶段自动注入必需上下文的核心组件。三层规则表驱动：

```python
PHASE_CONTEXT_RULES   # topic 级文件（如 survey 阶段注入 context.md）
IDEA_CONTEXT_RULES    # idea 级文件（如 refine 阶段注入 proposal.md）
GLOBAL_CONTEXT_RULES  # 全局文件（如 ideation 阶段注入 failed_ideas.md）
```

`build_context(phase, idea_id, ref_ideas, ref_topics)` 按 5 层优先级组装：
1. Topic 级文件
2. Idea 级文件
3. 全局文件
4. 跨 Idea 引用（支持 `T001-I001` 精确引用和 `T001` 全 topic 引用）
5. 跨 Topic 引用

文件截断到 40K 字符/个，总上下文截断到 60K 字符。

#### Research Tree（`research_tree.py`）

YAML 格式的树状研究状态追踪：
- **三级编号**：Topic（T001）-> Idea（I001）-> Step（S01）
- **实验迭代追踪**：每个 Step 下有 V1/V2/V3 迭代，`update_iteration` 更新状态并自动判断 Step 完成
- **Idea 评分**：`update_idea_scores` 存储 novelty/significance/feasibility/alignment/composite/rank
- **路径自动解析**：`_resolve_tree_path` 支持从 idea 子目录向上查找 tree 文件

#### Phase Logger（`phase_logger.py`）

阶段前后自动快照 + 知识库同步：
- `log_phase_start`：记录研究树状态和 idea 文件列表
- `log_phase_end`：收集新产出文件 → 上传到知识库
- **智能命名**：`derive_display_name` 将本地路径转为扁平命名（如 `topics/T001_.../ideas/I001_.../refinement/theory.md` → `T001_I001_refinement_theory`）
- **Session 级去重**：`_uploaded_artifact_set` 避免同一文件重复上传

#### Idea Scorer（`idea_scorer.py`）

三步评分流程：
1. **提取查询**：LLM 从 proposal 提取 2-3 个验证新颖性的英文搜索查询
2. **文献检索**：对每个查询调用 `search_papers`（2022 年后），去重合并
3. **结构化评分**：LLM 按 Novelty(0.35) + Significance(0.35) + Feasibility(0.20) + Alignment(0.10) 评分

评分结果写入 `review.md`，更新 research_tree，composite >= 3.5 标记为 recommended，< 2.5 标记为 deprioritized。

---

## 第六部分：数据模型与持久化

### 6.1 research_tree.yaml

```yaml
root:
  topic_id: T001
  topic_brief: mean_reversion
  topic: "时间序列预测中的均值回归特性建模与利用"
  description: "..."
  status: initialized  # initialized -> surveyed -> ideating -> experimenting -> concluded
  elaborate:
    status: completed
  survey:
    rounds: 1
    status: completed
  ideas:
    - id: I001
      brief: adaptive_mr
      title: "自适应均值回归强度估计器"
      category: architecture
      status: recommended  # proposed -> recommended -> refining -> coding -> experimenting -> concluded / deprioritized
      created_at: "2026-03-10T14:30:00"
      scores:
        novelty: 4
        significance: 4
        feasibility: 3
        alignment: 5
        composite: 3.95
        rank: 1
      phases:
        refinement: completed
        code_reference: completed
        coding: completed
        experiment: completed
        analysis: completed
        conclusion: completed
      relationships:
        - target: I002
          type: complementary
      experiment_steps:
        - step_id: S01
          name: quick_test
          status: completed
          max_iter: 3
          iterations:
            - version: 1
              status: completed
              config_diff: null
            - version: 2
              status: completed
              config_diff: "lr: 0.001 -> 0.0005"
```

### 6.2 论文索引（`knowledge/papers/index.yaml`）

```yaml
W2741809807:
  title: "Autoformer: Decomposition Transformers..."
  pdf_path: knowledge/papers/pdf/W2741809807.pdf
  md_path: knowledge/papers/parsed/W2741809807.md
  sections: [Introduction, Method, Experiments, ...]
  topics: [T001]
```

线程安全（`_index_lock`），支持按 paper_id 或标题关键词搜索。

### 6.3 论文列表（`survey/paper_list.yaml`）

```yaml
papers:
  - paper_id: "W2741809807"
    title: "Autoformer: ..."
    year: 2021
    citation_count: 4114
    arxiv_id: "2106.13008"
    venue: "NeurIPS"
    authors: ["Haixu Wu"]
    open_access_url: "https://..."
    relevance: "时序分解+自相关机制"
    download_status: downloaded  # pending -> downloaded / no_access / no_source / failed
    summary_status: done         # pending -> done / skipped / failed
```

### 6.4 经验日志（`memory/experience_log.yaml`）

```yaml
- timestamp: "2026-03-10T15:00:00"
  phase: survey
  type: insight
  idea_id: ""
  topic_id: T001
  summary: "Survey 流水线完成，共处理 25 篇论文"
  tags: [survey, pipeline]
```

通过 `query_memory(tags, phase, idea_id, topic_id)` 按维度过滤查询。

### 6.5 知识库策略

**单一全局知识库**（`archon_research`）：
- 所有 topic、所有阶段的产出物统一存储
- 通过智谱 Embedding-3-pro 向量化
- 检索时通过 `scope` 参数按文件名前缀过滤（如 `scope="T001"` 只返回该 topic 的结果）
- 文件名由 `derive_display_name` 从本地路径推导，保留层级信息

上传时机：
- 阶段结束时由 `phase_logger._upload_artifacts` 批量上传
- Survey 流水线中每步完成后增量上传（`_upload_single_artifact`）
- Session 级去重避免重复上传

---

## 第七部分：配置与运行

### 7.1 环境配置

**Conda 环境**：`agent`（默认），Python 3.10

**API Keys**（`.env` 文件）：

| Key | 用途 | 必须 |
|-----|------|------|
| `MINIMAX_API_KEY` | LLM 调用 | 是 |
| `ZHIPU_API_KEY` | PDF 解析 + 知识库 | 否（降级运行） |
| `OPENALEX_EMAIL` | OpenAlex polite pool | 否（降低速率） |

**可选环境变量**：
- `MINIMAX_BASE_URL`（默认 `https://api.minimaxi.com/anthropic`）
- `MINIMAX_MODEL`（默认 `MiniMax-M2.5`）
- `PAPER_PARSE_BACKEND`（`zhipu` 或 `mineru`）

### 7.2 Topic 配置文件（`config.yaml`）

```yaml
topic:
  title: "时间序列预测中的均值回归特性建模与利用"
  domain: "time_series_forecasting"
  keywords:
    - mean reversion time series
    - Ornstein-Uhlenbeck process forecasting
    - ...

project:
  name: mean_reversion
  author: zhaodawei

llm:
  provider: minimax
  sdk: anthropic
  base_url: "https://api.minimaxi.com/anthropic"
  default_model: MiniMax-M2.5
  fast_model: MiniMax-M2.1-highspeed
  max_tokens: 8192

environment:
  conda_env: agent
  python: "3.10"

datasets:
  ETTh1:
    path: shared/data/ETTh1.csv
    format: csv
    ...

search:
  openalex_api: "https://api.openalex.org"
  web_search_engine: duckduckgo
```

`load_topic_config(config_path)` 从中提取标准化字段供 Agent 使用。

### 7.3 CLI 使用方式

```bash
# 完整流程
python run_research.py init --topic mean_reversion.md
python run_research.py elaborate --topic T001
python run_research.py survey --round 1
python run_research.py ideation --topic T001
python run_research.py refine --idea T001-I001
python run_research.py code-ref --idea T001-I001
python run_research.py code --idea T001-I001
python run_research.py experiment --idea T001-I001 --max-iter 3
python run_research.py analyze --idea T001-I001
python run_research.py conclude --idea T001-I001

# 一键自动
python run_research.py auto --idea T001-I001 --start refine --max-iter 3

# 辅助命令
python run_research.py status --topic T001          # 查看研究树状态
python run_research.py memory --phase survey        # 查询经验日志

# Survey 断点恢复
python run_research.py survey --step 3              # 从 Step 3 开始（跳过已完成步骤）

# 并行 refine
python run_research.py refine --idea T001 --parallel 3  # 并行细化所有 idea

# 跨引用
python run_research.py refine --idea T001-I001 --ref-ideas T002-I003 --ref-topics T002
```

Idea ID 采用 `T001-I001` 的两级编码格式（topic + idea），全局唯一。引用支持精确引用（`T001-I001`）和 topic 级引用（`T001` = 该 topic 下所有 idea）。
