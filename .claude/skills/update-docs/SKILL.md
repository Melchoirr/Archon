---
name: update-docs
description: "MUST use after ANY of: (1) creating or updating a plan, (2) modifying code, (3) running tests or receiving test results from user, (4) discovering or fixing bugs, (5) any conversation end where files were changed. Proactively invoke — do not wait for user to ask. Maintains record/project/index.md + features/*.md + flow.md with commit-level change tracking."
---

# update-docs

## 流程

1. **识别涉及的功能** — 读 `record/project/index.md` 功能清单，按核心文件匹配变更文件。无匹配时：同目录新文件→扩展现有功能；全新模块→新建 feature 文件；配置文件→跳过。

2. **更新 features/fXX-*.md** — 使用以下模板结构：

   **「状态」节**：刷新实现状态。

   **「核心文件」节**：更新文件列表（行号、类/函数名、职责）。

   **「功能描述」节**：更新功能描述（解决什么问题、核心概念、关键数据结构、配置项）。

   **「运行流程」节**：更新触发条件、处理步骤、输出、依赖关系、错误与边界情况。

   **「变化」节**：在顶部追加条目（最新在上）：
   ```markdown
   ### [tag] YYYY-MM-DD HH:MM — 标题 (`commit_hash`)
   - **目的**：为什么做这个变更
   - **改动**：具体改了什么（文件、函数、逻辑）
   - **验证**：怎么验证正确性（命令 + 结果），未验证则写「未测试」
   ```
   Tag: `[计划]` `[实现]` `[修改]` `[修复]` `[重构]` `[弃用]` `[启用]`

   跨功能测试：在每个涉及的功能文件中都记录。

   **「建议」节**：当某条建议被纳入计划时，状态改为 📋已计划；用户否决时改为 🚫否决。

3. **判断是否需要更新 flow.md** — 决策矩阵：

   | 变更类型 | 更新 flow.md？ |
   |----------|---------------|
   | 新增/删除/重构模块 | ✅ 是 |
   | 调用链变化（新增调用、移除调用、调用顺序变化） | ✅ 是 |
   | 新增阶段或状态转换规则变化 | ✅ 是 |
   | 入口文件参数或初始化逻辑变化 | ✅ 是 |
   | 模块内部逻辑变化（不影响调用链） | ❌ 否 |
   | 仅修改配置/常量/文案 | ❌ 否 |

   需要更新时：仅更新受影响的阶段，不重写整个 flow.md。更新 mermaid 流程图中对应的节点和边。

4. **增量更新 index.md** — 使用分点列表 + 折叠格式（非表格）。只改涉及的功能条目（最后变更、状态等）。新功能追加条目，格式：

   ```markdown
   ### FXX — 功能名称 · 状态 · 维护状态
   - **核心文件**：`file1.py`, `file2.py`
   - **上游**：FXX（提供什么） / **下游**：FYY（消费什么）
   - **最后变更**：YYYY-MM-DD HH:MM

   <details><summary>功能概要</summary>

   **做什么**：一段话描述功能职责
   **怎么做**：核心逻辑的简要说明（3-5 行）
   **关键接口**：主要的类/函数及其签名
   **数据流**：输入什么 → 经过什么处理 → 输出什么

   </details>

   → [完整详情](features/fXX-name.md)
   ```

   全局问题汇总从 features/ 聚合（加链接）。

5. **Commit** — `git add` 变更文件 + 文档，commit message 准确描述变更。commit 后补 hash 到变化条目。

## 约定
- 时间：UTC+8，`YYYY-MM-DD HH:MM`。**必须通过 `date '+%Y-%m-%d %H:%M'` 获取精确时间，禁止仅使用系统注入的 currentDate（它只有日期没有时间）**
- ID：FXX 递增，文件名 `fXX-kebab-case.md`
- 状态：✅已完成 / 🔧进行中 / 📋计划中 / ❌已废弃
- 折叠：`<details><summary>` 包裹详情
