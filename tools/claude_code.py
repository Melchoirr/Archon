"""Claude Code CLI 工具：调用 claude -p 完成编码任务，每次聚焦一个模块"""
import subprocess
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def _clean_env() -> dict:
    """返回清理后的环境变量，移除嵌套 Claude Code 检测"""
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    return env


def _run_claude_p(prompt: str, cwd: str, timeout: int = 600) -> str:
    """调用 claude -p 并返回结果"""
    try:
        result = subprocess.run(
            ["claude", "-p", prompt,
             "--output-format", "text",
             "--dangerously-skip-permissions"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_clean_env(),
        )
        output = result.stdout.strip()
        if result.returncode != 0 and result.stderr:
            output += f"\n\n[stderr]: {result.stderr.strip()}"
        if not output:
            return "[Claude Code 无输出]"
        if len(output) > 8000:
            output = output[:8000] + f"\n\n... [输出截断，共 {len(output)} 字符]"
        return output
    except FileNotFoundError:
        return "claude CLI 未安装或不在 PATH 中"
    except subprocess.TimeoutExpired:
        return f"Claude Code 执行超时（>{timeout // 60}分钟）"


def claude_write_module(module_name: str, task: str, working_dir: str = "",
                        context_files: str = "") -> str:
    """调用 claude -p 编写一个功能模块。

    Args:
        module_name: 模块名称（如 "数据加载器"、"模型定义"、"训练循环"）
        task: 详细的编码任务描述，包含功能、输入输出、技术要求、目标文件路径
        working_dir: 工作目录（相对于项目根目录）
        context_files: 参考文件内容（直接传入文件内容作为上下文）
    Returns:
        Claude Code 的输出结果
    """
    cwd = os.path.join(PROJECT_ROOT, working_dir) if working_dir else PROJECT_ROOT
    if not os.path.isdir(cwd):
        return f"工作目录不存在: {cwd}"

    prompt = f"""你需要编写模块: {module_name}

{task}
"""
    if context_files:
        prompt += f"""
## 参考代码/文档
{context_files[:4000]}
"""

    prompt += """
要求:
1. 只关注当前模块的实现
2. 代码完整可运行，包含必要的 import
3. 遵循项目实验基础设施规范（YAML 配置、统一入口、标准输出目录）"""

    return _run_claude_p(prompt, cwd)


def claude_fix_error(error_info: str, fix_instruction: str = "", working_dir: str = "") -> str:
    """调用 claude -p 修复代码错误。

    Args:
        error_info: 错误信息（traceback、测试失败输出等）
        fix_instruction: 额外的修复提示
        working_dir: 工作目录
    Returns:
        修复结果
    """
    cwd = os.path.join(PROJECT_ROOT, working_dir) if working_dir else PROJECT_ROOT
    if not os.path.isdir(cwd):
        return f"工作目录不存在: {cwd}"

    prompt = f"""修复以下错误:

```
{error_info[:3000]}
```

{fix_instruction}

只修复错误，不做无关改动。"""

    return _run_claude_p(prompt, cwd)


def claude_review(review_instruction: str, working_dir: str = "") -> str:
    """调用 claude -p 审查代码。

    Args:
        review_instruction: 审查指令（审查什么文件、关注什么）
        working_dir: 工作目录
    Returns:
        审查结果
    """
    cwd = os.path.join(PROJECT_ROOT, working_dir) if working_dir else PROJECT_ROOT

    prompt = f"""{review_instruction}

只列出问题和修复建议，简明扼要。如无问题则回复"审查通过"。"""

    return _run_claude_p(prompt, cwd, timeout=300)

