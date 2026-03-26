"""统一资源预检与索引 — 论文、仓库、数据集的去重/预检入口"""

import logging
import os
import re
import threading
from datetime import datetime

import yaml

logger = logging.getLogger(__name__)

_repo_lock = threading.Lock()
_dataset_lock = threading.Lock()


# ── 通用 YAML 索引读写 ────────────────────────────────────────

def _load_yaml_index(path: str, lock: threading.Lock) -> dict:
    with lock:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    return {}


def _save_yaml_index(data: dict, path: str, lock: threading.Lock):
    with lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)


# ── URL 归一化 ─────────────────────────────────────────────────

def normalize_repo_url(url: str) -> str:
    """归一化 GitHub URL：去 protocol/.git/trailing slash，lowercase。

    Examples:
        https://github.com/User/Repo.git  -> github.com/user/repo
        git@github.com:User/Repo          -> github.com/user/repo
        https://github.com/User/Repo/     -> github.com/user/repo
    """
    url = url.strip()
    # SSH 格式: git@github.com:user/repo -> github.com/user/repo
    url = re.sub(r"^git@([^:]+):", r"\1/", url)
    # 去 protocol
    url = re.sub(r"^https?://", "", url)
    # 去 .git 后缀和 trailing slash
    url = url.rstrip("/").removesuffix(".git")
    return url.lower()


# ── 仓库索引 ──────────────────────────────────────────────────

def _default_repo_index_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "research", "knowledge", "repos", "index.yaml")


def register_repo(repo_url: str, local_path: str,
                  has_summary: bool = False) -> str:
    """将已 clone 的仓库注册到索引。"""
    index_path = _default_repo_index_path()
    index = _load_yaml_index(index_path, _repo_lock)
    key = normalize_repo_url(repo_url)
    index[key] = {
        "url": repo_url,
        "local_path": local_path,
        "has_summary": has_summary,
        "cloned_at": datetime.now().strftime("%Y-%m-%d"),
    }
    _save_yaml_index(index, index_path, _repo_lock)
    return f"已注册仓库: {key} -> {local_path}"


def update_repo_summary(repo_url: str = "", local_path: str = ""):
    """标记仓库已生成 SUMMARY.md（按 URL 或 local_path 查找）。"""
    index_path = _default_repo_index_path()
    index = _load_yaml_index(index_path, _repo_lock)

    target_key = None
    if repo_url:
        target_key = normalize_repo_url(repo_url)
    elif local_path:
        for k, v in index.items():
            if v.get("local_path") == local_path:
                target_key = k
                break

    if target_key and target_key in index:
        index[target_key]["has_summary"] = True
        _save_yaml_index(index, index_path, _repo_lock)


def _lookup_repo_index(query_lower: str) -> list[str]:
    """从 repo index 查找匹配的仓库，返回格式化结果列表。"""
    index_path = _default_repo_index_path()
    index = _load_yaml_index(index_path, _repo_lock)
    results = []
    # 尝试把 query 作为 URL 归一化后精确匹配
    query_normalized = normalize_repo_url(query_lower)
    for key, info in index.items():
        if query_normalized == key:
            lp = info.get("local_path", "")
            hs = info.get("has_summary", False)
            results.append(
                f"[代码库·精确匹配] {info.get('url', key)}\n"
                f"  本地路径: {lp}\n"
                f"  SUMMARY: {'有' if hs else '无'}"
            )
        elif query_lower in key or query_lower in info.get("local_path", "").lower():
            lp = info.get("local_path", "")
            hs = info.get("has_summary", False)
            results.append(
                f"[代码库·模糊匹配] {info.get('url', key)} -> {lp} "
                f"(SUMMARY: {'有' if hs else '无'})"
            )
    return results


# ── 数据集索引 ─────────────────────────────────────────────────

def _default_dataset_index_path() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "research", "knowledge", "dataset_cards", "index.yaml")


def _default_data_dir() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "shared", "data")


def _default_dataset_cards_dir() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "research", "knowledge", "dataset_cards")


def register_dataset(name: str, local_path: str = "", url: str = "",
                     format: str = "", description: str = "",
                     access_mode: str = "downloaded",
                     size_info: str = "", access_note: str = "") -> str:
    """注册数据集到索引并生成 dataset card。

    所有数据集（无论是否下载）都必须注册。access_mode 为 downloaded 时
    local_path 必填；card_only 时 access_note 应说明如何获取数据。
    """
    # 更新索引
    index_path = _default_dataset_index_path()
    index = _load_yaml_index(index_path, _dataset_lock)
    key = name.strip().lower()
    entry = {
        "name": name,
        "url": url,
        "local_path": local_path,
        "format": format,
        "description": description,
        "access_mode": access_mode,
        "size_info": size_info,
        "registered_at": datetime.now().strftime("%Y-%m-%d"),
    }
    if access_note:
        entry["access_note"] = access_note
    index[key] = entry
    _save_yaml_index(index, index_path, _dataset_lock)

    # 生成 dataset card
    card_path = _write_dataset_card(name, entry)

    mode_label = "已下载" if access_mode == "downloaded" else "仅记录"
    target = local_path or card_path
    return f"已注册数据集 ({mode_label}): {name} -> {target}"


def _write_dataset_card(name: str, entry: dict) -> str:
    """生成/更新 dataset card markdown 文件。"""
    cards_dir = _default_dataset_cards_dir()
    os.makedirs(cards_dir, exist_ok=True)
    # 文件名: 小写+下划线
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name.strip().lower())
    card_path = os.path.join(cards_dir, f"{safe_name}.md")

    access_mode = entry.get("access_mode", "downloaded")
    lines = [
        f"# {entry.get('name', name)}",
        "",
        f"- **获取方式**: {'已下载到本地' if access_mode == 'downloaded' else '仅记录（未下载）'}",
    ]
    if entry.get("url"):
        lines.append(f"- **来源**: {entry['url']}")
    if entry.get("format"):
        lines.append(f"- **格式**: {entry['format']}")
    if entry.get("size_info"):
        lines.append(f"- **规模**: {entry['size_info']}")
    if access_mode == "downloaded" and entry.get("local_path"):
        lines.append(f"- **本地路径**: `{entry['local_path']}`")
    if entry.get("access_note"):
        lines.append(f"- **获取说明**: {entry['access_note']}")
    if entry.get("description"):
        lines.append("")
        lines.append("## 描述")
        lines.append(entry["description"])
    lines.append("")

    with open(card_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return card_path


# ── 统一预检入口 ──────────────────────────────────────────────

def check_local_knowledge(query: str, resource_type: str = "all",
                          base_dir: str = "", repos_dir: str = "") -> str:
    """检查本地知识库中是否已存在匹配的资源（论文、代码库、数据集、总结）。

    在下载前调用此工具，避免重复下载已有内容。支持 paper_id、标题关键词、
    repo 名称/URL、数据集名称模糊匹配。

    Args:
        query: 搜索词
        resource_type: 资源类型 paper/repo/summary/dataset/all（默认 all）
        base_dir: 论文存储根目录（默认 knowledge/papers）
        repos_dir: 仓库存储根目录（默认 knowledge/repos）
    Returns:
        匹配结果的描述，包含已存在资源的路径和状态
    """
    results = []
    query_lower = query.lower().strip()

    # --- 论文检查 ---
    if resource_type in ("all", "paper"):
        from tools.paper_manager import _get_paths, _load_index
        paths = _get_paths(base_dir)
        index = _load_index(paths["index_path"])
        for pid, info in index.items():
            title_str = info.get("title", "")
            if query_lower == pid.lower() or query_lower == info.get("arxiv_id", "").lower():
                has_pdf = bool(info.get("pdf_path") and os.path.exists(info["pdf_path"]))
                has_md = bool(info.get("md_path") and os.path.exists(info["md_path"]))
                results.append(
                    f"[论文·精确匹配] {pid} — {title_str}\n"
                    f"  PDF: {'有 ' + info.get('pdf_path', '') if has_pdf else '无'}\n"
                    f"  Markdown: {'有 ' + info.get('md_path', '') if has_md else '无'}"
                )
            elif query_lower in title_str.lower() or query_lower in pid.lower():
                has_md = bool(info.get("md_path") and os.path.exists(info["md_path"]))
                results.append(
                    f"[论文·标题匹配] {pid} — {title_str} (Markdown: {'有' if has_md else '无'})"
                )

    # --- 总结检查 ---
    if resource_type in ("all", "summary"):
        from tools.paper_manager import _get_paths
        paths = _get_paths(base_dir)
        summaries_dir = paths["summaries_dir"]
        if os.path.isdir(summaries_dir):
            for fname in os.listdir(summaries_dir):
                if fname.endswith(".md") and query_lower in fname.lower():
                    results.append(f"[总结] {os.path.join(summaries_dir, fname)}")

    # --- 代码库检查（索引优先 + 目录 fallback）---
    if resource_type in ("all", "repo"):
        # 先查索引
        index_results = _lookup_repo_index(query_lower)
        results.extend(index_results)

        # 目录 fallback（捕获未入索引的旧仓库）
        if not repos_dir:
            repos_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                     "research", "knowledge", "repos")
        if os.path.isdir(repos_dir):
            repo_name = query.rstrip("/").split("/")[-1].replace(".git", "").lower()
            # 收集索引中已知的 local_path，避免重复报告
            known_paths = {r.split("本地路径: ")[-1].split("\n")[0]
                           for r in index_results if "本地路径" in r}
            for d in os.listdir(repos_dir):
                full_path = os.path.join(repos_dir, d)
                if not os.path.isdir(full_path) or d == "index.yaml":
                    continue
                if full_path in known_paths:
                    continue
                if query_lower in d.lower() or repo_name in d.lower():
                    has_summary = os.path.exists(os.path.join(full_path, "SUMMARY.md"))
                    results.append(
                        f"[代码库·目录匹配] {full_path} (SUMMARY: {'有' if has_summary else '无'})"
                    )

    # --- 数据集检查（索引 + 文件扫描）---
    if resource_type in ("all", "dataset"):
        # 查索引
        ds_index_path = _default_dataset_index_path()
        ds_index = _load_yaml_index(ds_index_path, _dataset_lock)
        indexed_paths = set()
        for key, info in ds_index.items():
            name = info.get("name", key)
            lp = info.get("local_path", "")
            if query_lower in key or query_lower in name.lower():
                exists = bool(lp and os.path.exists(lp))
                indexed_paths.add(lp)
                results.append(
                    f"[数据集·索引匹配] {name}\n"
                    f"  路径: {lp} ({'存在' if exists else '缺失'})\n"
                    f"  格式: {info.get('format', '未知')}"
                )
            elif query_lower in info.get("url", "").lower():
                exists = bool(lp and os.path.exists(lp))
                indexed_paths.add(lp)
                results.append(
                    f"[数据集·URL匹配] {name} -> {lp} ({'存在' if exists else '缺失'})"
                )

        # 文件 fallback（扫描 shared/data/ 目录）
        data_dir = _default_data_dir()
        if os.path.isdir(data_dir):
            for entry in os.listdir(data_dir):
                entry_path = os.path.join(data_dir, entry)
                if entry_path in indexed_paths:
                    continue
                if query_lower in entry.lower():
                    if os.path.isfile(entry_path):
                        size_mb = os.path.getsize(entry_path) / (1024 * 1024)
                        results.append(
                            f"[数据集·文件匹配] {entry_path} ({size_mb:.1f} MB)"
                        )
                    elif os.path.isdir(entry_path):
                        results.append(f"[数据集·目录匹配] {entry_path}/")

    if not results:
        return f"本地知识库中未找到与 '{query}' 匹配的资源，可以下载。"
    return f"找到 {len(results)} 个匹配资源:\n\n" + "\n\n".join(results)
