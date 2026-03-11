"""论文管理工具：下载 PDF、MinerU 解析为 Markdown、按需阅读章节"""
import json
import os
import re
import subprocess
import requests
import yaml
from difflib import SequenceMatcher

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge", "papers")
PDF_DIR = os.path.join(BASE_DIR, "pdf")
MD_DIR = os.path.join(BASE_DIR, "parsed")
INDEX_PATH = os.path.join(BASE_DIR, "index.yaml")

SS_API = "https://api.semanticscholar.org/graph/v1"

SUMMARIES_DIR = os.path.join(BASE_DIR, "summaries")

os.makedirs(PDF_DIR, exist_ok=True)
os.makedirs(MD_DIR, exist_ok=True)
os.makedirs(SUMMARIES_DIR, exist_ok=True)


def _load_index() -> dict:
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


def _save_index(index: dict):
    with open(INDEX_PATH, "w") as f:
        yaml.dump(index, f, allow_unicode=True, default_flow_style=False)


def _get_pdf_url(paper_id: str) -> tuple[str | None, str]:
    """从 Semantic Scholar 获取 Open Access PDF URL。返回 (url, title)"""
    import time
    url = f"{SS_API}/paper/{paper_id}"
    params = {"fields": "openAccessPdf,title"}
    for attempt in range(3):
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(3 * (attempt + 1))
            continue
        resp.raise_for_status()
        data = resp.json()
        title = data.get("title", "")
        oa = data.get("openAccessPdf")
        if oa and oa.get("url"):
            return oa["url"], title
        return None, title
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


def download_paper(paper_id: str, title: str = "") -> str:
    """下载论文 PDF 并用 MinerU 解析为 Markdown。

    Args:
        paper_id: Semantic Scholar 论文 ID
        title: 论文标题（可选，用于索引记录）
    Returns:
        下载和解析结果的描述
    """
    index = _load_index()

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
    pdf_path = os.path.join(PDF_DIR, f"{paper_id}.pdf")
    try:
        resp = requests.get(pdf_url, timeout=120, stream=True)
        resp.raise_for_status()
        with open(pdf_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        return f"PDF 下载失败: {e}"

    # 3. 调用 MinerU 解析
    output_dir = os.path.join(MD_DIR, paper_id)
    os.makedirs(output_dir, exist_ok=True)
    try:
        result = subprocess.run(
            ["mineru", "-p", pdf_path, "-o", output_dir],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            return f"MinerU 解析失败: {result.stderr[:500]}"
    except FileNotFoundError:
        return "MinerU 未安装。请运行: conda activate agent && uv pip install -U 'mineru[all]'"
    except subprocess.TimeoutExpired:
        return "MinerU 解析超时（>5分钟）"

    # 4. 找到输出的 md 文件
    md_path = _find_md_file(output_dir)
    if not md_path:
        return f"MinerU 解析完成但未找到 .md 文件，输出目录: {output_dir}"

    # 5. 更新索引
    sections = _parse_sections(open(md_path, "r").read())
    section_titles = [s["title"] for s in sections if s["title"] != "preamble"]

    index[paper_id] = {
        "title": title or paper_id,
        "pdf_path": pdf_path,
        "md_path": md_path,
        "sections": section_titles,
    }
    _save_index(index)

    return f"论文下载并解析成功!\n- PDF: {pdf_path}\n- Markdown: {md_path}\n- 章节数: {len(section_titles)}\n- 章节: {', '.join(section_titles[:10])}"


def read_paper_section(paper_id: str, section: str = "") -> str:
    """按需阅读论文的指定部分。

    Args:
        paper_id: Semantic Scholar 论文 ID
        section: 章节名（如 abstract, introduction, method）或关键词。为空则返回结构概览。
    Returns:
        论文指定部分的内容
    """
    MAX_CHARS = 3000

    index = _load_index()
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


def list_papers() -> str:
    """列出所有已下载的论文。

    Returns:
        论文列表（paper_id, title, 是否有 md）
    """
    index = _load_index()
    if not index:
        return "尚无已下载的论文"

    lines = ["已下载论文列表:", ""]
    for pid, info in index.items():
        has_md = "有" if info.get("md_path") and os.path.exists(info["md_path"]) else "无"
        title = info.get("title", "未知")
        n_sections = len(info.get("sections", []))
        lines.append(f"- [{pid}] {title} (Markdown: {has_md}, 章节数: {n_sections})")
    return "\n".join(lines)


# Tool schemas for MiniMax function calling
DOWNLOAD_PAPER_SCHEMA = {
    "description": "下载论文 PDF 并用 MinerU 解析为 Markdown，支持后续按章节阅读",
    "parameters": {
        "type": "object",
        "properties": {
            "paper_id": {"type": "string", "description": "Semantic Scholar 论文 ID"},
            "title": {"type": "string", "description": "论文标题（可选，用于索引）", "default": ""},
        },
        "required": ["paper_id"],
    },
}

READ_PAPER_SECTION_SCHEMA = {
    "description": "按需阅读论文的指定章节（如 method, experiment）或按关键词搜索论文内容。为空则返回结构概览。",
    "parameters": {
        "type": "object",
        "properties": {
            "paper_id": {"type": "string", "description": "Semantic Scholar 论文 ID"},
            "section": {"type": "string", "description": "章节名（abstract/introduction/method/experiment/conclusion）或搜索关键词，为空返回概览", "default": ""},
        },
        "required": ["paper_id"],
    },
}

LIST_PAPERS_SCHEMA = {
    "description": "列出所有已下载并解析的论文",
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}


def extract_paper_ids_from_summaries(summaries_dir: str = None, topic_id: str = None) -> list:
    """从论文总结文件中提取 paper ID 列表。

    Args:
        summaries_dir: 总结目录路径，默认为全局 summaries 目录
        topic_id: 如果指定，只提取属于该 topic 的总结

    Returns:
        [{"file": "paper_timegrad.md", "paper_id": "arXiv:2107.03502", "title": "TimeGrad..."}]
    """
    if summaries_dir is None:
        summaries_dir = SUMMARIES_DIR

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


def update_global_index(paper_ids: list, topic_id: str):
    """更新全局论文索引 index.yaml，按 paper_id 去重，标记引用的 topic。

    Args:
        paper_ids: extract_paper_ids_from_summaries 的返回值
        topic_id: 当前 topic ID
    """
    index = _load_index()

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
                "summary_path": os.path.join(SUMMARIES_DIR, item["file"]),
            }

    _save_index(index)


def search_paper_index(query: str, topic_id: str = None) -> str:
    """按标题/关键词搜索全局论文索引。

    Args:
        query: 搜索关键词
        topic_id: 可选，只搜索指定 topic 引用的论文

    Returns:
        匹配的论文列表描述
    """
    index = _load_index()
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


SEARCH_PAPER_INDEX_SCHEMA = {
    "description": "搜索全局论文索引，查找已有的论文总结避免重复调研",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词（标题或 paper ID）"},
            "topic_id": {"type": "string", "description": "可选，只搜索指定 topic 引用的论文", "default": ""},
        },
        "required": ["query"],
    },
}


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


def download_paper_by_arxiv(arxiv_id: str, paper_id: str = "", title: str = "") -> str:
    """通过 arXiv ID 直接下载 PDF 并用 MinerU 解析。

    Args:
        arxiv_id: arXiv ID（如 "2106.13008"）
        paper_id: Semantic Scholar paper ID（用于索引标识，默认用 arxiv_id）
        title: 论文标题
    Returns:
        下载和解析结果描述
    """
    if not paper_id:
        paper_id = f"arXiv:{arxiv_id}"

    index = _load_index()

    # 检查是否已下载
    if paper_id in index and index[paper_id].get("md_path"):
        md_path = index[paper_id]["md_path"]
        if os.path.exists(md_path):
            return f"论文 {paper_id} 已下载并解析过，md 路径: {md_path}"

    # arXiv PDF URL
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

    # 下载 PDF
    pdf_path = os.path.join(PDF_DIR, f"{paper_id.replace('/', '_').replace(':', '_')}.pdf")
    try:
        resp = requests.get(pdf_url, timeout=120, stream=True)
        resp.raise_for_status()
        with open(pdf_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        return f"arXiv PDF 下载失败 ({arxiv_id}): {e}"

    # MinerU 解析
    safe_id = paper_id.replace("/", "_").replace(":", "_")
    output_dir = os.path.join(MD_DIR, safe_id)
    os.makedirs(output_dir, exist_ok=True)
    try:
        result = subprocess.run(
            ["mineru", "-p", pdf_path, "-o", output_dir],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            return f"MinerU 解析失败: {result.stderr[:500]}"
    except FileNotFoundError:
        return "MinerU 未安装。请运行: conda activate agent && uv pip install -U 'mineru[all]'"
    except subprocess.TimeoutExpired:
        return "MinerU 解析超时（>5分钟）"

    # 找 md 文件
    md_path = _find_md_file(output_dir)
    if not md_path:
        return f"MinerU 解析完成但未找到 .md 文件，输出目录: {output_dir}"

    # 更新索引
    sections = _parse_sections(open(md_path, "r").read())
    section_titles = [s["title"] for s in sections if s["title"] != "preamble"]

    index[paper_id] = {
        "title": title or paper_id,
        "pdf_path": pdf_path,
        "md_path": md_path,
        "sections": section_titles,
    }
    _save_index(index)

    return f"论文下载并解析成功!\n- PDF: {pdf_path}\n- Markdown: {md_path}\n- 章节数: {len(section_titles)}"
