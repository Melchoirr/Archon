# [F01] CLI 入口与项目初始化

## 状态
- **实现状态**：✅已完成

## 核心文件
- `run_research.py:36-47` — `_load_dotenv()`，加载 .env 环境变量
- `run_research.py:59-73` — `_parse_idea_ref()` / `_parse_ref_list()`，解析 idea/topic 引用
- `run_research.py:76-113` — `_find_topic_dir_by_md()` / `_find_topic_dir()`，查找 topic 目录
- `run_research.py:116-160` — `_parse_topic_md()`，解析 topic markdown 文件
- `run_research.py:163-301` — `cmd_init()`，初始化项目
- `run_research.py:325-373` — `_verify_environment()`，验证运行环境
- `run_research.py:376-394` — `_get_orchestrator()`，获取 Orchestrator 实例
- `run_research.py:397-561` — `cmd_elaborate()` ~ `cmd_auto()`，各阶段命令
- `run_research.py:564-650` — `cmd_fsm()`，FSM 模式命令
- `run_research.py:653-800` — `main()`，argparse 定义 + 命令映射

## 功能描述
CLI 入口层，提供 15 个子命令覆盖完整研究流程。两种运行模式：

1. **手动模式**：逐阶段执行（init, elaborate, survey, ideation, refine, code-ref, code, theory-check, debug, experiment, analyze, conclude, status, memory, auto）
2. **FSM 模式**：`fsm run` 自动走完 topic 或 idea 级状态机，支持 `--force` 强制跳转、`--from` 指定起始状态、`--auto` 全自动运行（跳过用户确认）

**Idea ID 格式**：`T001-I001`（两级编码：topic + idea），支持 `T001` 指代全 topic

**配置系统**：每个 topic 生成独立 `config.yaml`，包含 LLM 配置（MiniMax M2.5）、环境配置（conda_env: agent）、搜索配置（OpenAlex + DuckDuckGo）

## 运行流程

### 触发条件
- 用户在命令行执行 `python run_research.py <command>`
- 程序入口 `if __name__ == "__main__": main()`

### 处理步骤
1. **环境加载** — `_load_dotenv()` 读取 `.env`，设置 API key 环境变量
2. **日志配置** — INFO 级别，静音 httpx/anthropic/duckduckgo 等库
3. **CLI 解析** — argparse 解析子命令和参数
4. **Orchestrator 获取** — `_get_orchestrator(args)` 创建 ResearchOrchestrator（自动发现最新 topic）
5. **命令执行** — `commands[args.command](args)` 派发到对应 cmd_* 函数
6. **结果输出** — 打印摘要（前 500 字符）

### 输出
- init：`topics/T001_name/` 目录结构 + config.yaml + research_tree.yaml
- 其他命令：调用 Orchestrator 对应 phase 方法，打印结果摘要

### 依赖关系
- **上游**：无（系统入口）
- **下游**：F02（编排引擎，通过 _get_orchestrator() 创建）

### 错误与边界情况
- topic md 文件不存在时尝试 3 种路径查找（直接、topics/下、自动补 .md）
- API key 未设置时打印 WARNING 但不阻断
- 并行 refine 支持（`--idea T001` 时并行 refine 所有 idea，默认 3 workers）

## 测试方法
```bash
python run_research.py --help
python run_research.py init --topic mean_reversion.md
python run_research.py status
```

## 建议
（暂无）

## 变化
### [修复] 2026-03-26 10:18 — config.yaml 缺失时报错退出替代静默回退 (`d4e0e0a`)
- **目的**：topic 目录缺少 config.yaml 时不应回退到项目根目录的 config.yaml（可能不存在或配置不匹配），改为明确报错
- **改动**：`run_research.py` `_get_fsm()` 中 config_path 不存在时打印错误信息并 `sys.exit(1)`，不再回退到根目录 `config.yaml`
- **验证**：未测试

### [修改] 2026-03-24 10:57 — fsm run 增加 --auto CLI 参数 (`f944c36`)
- **目的**：支持全自动运行模式，跳过用户确认，由 MAX_RETRIES 控制上限
- **改动**：`run_research.py` — fsm_run_p 增加 `--auto` 参数；`cmd_fsm()` 中读取 auto 标志并设置到 FSM 实例
- **验证**：`python run_research.py fsm run --help` 显示 `--auto` 参数

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
- **目的**：实现 CLI 入口和项目初始化
- **改动**：新增 run_research.py（800 行），包含 15 个子命令、topic 解析、环境验证
- **验证**：未测试

### [修改] 2026-03-17 10:38 — FSM 模式与 topic md 自动初始化 (`b6b5ff6`)
- **目的**：新增 FSM 运行模式，支持 `fsm run --topic mean_reversion.md` 自动初始化
- **改动**：新增 cmd_fsm()、_get_fsm()，支持 --force/--from/--feedback 参数
- **验证**：未测试

### [修改] 2026-03-17 10:46 — 移除硬编码 author 字段 (`68c6db0`)
- **目的**：从 config.yaml 生成逻辑中移除硬编码的 author 字段
- **改动**：cmd_init() 中 config dict 不再包含 project.author
- **验证**：未测试
