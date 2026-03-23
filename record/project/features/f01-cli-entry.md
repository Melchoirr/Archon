# [F01] CLI 入口与项目初始化

## 状态

- **实现状态**：✅已完成
- **核心文件**：
  - `run_research.py:1` — 主入口，argparse 子命令分发（init/elaborate/survey/ideation/refine/code/experiment/analyze/conclude/auto/fsm/status/memory）
  - `run_research.py:163` — `cmd_init()`，从 topic md 文件创建目录结构 + config.yaml + research_tree.yaml
  - `run_research.py:325` — `_verify_environment()`，检查 API key + 依赖 + MiniMax 连通性
- **功能描述**：CLI 入口层，解析命令行参数后分发到 Orchestrator 或 FSM。`init` 命令从 topics/ 下的 markdown 文件解析结构化信息（标题/领域/关键词/描述/范围），创建 topic 目录和初始配置。Idea ID 格式 `T001-I001`，两级编码。
- **测试方法**：
  ```bash
  python run_research.py --help
  python run_research.py init --topic mean_reversion.md
  python run_research.py status
  ```

## 建议

（暂无）

## 变化

### [实现] 2026-03-11 17:12 — 初始实现 (`969dd1c`)

<details><summary>详情</summary>

**计划**：建立完整的 CLI 入口，支持所有研究阶段命令
**代码修改**：新增 run_research.py，包含 15 个子命令 + init 项目初始化 + 环境验证
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>

### [修改] 2026-03-17 10:38 — FSM 子命令与 topic md 自动 init (`b6b5ff6`)

<details><summary>详情</summary>

**计划**：支持 `fsm run --topic mean_reversion.md` 自动触发 init
**代码修改**：新增 fsm 子命令（run/status/history）、`_find_topic_dir_by_md()` 辅助函数
**测试**：
| 方法 | 结果 | 备注 |
|------|------|------|
| （暂无记录） | | |

</details>
