# Archon 项目文档体系

本目录用于系统化跟踪 Archon 项目的演化过程，涵盖架构、变更、问题、规划等方面。

## 文件索引

| 文件 | 用途 |
|------|------|
| [architecture.md](architecture.md) | 项目架构快照 — 模块、层次、依赖关系 |
| [changelog.md](changelog.md) | 变更日志 — 按版本/日期记录重要变更 |
| [issues.md](issues.md) | 已知问题和 Bug 跟踪 |
| [todo.md](todo.md) | 待办事项和未来规划 |
| [test_log.md](test_log.md) | 测试记录 — 运行结果、发现的问题 |
| [decisions.md](decisions.md) | 设计决策记录 — 关键技术选型和理由 |

## 更新约定

- **何时更新**：每次完成重要功能、修复 Bug、或做出架构决策后，及时更新相关文档
- **谁来更新**：开发者（人工或 AI 辅助）在完成代码变更后同步更新
- **changelog.md**：每次提交重要变更时追加记录
- **issues.md**：发现问题时创建，修复后更新状态
- **todo.md**：迭代规划时更新，完成后标记
- **architecture.md**：架构发生实质性变化时更新
- **decisions.md**：做出重要技术选型时记录
- **test_log.md**：执行测试后记录结果
