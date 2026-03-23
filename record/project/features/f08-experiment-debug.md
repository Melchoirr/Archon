# [F08] 实验执行与调试

## 状态
- **实现状态**：✅已完成

## 核心文件
- `agents/experiment_agent.py:110-149` — `ExperimentAgent.__init__()`，11 个工具，40 次迭代
- `agents/experiment_agent.py:150-159` — `_load_infra_template()`，加载基础设施模板
- `agents/experiment_agent.py:161-194` — `build_code_prompt()`，代码编写 prompt（含 debug_report_path）
- `agents/experiment_agent.py:189-225` — `build_experiment_prompt()`，实验运行 prompt
- `agents/experiment_agent.py:24-107` — system prompt（PM 角色 + 8 项规范）
- `agents/debug_agent.py:54-76` — `DebugAgent.__init__()`，6 个工具，35 次迭代
- `agents/debug_agent.py:77-112` — `build_prompt()`，调试 prompt（analysis_path + debug_report_path）
- `tools/claude_code.py:42-75` — `claude_write_module()`，委托 Claude Code 写模块
- `tools/claude_code.py:77-102` — `claude_fix_error()`，修 bug
- `tools/claude_code.py:104-121` — `claude_review()`，代码审查
- `tools/venv_manager.py:8-78` — `setup_idea_venv()`，创建隔离 venv（uv 优先）
- `tools/bash_exec.py:1-27` — `run_command()`，执行 shell 命令

## 功能描述
代码编写、调试、实验运行三大能力：

**ExperimentAgent（代码编写）**：PM 角色，Claude Code 作为程序员。分解任务 → 逐模块 `claude_write_module()` → structure.md + requirements.txt。8 项基础设施规范：YAML 配置、统一入口、Pydantic 校验、Trainer、Evaluator、Ablation、Bash 脚本、可视化。

**ExperimentAgent（实验运行）**：在 venv 中执行实验步骤（S01→S02→...），支持多版本迭代。

**DebugAgent**：运行测试 → 修 bug → 验证（最多 5 轮），输出 debug_report.md。

**Venv 隔离**：uv（快）或 python -m venv，每 idea 独立 venv，支持 pip mirror。

## 运行流程

### 触发条件
- `code --idea T001-I001` 或 FSM idea_state == "code"
- `debug --idea T001-I001` 或 FSM idea_state == "debug"
- `experiment --idea T001-I001` 或 FSM idea_state == "experiment"

### 处理步骤（代码编写）
1. **加载模板** — `_load_infra_template()` 读取基础设施规范
2. **构建 prompt** — 组合设计文档 + 模板 + 参考代码
3. **ReAct 循环**（40 迭代）— 分解任务 → `claude_write_module()` 逐模块实现
4. **Venv 设置** — 创建环境 + 安装依赖

### 处理步骤（调试）
1. **DebugAgent**（35 迭代，6 工具）运行测试 → `claude_fix_error()` 修复 → 验证
2. **输出** — debug_report.md，FSM 解析 verdict

### 输出
- 代码 → `ideas/*/src/`
- 调试 → 修复后 src/ + debug_report.md
- 实验 → `results/SXX_name/VN/`

### 依赖关系
- **上游**：F07（设计文档）、F02（FSM 触发）
- **下游**：F09（分析依赖实验输出）、F04（DebugVerdict → FSM 路由）

### 错误与边界情况
- Claude Code 超时、输出截断到 8000 字符
- debug 重试上限 6 次，needs_rewrite → 返回 code
- venv 创建失败：fallback 系统 Python

## 测试方法
```bash
python run_research.py code --idea T001-I001
python run_research.py debug --idea T001-I001
python run_research.py experiment --idea T001-I001 --step S01
```

## 建议
（暂无）

## 变化
### [修改] 2026-03-24 00:13 — DebugAgent/ExperimentAgent 用文档路径替代 feedback 字符串 (`1e3166c`)
- **目的**：analyze→debug、debug→debug、debug→code 回退时，下游 Agent 信息不足。改为传文档路径让 Agent 自行读取完整内容
- **改动**：`debug_agent.py` `build_prompt()` 去掉 `feedback`，增加 `analysis_path` + `debug_report_path`；`experiment_agent.py` `build_code_prompt()` 增加 `debug_report_path`，refactor 为先赋值 prompt 变量再 return
- **验证**：import 通过

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)
- **目的**：实现代码编写、调试、实验运行
- **改动**：新增 experiment_agent.py + debug_agent.py + claude_code.py + venv_manager.py + bash_exec.py
- **验证**：未测试

### [重构] 2026-03-17 10:38 — Venv 隔离 + EDA 环境支持 (`b6b5ff6`)
- **目的**：每 idea 独立 venv，支持 uv 快速安装和 pip mirror
- **改动**：新增 venv_manager.py，experiment_agent.py 集成 venv
- **验证**：未测试
