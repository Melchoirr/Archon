# Archon — AI 驱动的科研自动化系统

多 Agent 协作的端到端科研系统，专注时序预测领域。从课题定义到实验结论，全链路自动化。

## 架构

```
入口层   run_research.py (CLI)
            │
编排层   Orchestrator / FSM 状态机
            │
执行层   11 Agent + 20 Tool（ReAct 循环）
```

**技术栈**：MiniMax M2.5 (Anthropic SDK 兼容) · OpenAlex 学术搜索 · 智谱知识库 · Claude Code 代码生成 · DuckDuckGo

## 研究流程

```
init → elaborate → survey → ideation → refine → code-ref → code → experiment → analyze → conclude
```

| 阶段 | 说明 | 产出 |
|------|------|------|
| **init** | 从 topic md 创建项目结构 | 目录 + config.yaml + research_tree |
| **elaborate** | 展开研究背景 | context.md |
| **survey** | 文献调研（搜索→下载→摘要→仓库→综合） | survey/*.md, baselines.md, datasets.md |
| **ideation** | 生成研究 idea 并评分 | ideas/I00x/proposal.md + review.md |
| **refine** | 细化理论和实验设计 | theory.md + experiment_plan.md |
| **code-ref** | 获取参考代码仓库 | 代码摘要 |
| **code** | 编写实现代码 | src/{model/, experiment/} |
| **experiment** | 运行实验（支持多版本迭代） | results/S01/V1/{metrics, plots} |
| **analyze** | 分析实验结果（支持 VLM 读图） | analysis.md |
| **conclude** | 生成结论，记录经验 | conclusion.md |

## 快速开始

### 环境准备

```bash
pip install -r requirements.txt
```

在 `.env` 中配置：
```
MINIMAX_API_KEY=your_key
ZHIPU_API_KEY=your_key          # 可选，知识库功能
```

### Topic 文件格式

在 `topics/` 下创建 md 文件，需包含以下 section：

```markdown
# 课题标题

## 领域
时间序列预测

## 关键词
- keyword1
- keyword2

## 描述
研究动机和核心思路。

## 范围
实验范围和约束条件。
```

### 运行

```bash
# 初始化 + 交互式运行（传 .md 自动初始化）
python run_research.py --topic your_topic.md

# 初始化 + 全自动运行
python run_research.py --topic your_topic.md --auto

# 恢复已有 topic
python run_research.py --topic T001
python run_research.py --topic T001 --auto

# 单 idea 运行
python run_research.py --idea T001-I001
python run_research.py --idea T001-I001 --auto

# 从指定阶段开始
python run_research.py --idea T001-I001 --from refine

# 强制跳转状态
python run_research.py --idea T001-I001 --force conclude
```

### 辅助查询

```bash
python run_research.py --status [--topic T001]                  # FSM 状态
python run_research.py --history [--topic T001] [--idea T001-I001]  # 转换历史
python run_research.py --memory [--tags t1,t2] [--phase survey]     # 经验记忆
```

## 目录结构

```
├── run_research.py           # CLI 入口
├── agents/                   # Agent 层（11 个）
│   ├── base_agent.py         #   ReAct 基类
│   ├── orchestrator.py       #   中央编排器
│   ├── fsm_engine.py         #   FSM 状态机引擎
│   └── ...                   #   各阶段专用 Agent
├── tools/                    # 工具层（20 个模块）
├── shared/                   # 共享模型和工具
├── topics/                   # 课题目录（运行时生成）
├── knowledge/                # 论文、代码仓库、数据集卡片
└── memory/                   # 经验记忆系统
```

## FSM 状态机

FSM 分为 **Topic 级**和 **Idea 级**两层，每层有独立的状态和评估器。

### Topic 级 FSM

```
elaborate → survey → ideation → [为每个 idea 启动 Idea FSM]
               ↑        |
               └────────┘
            SurveyEvaluator:
            need_more → 继续调研
            sufficient → 进入 ideation
```

### Idea 级 FSM

```
refine → theory_check ──→ code_reference → code → debug ──→ experiment → analyze ──→ conclude
  ↑          │                                      ↑           ↑            │
  │          │ TheoryEvaluator                      │           │            │ AnalysisEvaluator
  │          ├─ sound → 继续                         │           └────────────┤
  │          ├─ weak → 回到 refine                   │          tune → 迭代V+1 ├─ success → conclude
  │          ├─ flawed → 回到 refine                 │                        ├─ enrich → experiment
  │          └─ derivative → abandoned               │ DebugEvaluator         ├─ code_bug → debug
  │                                                  ├─ tests_pass → 继续     ├─ restructure → refine
  └──────────────────────────────────────────────────┼─ fixable → 重试 debug  ├─ need_literature → survey
                                                     ├─ needs_rewrite → code  └─ abandon → abandoned
                                                     └─ design_issue → refine
```

### 重试上限（auto 模式）

| 状态 | 最大重试 |
|------|---------|
| refine | 4 |
| theory_check | 3 |
| debug | 6 |
| experiment | 6 |
| survey | 4 |

超过上限自动进入 `abandoned`（analyze 阶段若达标率 ≥ 30% 则进入 `conclude`）。

交互模式下，回退跳转（如 analyze→refine、theory_check→abandoned）需用户确认。

## 核心机制

- **Idea ID**：`T001-I001` 两级编码（Topic + Idea），全局唯一
- **交叉引用**：`--ref-ideas T001-I002,T002-I003` / `--ref-topics T002` 实现跨 idea/topic 引用
- **并行 refine**：`--idea T001` 自动并行 refine 该 topic 下所有 idea
- **实验迭代**：`--max-iter 3` 自动多版本迭代，每轮基于上轮结果改进
- **知识积累**：研究树追踪状态 + 经验日志避免重复犯错 + 智谱知识库向量检索
