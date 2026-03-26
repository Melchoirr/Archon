"""GitHub 仓库工具：clone/summarize/list（集成 repo 索引去重）"""
import os
import subprocess
import logging

from tools.knowledge_index import (
    normalize_repo_url, register_repo, update_repo_summary,
    _load_yaml_index, _repo_lock, _default_repo_index_path,
)

logger = logging.getLogger(__name__)

_DEFAULT_REPOS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "research", "knowledge", "repos")


def _ensure_repos_dir(repos_dir: str = ""):
    os.makedirs(repos_dir or _DEFAULT_REPOS_DIR, exist_ok=True)


def clone_repo(repo_url: str, target_dir: str = "", repos_dir: str | None = None) -> str:
    """Git clone 仓库到 knowledge/repos/ 目录。

    去重逻辑：先用归一化 URL 查索引，再检查目录是否存在。
    clone 成功后自动注册到 repo 索引。

    Args:
        repo_url: GitHub 仓库 URL
        target_dir: 目标目录名（默认从 URL 推断）
        repos_dir: 仓库存储根目录
    """
    repos_dir = repos_dir or _DEFAULT_REPOS_DIR
    _ensure_repos_dir(repos_dir)

    # 索引去重：归一化 URL 检查
    index = _load_yaml_index(_default_repo_index_path(), _repo_lock)
    normalized = normalize_repo_url(repo_url)
    if normalized in index:
        existing_path = index[normalized].get("local_path", "")
        if existing_path and os.path.exists(existing_path):
            return f"Repository already exists at {existing_path} (indexed as {normalized})"

    if not target_dir:
        target_dir = repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    full_path = os.path.join(repos_dir, target_dir)
    if os.path.exists(full_path):
        # 目录存在但未入索引 → 补注册
        register_repo(repo_url, full_path,
                      has_summary=os.path.exists(os.path.join(full_path, "SUMMARY.md")))
        return f"Repository already exists at {full_path}"

    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, full_path],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            register_repo(repo_url, full_path)
            return f"Cloned {repo_url} -> {full_path}"
        return f"Clone failed: {result.stderr}"
    except subprocess.TimeoutExpired:
        return "Clone timed out (>120s)"
    except Exception as e:
        return f"Clone error: {e}"


def summarize_repo(repo_path: str, repos_dir: str | None = None) -> str:
    """用 claude -p 生成仓库代码摘要。

    Args:
        repo_path: 仓库路径（如 knowledge/repos/repo_name）
        repos_dir: 未使用，保留以统一接口签名
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
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", ".git")]
        for f in files:
            if f.endswith((".py", ".md", ".yaml", ".yml", ".json", ".cfg", ".toml")):
                rel = os.path.relpath(os.path.join(root, f), repo_path)
                key_files.append(rel)

    file_list = "\n".join(key_files[:50])

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
            update_repo_summary(local_path=repo_path)
            return summary
        return f"Summary generation failed: {result.stderr}"
    except FileNotFoundError:
        return "claude CLI not available for summarization"
    except subprocess.TimeoutExpired:
        return "Summary generation timed out"


def list_repos(repos_dir: str | None = None) -> str:
    """列出已 clone 的仓库（索引优先，目录 fallback）

    Args:
        repos_dir: 仓库存储根目录
    """
    repos_dir = repos_dir or _DEFAULT_REPOS_DIR
    _ensure_repos_dir(repos_dir)

    # 优先从索引读
    index = _load_yaml_index(_default_repo_index_path(), _repo_lock)
    repos = []
    indexed_dirs = set()

    for key, info in index.items():
        lp = info.get("local_path", "")
        hs = info.get("has_summary", False)
        name = os.path.basename(lp) if lp else key
        exists = bool(lp and os.path.exists(lp))
        indexed_dirs.add(lp)
        repos.append(f"  {name}/ {'(has SUMMARY)' if hs else ''}"
                     f"{'' if exists else ' [路径缺失]'}")

    # fallback：扫描目录中未入索引的仓库
    if os.path.isdir(repos_dir):
        for d in os.listdir(repos_dir):
            full = os.path.join(repos_dir, d)
            if not os.path.isdir(full) or d.startswith(".") or d == "index.yaml":
                continue
            if full not in indexed_dirs:
                has_summary = os.path.exists(os.path.join(full, "SUMMARY.md"))
                repos.append(f"  {d}/ {'(has SUMMARY)' if has_summary else ''} [未入索引]")

    if not repos:
        return "No repositories cloned yet."
    return "Cloned repositories:\n" + "\n".join(repos)
