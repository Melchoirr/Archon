"""GitHub 仓库工具：clone/summarize/list"""
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

REPOS_DIR = "knowledge/repos"


def _ensure_repos_dir():
    os.makedirs(REPOS_DIR, exist_ok=True)


def clone_repo(repo_url: str, target_dir: str = "") -> str:
    """Git clone 仓库到 knowledge/repos/ 目录。

    Args:
        repo_url: GitHub 仓库 URL
        target_dir: 目标目录名（默认从 URL 推断）
    """
    _ensure_repos_dir()
    if not target_dir:
        target_dir = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    full_path = os.path.join(REPOS_DIR, target_dir)
    if os.path.exists(full_path):
        return f"Repository already exists at {full_path}"

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, full_path],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            return f"Cloned {repo_url} -> {full_path}"
        return f"Clone failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        return "Clone timed out (>120s)"
    except Exception as e:
        return f"Clone error: {e}"


def summarize_repo(repo_path: str) -> str:
    """用 claude -p 生成仓库代码摘要。

    Args:
        repo_path: 仓库路径（如 knowledge/repos/repo_name）
    """
    if not os.path.exists(repo_path):
        return f"Repository not found: {repo_path}"

    summary_path = os.path.join(repo_path, "SUMMARY.md")
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            return f.read()

    # 收集关键文件
    key_files = []
    for root, dirs, files in os.walk(repo_path):
        # 跳过隐藏目录和常见无用目录
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", ".git")]
        for f in files:
            if f.endswith((".py", ".md", ".yaml", ".yml", ".json", ".cfg", ".toml")):
                rel = os.path.relpath(os.path.join(root, f), repo_path)
                key_files.append(rel)

    # 构建摘要提示
    file_list = "\n".join(key_files[:50])  # 限制文件数

    prompt = f"""请分析这个代码仓库并生成摘要。

仓库路径: {repo_path}
关键文件:
{file_list}

请生成 SUMMARY.md，包含:
1. 仓库功能概述
2. 核心模块和文件结构
3. 关键实现细节（模型结构、训练方法、损失函数等）
4. 可复用的代码片段和 trick
5. 依赖和环境要求"""

    try:
        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        result = subprocess.run(
            ["claude", "-p", prompt,
             "--output-format", "text",
             "--dangerously-skip-permissions"],
            cwd=repo_path,
            capture_output=True, text=True, timeout=300, env=env,
        )
        summary = result.stdout.strip()
        if summary:
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary)
            return summary
        return f"Summary generation failed: {result.stderr}"
    except FileNotFoundError:
        return "claude CLI not available for summarization"
    except subprocess.TimeoutExpired:
        return "Summary generation timed out"


def list_repos() -> str:
    """列出已 clone 的仓库"""
    _ensure_repos_dir()
    repos = []
    for d in os.listdir(REPOS_DIR):
        full = os.path.join(REPOS_DIR, d)
        if os.path.isdir(full) and not d.startswith("."):
            has_summary = os.path.exists(os.path.join(full, "SUMMARY.md"))
            repos.append(f"  {d}/ {'(has SUMMARY)' if has_summary else ''}")
    if not repos:
        return "No repositories cloned yet."
    return "Cloned repositories:\n" + "\n".join(repos)
