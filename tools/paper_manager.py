"""论文管理工具：下载 PDF、解析为 Markdown（智谱API优先，MinerU fallback）、按需阅读章节"""
import json
import logging
import os
import re
import subprocess
import requests
import yaml
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

OPENALEX_API = "https://api.openalex.org"

# 解析后端: "zhipu" (默认) 或 "mineru"
PARSE_BACKEND = os.environ.get("PAPER_PARSE_BACKEND", "zhipu")


def _default_base_dir() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge", "papers")


def _get_paths(base_dir: str = "") -> dict:
    """Return resolved directory/file paths, creating dirs as needed."""
    base = base_dir or _default_base_dir()
    paths = {
        "base_dir": base,
        "pdf_dir": os.path.join(base, "pdf"),
        "md_dir": os.path.join(base, "parsed"),
        "index_path": os.path.join(base, "index.yaml"),
        "summaries_dir": os.path.join(base, "summaries"),
    }
    os.makedirs(paths["pdf_dir"], exist_ok=True)
    os.makedirs(paths["md_dir"], exist_ok=True)
    os.makedirs(paths["summaries_dir"], exist_ok=True)
    return paths

import threading
_index_lock = threading.Lock()


def _load_index(index_path: str = "") -> dict:
    if not index_path:
        index_path = _get_paths()["index_path"]
    with _index_lock:
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                return yaml.safe_load(f) or {}
    return {}


def _save_index(index: dict, index_path: str = ""):
    if not index_path:
        index_path = _get_paths()["index_path"]
    with _index_lock:
        with open(index_path, "w") as f:
            yaml.dump(index, f, allow_unicode=True, default_flow_style=False)


def _update_index(paper_id: str, entry: dict, index_path: str = ""):
    """原子更新 index 中的单条记录（线程安全）"""
    if not index_path:
        index_path = _get_paths()["index_path"]
    with _index_lock:
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                index = yaml.safe_load(f) or {}
        else:
            index = {}
        index[paper_id] = entry
        with open(index_path, "w") as f:
            yaml.dump(index, f, allow_unicode=True, default_flow_style=False)


def _get_pdf_url(paper_id: str) -> tuple[str | None, str]:
    """获取论文的 Open Access PDF URL。支持 OpenAlex (W*) 和 arXiv ID。返回 (url, title)"""
    import re as _re
    import time

    # arXiv ID → 直接构造 URL
    arxiv_match = _re.match(r"^(?:arXiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)$", paper_id, _re.IGNORECASE)
    if arxiv_match:
        aid = arxiv_match.group(1)
        return f"https://arxiv.org/pdf/{aid}", ""

    # OpenAlex W* ID → 调 OpenAlex API
    if paper_id.startswith("W") and paper_id[1:].isdigit():
        params = {"select": "id,display_name,open_access,best_oa_location,locations"}
        api_key = os.environ.get("OPENALEX_API_KEY", "")
        if api_key:
            params["api_key"] = api_key
        email = os.environ.get("OPENALEX_EMAIL", "")
        if email:
            params["mailto"] = email
        url = f"{OPENALEX_API}/works/{paper_id}"
        for attempt in range(3):
            try:
                resp = requests.get(url, params=params, timeout=30)
            except requests.RequestException:
                time.sleep(2 * (attempt + 1))
                continue
            if resp.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            if resp.status_code == 404:
                return None, ""
            resp.raise_for_status()
            data = resp.json()
            title = data.get("display_name", "")

            # 从 open_access 获取
            oa = data.get("open_access") or {}
            oa_url = oa.get("oa_url", "")
            if oa_url:
                return oa_url, title

            # 从 best_oa_location 获取
            best = data.get("best_oa_location") or {}
            pdf_url = best.get("pdf_url") or best.get("landing_page_url") or ""
            if pdf_url:
                return pdf_url, title

            # 从 locations 中找 arXiv
            for loc in data.get("locations") or []:
                source = loc.get("source") or {}
                if "arxiv" in (source.get("display_name") or "").lower():
                    landing = loc.get("landing_page_url") or ""
                    m = _re.search(r"arxiv\.org/abs/(\d{4}\.\d{4,5})", landing)
                    if m:
                        return f"https://arxiv.org/pdf/{m.group(1)}", title

            return None, title
        return None, ""

    # 其他格式的 ID（DOI 等）→ 尝试用 OpenAlex 搜索
    logger.warning(f"未知 paper_id 格式: {paper_id}，无法获取 PDF URL")
    return None, ""


def _find_md_file(paper_dir: str) -> str | None:
    """在 MinerU 输出目录中查找主 markdown 文件"""
    if not os.path.isdir(paper_dir):
        return None
    for root, _, files in os.walk(paper_dir):
        for f in files:
            if f.endswith(".md"):
                return os.path.join(root, f)
    return None


def _parse_sections(md_text: str) -> list[dict]:
    """将 markdown 按标题切分为章节列表"""
    sections = []
    current = {"title": "preamble", "level": 0, "content": ""}
    for line in md_text.split("\n"):
        m = re.match(r'^(#{1,4})\s+(.*)', line)
        if m:
            if current["content"].strip():
                sections.append(current)
            current = {
                "title": m.group(2).strip(),
                "level": len(m.group(1)),
                "content": "",
            }
        else:
            current["content"] += line + "\n"
    if current["content"].strip():
        sections.append(current)
    return sections


def _parse_pdf_zhipu(pdf_path: str) -> str | None:
    """用智谱异步文档解析 API（expert 档）将 PDF 解析为 Markdown。

    流程: 创建任务 → 轮询结果。expert 档支持图表和公式解析。

    Returns:
        解析后的文本，失败返回 None
    """
    import time as _time

    api_key = os.environ.get("ZHIPU_API_KEY", "")
    if not api_key:
        logger.warning("ZHIPU_API_KEY 未设置，无法使用智谱解析")
        return None

    headers = {"Authorization": f"Bearer {api_key}"}

    # 1. 创建解析任务
    create_url = "https://open.bigmodel.cn/api/paas/v4/files/parser/create"
    try:
        with open(pdf_path, "rb") as f:
            files = {"file": (os.path.basename(pdf_path), f, "application/pdf")}
            data = {"tool_type": "expert", "file_type": "pdf"}
            resp = requests.post(create_url, headers=headers, files=files, data=data, timeout=120)
        resp.raise_for_status()
        create_result = resp.json()
    except Exception as e:
        logger.warning(f"智谱解析创建任务失败: {e}")
        return None

    task_id = create_result.get("task_id") or create_result.get("id")
    if not task_id:
        logger.warning(f"智谱解析未返回 task_id: {create_result}")
        return None

    # 2. 轮询结果
    result_url = f"https://open.bigmodel.cn/api/paas/v4/files/parser/result/{task_id}/text"
    max_wait = 180  # 最多等 3 分钟
    poll_interval = 3
    waited = 0

    while waited < max_wait:
        _time.sleep(poll_interval)
        waited += poll_interval
        try:
            resp = requests.get(result_url, headers=headers, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                status = result.get("status", "")
                if status == "succeeded" or status == "success":
                    content = result.get("content", "")
                    if content:
                        return content
                    # 可能内容在其他字段
                    data = result.get("data")
                    if isinstance(data, str) and data:
                        return data
                    if isinstance(data, dict) and data.get("content"):
                        return data["content"]
                    logger.warning(f"智谱解析成功但无内容: {list(result.keys())}")
                    return None
                elif status in ("failed", "error"):
                    logger.warning(f"智谱解析任务失败: {result.get('message', '')}")
                    return None
                # processing / pending → 继续等
            elif resp.status_code == 404:
                pass  # 任务还没准备好
            else:
                logger.warning(f"智谱轮询异常 HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"智谱轮询异常: {e}")

    logger.warning(f"智谱解析超时（等待 {max_wait}s），task_id={task_id}")
    return None


def _parse_pdf_mineru(pdf_path: str, output_dir: str) -> str | None:
    """用 MinerU 将 PDF 解析为 Markdown（fallback）。

    Returns:
        md 文件路径，失败返回 None
    """
    os.makedirs(output_dir, exist_ok=True)
    try:
        result = subprocess.run(
            ["mineru", "-p", pdf_path, "-o", output_dir,
             "-b", "pipeline", "-m", "txt", "-d", "mps",
             "-f", "false", "-t", "false"],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            logger.warning(f"MinerU 解析失败: {result.stderr[:500]}")
            return None
    except FileNotFoundError:
        logger.warning("MinerU 未安装")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("MinerU 解析超时（>10分钟）")
        return None

    return _find_md_file(output_dir)


def _parse_pdf(pdf_path: str, paper_id: str, md_dir: str = "") -> tuple[str | None, str]:
    """解析 PDF 为 Markdown，返回 (md_path, backend_used)。

    产出文件直接放在 parsed/ 目录下（无子目录），文件名为 {safe_id}.md。
    优先用智谱 API，失败则 fallback 到 MinerU。
    """
    if not md_dir:
        md_dir = _get_paths()["md_dir"]
    safe_id = paper_id.replace("/", "_").replace(":", "_")
    md_path = os.path.join(md_dir, f"{safe_id}.md")

    if PARSE_BACKEND == "zhipu":
        md_text = _parse_pdf_zhipu(pdf_path)
        if md_text:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_text)
            return md_path, "zhipu"
        # fallback
        logger.info("智谱解析失败，fallback 到 MinerU")

    # MinerU 需要输出目录
    mineru_output_dir = os.path.join(md_dir, f"_mineru_{safe_id}")
    mineru_md = _parse_pdf_mineru(pdf_path, mineru_output_dir)
    if mineru_md:
        # 将 MinerU 输出的 md 复制到扁平路径
        import shutil
        shutil.copy2(mineru_md, md_path)
        return md_path, "mineru"
    return None, ""


def check_local_knowledge(query: str, resource_type: str = "all", base_dir: str = "") -> str:
    """检查本地知识库中是否已存在匹配的资源（论文、代码库、总结）。

    在下载前调用此工具，避免重复下载已有内容。支持按 paper_id、标题关键词、
    repo 名称/URL 模糊匹配。

    Args:
        query: 搜索词（paper_id / arXiv ID / 标题关键词 / repo 名称或 URL）
        resource_type: 资源类型 paper/repo/summary/all（默认 all）
        base_dir: 论文存储根目录（默认 knowledge/papers）
    Returns:
        匹配结果的描述，包含已存在资源的路径和状态
    """
    results = []
    query_lower = query.lower().strip()

    # --- 论文检查 ---
    if resource_type in ("all", "paper"):
        paths = _get_paths(base_dir)
        index = _load_index(paths["index_path"])
        for pid, info in index.items():
            title_str = info.get("title", "")
            # 精确 ID 匹配
            if query_lower == pid.lower() or query_lower == info.get("arxiv_id", "").lower():
                has_pdf = bool(info.get("pdf_path") and os.path.exists(info["pdf_path"]))
                has_md = bool(info.get("md_path") and os.path.exists(info["md_path"]))
                results.append(
                    f"[论文·精确匹配] {pid} — {title_str}\n"
                    f"  PDF: {'有 ' + info.get('pdf_path', '') if has_pdf else '无'}\n"
                    f"  Markdown: {'有 ' + info.get('md_path', '') if has_md else '无'}"
                )
            # 标题模糊匹配
            elif query_lower in title_str.lower() or query_lower in pid.lower():
                has_md = bool(info.get("md_path") and os.path.exists(info["md_path"]))
                results.append(
                    f"[论文·标题匹配] {pid} — {title_str} (Markdown: {'有' if has_md else '无'})"
                )

    # --- 总结检查 ---
    if resource_type in ("all", "summary"):
        paths = _get_paths(base_dir)
        summaries_dir = paths["summaries_dir"]
        if os.path.isdir(summaries_dir):
            for fname in os.listdir(summaries_dir):
                if fname.endswith(".md") and query_lower in fname.lower():
                    results.append(f"[总结] {os.path.join(summaries_dir, fname)}")

    # --- 代码库检查 ---
    if resource_type in ("all", "repo"):
        repos_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge", "repos")
        if os.path.isdir(repos_dir):
            # 从 URL 提取 repo 名称
            repo_name = query.rstrip("/").split("/")[-1].replace(".git", "").lower()
            for d in os.listdir(repos_dir):
                if not os.path.isdir(os.path.join(repos_dir, d)):
                    continue
                if query_lower in d.lower() or repo_name in d.lower():
                    full_path = os.path.join(repos_dir, d)
                    has_summary = os.path.exists(os.path.join(full_path, "SUMMARY.md"))
                    results.append(
                        f"[代码库] {full_path} (SUMMARY: {'有' if has_summary else '无'})"
                    )

    if not results:
        return f"本地知识库中未找到与 '{query}' 匹配的资源，可以下载。"
    return f"找到 {len(results)} 个匹配资源:\n\n" + "\n\n".join(results)


def download_paper(paper_id: str, title: str = "", base_dir: str = "") -> str:
    """下载论文 PDF 并解析为 Markdown（智谱API优先，MinerU fallback）。

    Args:
        paper_id: 论文 ID（支持 OpenAlex W* / arXiv ID）
        title: 论文标题（可选，用于索引记录）
        base_dir: 论文存储根目录（默认 knowledge/papers）
    Returns:
        下载和解析结果的描述
    """
    paths = _get_paths(base_dir)
    index = _load_index(paths["index_path"])

    if paper_id in index and index[paper_id].get("md_path"):
        md_path = index[paper_id]["md_path"]
        if os.path.exists(md_path):
            return f"论文 {paper_id} 已下载并解析过，md 路径: {md_path}"

    # 1. 获取 PDF URL
    pdf_url, fetched_title = _get_pdf_url(paper_id)
    if not title and fetched_title:
        title = fetched_title
    if not pdf_url:
        return f"论文 {paper_id} 没有 Open Access PDF 可下载"

    # 2. 下载 PDF
    pdf_path = os.path.join(paths["pdf_dir"], f"{paper_id}.pdf")
    try:
        resp = requests.get(pdf_url, timeout=120, stream=True)
        resp.raise_for_status()
        with open(pdf_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        return f"PDF 下载失败: {e}"

    # 3. 解析 PDF → Markdown
    md_path, backend = _parse_pdf(pdf_path, paper_id, md_dir=paths["md_dir"])
    if not md_path:
        return f"PDF 解析失败（智谱API和MinerU均失败），PDF已保存: {pdf_path}"

    # 4. 更新索引（线程安全）
    sections = _parse_sections(open(md_path, "r").read())
    section_titles = [s["title"] for s in sections if s["title"] != "preamble"]

    _update_index(paper_id, {
        "title": title or paper_id,
        "pdf_path": pdf_path,
        "md_path": md_path,
        "sections": section_titles,
    }, index_path=paths["index_path"])

    return f"论文下载并解析成功!\n- PDF: {pdf_path}\n- Markdown: {md_path}\n- 章节数: {len(section_titles)}\n- 章节: {', '.join(section_titles[:10])}"


def read_paper_section(paper_id: str, section: str = "", base_dir: str = "") -> str:
    """按需阅读论文的指定部分。

    Args:
        paper_id: 论文 ID（支持 OpenAlex W* / arXiv ID）
        section: 章节名（如 abstract, introduction, method）或关键词。为空则返回结构概览。
        base_dir: 论文存储根目录（默认 knowledge/papers）
    Returns:
        论文指定部分的内容
    """
    MAX_CHARS = 3000

    paths = _get_paths(base_dir)
    index = _load_index(paths["index_path"])
    entry = index.get(paper_id)
    if not entry or not entry.get("md_path"):
        return f"论文 {paper_id} 尚未下载解析，请先调用 download_paper"

    md_path = entry["md_path"]
    if not os.path.exists(md_path):
        return f"Markdown 文件不存在: {md_path}"

    md_text = open(md_path, "r").read()
    sections = _parse_sections(md_text)

    # 无 section 参数：返回结构概览
    if not section:
        overview_lines = [f"# {entry.get('title', paper_id)}", ""]
        for s in sections:
            if s["title"] == "preamble":
                continue
            prefix = "#" * s["level"]
            first_lines = s["content"].strip().split("\n")[:2]
            preview = " ".join(first_lines)[:100]
            overview_lines.append(f"{prefix} {s['title']}")
            overview_lines.append(f"  > {preview}...")
            overview_lines.append("")
        return "\n".join(overview_lines)

    # 模糊匹配章节名
    section_lower = section.lower()
    best_match = None
    best_score = 0.0

    # 常见别名映射
    aliases = {
        "abstract": ["abstract"],
        "introduction": ["introduction", "intro"],
        "method": ["method", "methodology", "approach", "proposed", "framework"],
        "experiment": ["experiment", "evaluation", "result", "empirical"],
        "conclusion": ["conclusion", "summary", "discussion"],
        "related": ["related work", "background", "literature"],
    }

    # 先尝试别名匹配
    expanded_terms = [section_lower]
    for key, vals in aliases.items():
        if section_lower in vals or section_lower == key:
            expanded_terms = vals
            break

    for s in sections:
        title_lower = s["title"].lower()
        for term in expanded_terms:
            if term in title_lower:
                score = len(term) / max(len(title_lower), 1)
                if score > best_score:
                    best_score = score
                    best_match = s

    # 如果没有匹配到章节名，尝试序列匹配
    if not best_match:
        for s in sections:
            score = SequenceMatcher(None, section_lower, s["title"].lower()).ratio()
            if score > best_score and score > 0.4:
                best_score = score
                best_match = s

    if best_match:
        content = best_match["content"].strip()
        if len(content) > MAX_CHARS:
            content = content[:MAX_CHARS] + "\n\n... [内容截断，共 {} 字符]".format(len(best_match["content"]))
        return f"## {best_match['title']}\n\n{content}"

    # 关键词搜索模式：在全文中搜索包含关键词的段落
    keyword = section_lower
    matching_paragraphs = []
    for s in sections:
        paragraphs = re.split(r'\n\n+', s["content"])
        for p in paragraphs:
            if keyword in p.lower():
                matching_paragraphs.append(f"[{s['title']}] {p.strip()}")

    if matching_paragraphs:
        result = f"关键词 '{section}' 的搜索结果 ({len(matching_paragraphs)} 段):\n\n"
        total = 0
        for p in matching_paragraphs:
            if total + len(p) > MAX_CHARS:
                result += f"\n... [还有更多结果未显示]"
                break
            result += p + "\n\n"
            total += len(p)
        return result

    return f"未找到与 '{section}' 匹配的章节或关键词"


def list_papers(base_dir: str = "") -> str:
    """列出所有已下载的论文。

    Args:
        base_dir: 论文存储根目录（默认 knowledge/papers）
    Returns:
        论文列表（paper_id, title, 是否有 md）
    """
    paths = _get_paths(base_dir)
    index = _load_index(paths["index_path"])
    if not index:
        return "尚无已下载的论文"

    lines = ["已下载论文列表:", ""]
    for pid, info in index.items():
        has_md = "有" if info.get("md_path") and os.path.exists(info["md_path"]) else "无"
        title = info.get("title", "未知")
        n_sections = len(info.get("sections", []))
        lines.append(f"- [{pid}] {title} (Markdown: {has_md}, 章节数: {n_sections})")
    return "\n".join(lines)



def extract_paper_ids_from_summaries(summaries_dir: str = None, topic_id: str = None) -> list:
    """从论文总结文件中提取 paper ID 列表。

    Args:
        summaries_dir: 总结目录路径，默认为全局 summaries 目录
        topic_id: 如果指定，只提取属于该 topic 的总结

    Returns:
        [{"file": "paper_timegrad.md", "paper_id": "arXiv:2107.03502", "title": "TimeGrad..."}]
    """
    if summaries_dir is None:
        summaries_dir = _get_paths()["summaries_dir"]

    if not os.path.exists(summaries_dir):
        return []

    results = []
    for fname in os.listdir(summaries_dir):
        if not fname.endswith(".md"):
            continue

        fpath = os.path.join(summaries_dir, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        # 如果指定了 topic_id，检查文件是否属于该 topic
        if topic_id:
            if f"topic: {topic_id}" not in content and f"topic:{topic_id}" not in content:
                continue

        # 提取 Paper ID
        paper_id = None
        title = ""

        # 匹配 Paper ID: arXiv:xxx 或 DOI:xxx 或 S2 ID
        id_match = re.search(r'Paper ID:\s*(\S+)', content)
        if id_match:
            paper_id = id_match.group(1).strip()

        # 提取标题（第一个 # 标题）
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()

        if paper_id:
            results.append({
                "file": fname,
                "paper_id": paper_id,
                "title": title,
            })

    return results


def batch_download_papers(paper_ids: list) -> dict:
    """批量下载论文 PDF。

    Args:
        paper_ids: extract_paper_ids_from_summaries 的返回值

    Returns:
        {"downloaded": N, "no_access": N, "failed": N, "details": [...]}
    """
    import time

    results = {"downloaded": 0, "no_access": 0, "failed": 0, "details": []}

    for item in paper_ids:
        pid = item["paper_id"]
        title = item.get("title", "")

        # 检查是否已下载
        index = _load_index()
        if pid in index and index[pid].get("pdf_path") and os.path.exists(index[pid]["pdf_path"]):
            results["details"].append({"paper_id": pid, "status": "already_exists"})
            results["downloaded"] += 1
            continue

        result_str = download_paper(pid, title)

        if "没有 Open Access PDF" in result_str:
            results["no_access"] += 1
            results["details"].append({"paper_id": pid, "status": "no_access"})
        elif "失败" in result_str or "Error" in result_str:
            results["failed"] += 1
            results["details"].append({"paper_id": pid, "status": "failed", "error": result_str[:200]})
        else:
            results["downloaded"] += 1
            results["details"].append({"paper_id": pid, "status": "downloaded"})

        # 间隔 2s 避免 429
        time.sleep(2)

    return results


def update_global_index(paper_ids: list, topic_id: str, base_dir: str = ""):
    """更新全局论文索引 index.yaml，按 paper_id 去重，标记引用的 topic。

    Args:
        paper_ids: extract_paper_ids_from_summaries 的返回值
        topic_id: 当前 topic ID
        base_dir: 论文存储根目录（默认 knowledge/papers）
    """
    paths = _get_paths(base_dir)
    index = _load_index(paths["index_path"])

    for item in paper_ids:
        pid = item["paper_id"]
        if pid in index:
            # 已存在，追加 topic 引用
            topics = index[pid].get("topics", [])
            if topic_id and topic_id not in topics:
                topics.append(topic_id)
            index[pid]["topics"] = topics
        else:
            # 新增条目
            index[pid] = {
                "title": item.get("title", pid),
                "topics": [topic_id] if topic_id else [],
                "summary_path": os.path.join(paths["summaries_dir"], item["file"]),
            }

    _save_index(index, paths["index_path"])


def search_paper_index(query: str, topic_id: str = None, base_dir: str = "") -> str:
    """按标题/关键词搜索全局论文索引。

    Args:
        query: 搜索关键词
        topic_id: 可选，只搜索指定 topic 引用的论文
        base_dir: 论文存储根目录（默认 knowledge/papers）

    Returns:
        匹配的论文列表描述
    """
    paths = _get_paths(base_dir)
    index = _load_index(paths["index_path"])
    if not index:
        return "全局论文索引为空"

    query_lower = query.lower()
    matches = []

    for pid, info in index.items():
        title = info.get("title", "").lower()
        topics = info.get("topics", [])

        # topic 过滤
        if topic_id and topic_id not in topics:
            continue

        # 关键词匹配
        if query_lower in title or query_lower in pid.lower():
            summary_path = info.get("summary_path", "")
            pdf_path = info.get("pdf_path", "")
            matches.append(
                f"- [{pid}] {info.get('title', '')} "
                f"(topics: {', '.join(topics)}, "
                f"summary: {summary_path}, pdf: {pdf_path})"
            )

    if not matches:
        return f"未找到与 '{query}' 匹配的论文"

    return f"找到 {len(matches)} 篇匹配论文:\n" + "\n".join(matches)



def title_to_slug(title: str) -> str:
    """将论文标题转为文件名安全的 slug。

    例: "Autoformer: Decomposition Transformers" -> "autoformer_decomposition_transformers"
    """
    # 移除非字母数字字符，转小写
    slug = re.sub(r'[^a-zA-Z0-9\s]', '', title.lower())
    # 多空格合并，替换为下划线
    slug = re.sub(r'\s+', '_', slug.strip())
    # 截断到合理长度
    if len(slug) > 60:
        slug = slug[:60].rstrip('_')
    return slug


def download_paper_by_arxiv(arxiv_id: str, paper_id: str = "", title: str = "",
                            base_dir: str = "") -> str:
    """通过 arXiv ID 直接下载 PDF 并用 MinerU 解析。

    Args:
        arxiv_id: arXiv ID（如 "2106.13008"）
        paper_id: 论文 ID（用于索引标识，默认用 arxiv_id）
        title: 论文标题
        base_dir: 论文存储根目录（默认 knowledge/papers）
    Returns:
        下载和解析结果描述
    """
    paths = _get_paths(base_dir)
    if not paper_id:
        paper_id = f"arXiv:{arxiv_id}"

    index = _load_index(paths["index_path"])

    # 检查是否已下载
    if paper_id in index and index[paper_id].get("md_path"):
        md_path = index[paper_id]["md_path"]
        if os.path.exists(md_path):
            return f"论文 {paper_id} 已下载并解析过，md 路径: {md_path}"

    # arXiv PDF URL
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

    # 下载 PDF
    pdf_path = os.path.join(paths["pdf_dir"], f"{paper_id.replace('/', '_').replace(':', '_')}.pdf")
    try:
        resp = requests.get(pdf_url, timeout=120, stream=True)
        resp.raise_for_status()
        with open(pdf_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        return f"arXiv PDF 下载失败 ({arxiv_id}): {e}"

    # 解析 PDF → Markdown
    md_path, backend = _parse_pdf(pdf_path, paper_id, md_dir=paths["md_dir"])
    if not md_path:
        return f"PDF 解析失败（智谱API和MinerU均失败），PDF已保存: {pdf_path}"

    # 更新索引（线程安全）
    sections = _parse_sections(open(md_path, "r").read())
    section_titles = [s["title"] for s in sections if s["title"] != "preamble"]

    _update_index(paper_id, {
        "title": title or paper_id,
        "pdf_path": pdf_path,
        "md_path": md_path,
        "sections": section_titles,
    }, index_path=paths["index_path"])

    return f"论文下载并解析成功!\n- PDF: {pdf_path}\n- Markdown: {md_path}\n- 章节数: {len(section_titles)}"
