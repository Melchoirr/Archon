# [F08] 实验执行与调试

## 状态

- **实现状态**：✅已完成
- **核心文件**：
  - `agents/experiment_agent.py` — `ExperimentAgent`，编排代码实现（任务分解→Claude Code 分发→基础设施管理）
  - `agents/debug_agent.py` — `DebugAgent`，运行测试、修复 Bug、验证代码与设计文档一致性，产出 debug_report.md
  - `agents/data_agent.py` — `DataAgent`，数据集下载 + EDA（探索性数据分析），venv 隔离运行
  - `tools/claude_code.py` — `claude_write_module()`、`claude_fix_error()`、`claude_review()`，分发编码任务到 Claude Code CLI (-p)
  - `tools/bash_exec.py` — `run_command()`，shell 命令执行 + 可选 venv 激活
  - `tools/venv_manager.py` — `setup_idea_venv()`，per-idea venv 创建 + 依赖安装（支持 uv）
- **功能描述**：代码实现全链路 — ExperimentAgent 分解编码任务并通过 Claude Code CLI 执行；DebugAgent 运行测试、修复错误、做完整性检查；DataAgent 管理数据集获取和 EDA。每个 idea 有独立 venv 避免依赖冲突。支持迭代实验循环（experiment_loop）。
- **测试方法**：
  ```bash
  python run_research.py code --idea T001-I001
  python run_research.py debug --idea T001-I001
  python run_research.py experiment --idea T001-I001 --max-iter 3
  ```

## 建议

（暂无）

## 变化

### [重构] 2026-03-17 10:38 — venv 隔离、EDA 环境支持 (`b6b5ff6`)

<details><summary>详情</summary>

**计划**：增强 venv 管理，支持 EDA 环境
**代码修改**：重构 venv_manager.py，更新 experiment_agent.py 和 data_agent.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)

<details><summary>详情</summary>

**计划**：建立实验执行与调试管道
**代码修改**：新增 experiment_agent.py、debug_agent.py、data_agent.py、claude_code.py、bash_exec.py、venv_manager.py
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>
