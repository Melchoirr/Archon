"""OpenAlex API 工具，用于学术论文搜索和引用分析

OpenAlex: 免费开放的学术元数据 API，CC0 许可，271M+ 论文。
Polite pool（提供 email）可获得 10 req/s 速率。
文档: https://docs.openalex.org/
"""
import json
import logging
import os
import re
import time
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org"
MAX_RETRIES = 3
BASE_DELAY = 1  # 秒
_MIN_INTERVAL = 0.15  # polite pool 10 req/s → 100ms 间隔，留余量
_last_request_time = 0.0
_SEMANTIC_MIN_INTERVAL = 1.0  # semantic search 限制 1 req/s
_last_semantic_time = 0.0


def _get_params_base() -> dict:
    """返回基础查询参数（含 API key 和 polite pool email）"""
    params = {}
    api_key = os.environ.get("OPENALEX_API_KEY", "")
    if api_key:
        params["api_key"] = api_key
    email = os.environ.get("OPENALEX_EMAIL", "")
    if email:
        params["mailto"] = email
    return params


def _rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()


def _semantic_rate_limit():
    """semantic search 专用限流：1 req/s（官方限制）"""
    global _last_semantic_time
    elapsed = time.time() - _last_semantic_time
    if elapsed < _SEMANTIC_MIN_INTERVAL:
        time.sleep(_SEMANTIC_MIN_INTERVAL - elapsed)
    _last_semantic_time = time.time()


def _request_with_retry(url: str, params: dict) -> dict:
    """带限流和指数退避重试的 GET 请求"""
    for attempt in range(MAX_RETRIES):
        _rate_limit()
        try:
            resp = requests.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                delay = BASE_DELAY * (2 ** attempt)
                logger.warning(f"OpenAlex request error: {e}, retry {attempt+1} after {delay}s")
                time.sleep(delay)
                continue
            raise
        if resp.status_code == 429:
            delay = BASE_DELAY * (2 ** attempt)
            logger.warning(f"OpenAlex 429, retry {attempt+1}/{MAX_RETRIES} after {delay}s")
            time.sleep(delay)
            continue
        if resp.status_code == 400:
            # 返回错误信息而非抛异常，让 Agent 可以调整 query 重试
            error_detail = ""
            try:
                error_detail = resp.json().get("message", resp.text[:200])
            except Exception:
                error_detail = resp.text[:200]
            return {"error": f"400 Bad Request: {error_detail}", "results": []}
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(
        f"OpenAlex API {MAX_RETRIES} 次重试后仍失败。"
        f"请改用 web_search 搜索 'query site:arxiv.org' 作为替代。"
    )


def _extract_arxiv_id(work: dict) -> str:
    """从 OpenAlex work 对象提取 ArXiv ID"""
    # 方法1: 从 ids.doi 提取 (arXiv DOI 格式: 10.48550/arXiv.2106.13008)
    doi = (work.get("ids") or {}).get("doi", "") or work.get("doi", "") or ""
    m = re.search(r"arXiv\.(\d{4}\.\d{4,5}(?:v\d+)?)", doi, re.IGNORECASE)
    if m:
        return m.group(1)

    # 方法2: 从 locations 中找 arXiv source
    for loc in work.get("locations") or []:
        source = loc.get("source") or {}
        if "arxiv" in (source.get("display_name") or "").lower():
            landing_url = loc.get("landing_page_url") or ""
            m = re.search(r"arxiv\.org/abs/(\d{4}\.\d{4,5}(?:v\d+)?)", landing_url)
            if m:
                return m.group(1)

    # 方法3: 从 primary_location
    primary = work.get("primary_location") or {}
    landing = primary.get("landing_page_url") or ""
    m = re.search(r"arxiv\.org/abs/(\d{4}\.\d{4,5}(?:v\d+)?)", landing)
    if m:
        return m.group(1)

    return ""


def _extract_open_access_url(work: dict) -> str:
    """提取开放获取 PDF URL"""
    oa = work.get("open_access") or {}
    url = oa.get("oa_url") or ""
    if url:
        return url
    # 从 best_oa_location 取
    best = work.get("best_oa_location") or {}
    return best.get("pdf_url") or best.get("landing_page_url") or ""


def _normalize_work(work: dict, include_abstract: bool = False) -> dict:
    """将 OpenAlex work 对象标准化为与 S2 兼容的格式"""
    arxiv_id = _extract_arxiv_id(work)
    oa_url = _extract_open_access_url(work)

    # 提取作者（取前 5 个）
    authorships = work.get("authorships") or []
    authors = []
    for a in authorships[:5]:
        author_info = a.get("author") or {}
        name = author_info.get("display_name", "")
        if name:
            authors.append(name)

    # venue: 从 primary_location.source 提取
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    venue = source.get("display_name") or ""

    # OpenAlex ID
    openalex_id = (work.get("ids") or {}).get("openalex", "") or work.get("id", "")
    # 提取短 ID (W开头的数字)
    if openalex_id and "/" in openalex_id:
        openalex_id = openalex_id.rsplit("/", 1)[-1]

    result = {
        "paperId": openalex_id,
        "title": work.get("display_name") or work.get("title", ""),
        "year": work.get("publication_year"),
        "citationCount": work.get("cited_by_count", 0),
        "venue": venue,
        "authors": [{"name": n} for n in authors],
        "externalIds": {},
        "url": f"https://openalex.org/works/{openalex_id}",
    }

    # abstract: 从 abstract_inverted_index 重建
    if include_abstract:
        abstract = _reconstruct_abstract(work)
        if abstract:
            result["abstract"] = abstract

    # topics
    topics = work.get("topics") or []
    if topics:
        result["topics"] = [
            {"id": (t.get("id") or "").rsplit("/", 1)[-1],
             "name": t.get("display_name", "")}
            for t in topics[:3]
        ]

    if arxiv_id:
        result["externalIds"]["ArXiv"] = arxiv_id
        result["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
        result["arxiv_pdf"] = f"https://arxiv.org/pdf/{arxiv_id}"

    doi = work.get("doi") or (work.get("ids") or {}).get("doi", "")
    if doi:
        # 去掉 https://doi.org/ 前缀
        if doi.startswith("https://doi.org/"):
            doi = doi[len("https://doi.org/"):]
        result["externalIds"]["DOI"] = doi

    if oa_url:
        result["openAccessPdf"] = {"url": oa_url}

    return result


def _reconstruct_abstract(work: dict) -> str:
    """从 abstract_inverted_index 重建摘要文本"""
    inv_index = work.get("abstract_inverted_index")
    if not inv_index:
        return ""
    # inv_index: {"word": [pos1, pos2, ...], ...}
    positions = {}
    for word, pos_list in inv_index.items():
        for pos in pos_list:
            positions[pos] = word
    if not positions:
        return ""
    max_pos = max(positions.keys())
    words = [positions.get(i, "") for i in range(max_pos + 1)]
    return " ".join(words)


def _build_year_filter(year_range: str) -> str:
    """安全构建年份过滤条件"""
    if not year_range:
        return ""
    year_range = year_range.strip()
    # "2023-" → from_publication_date:2023-01-01
    if year_range.endswith("-"):
        year = year_range[:-1].strip()
        return f"from_publication_date:{year}-01-01"
    # "2019-2024" → from_publication_date:2019-01-01,to_publication_date:2024-12-31
    if "-" in year_range:
        parts = year_range.split("-", 1)
        start, end = parts[0].strip(), parts[1].strip()
        return f"from_publication_date:{start}-01-01,to_publication_date:{end}-12-31"
    # "2023" → publication_year:2023
    return f"publication_year:{year_range}"


def search_topics(query: str, limit: int = 5) -> str:
    """搜索 OpenAlex Topics，返回 topic ID 和名称。

    用于两步搜索：先用 search_topics 找到领域 topic ID，
    再用 search_papers(topic_id=...) 在该领域内精确搜索。

    Args:
        query: 搜索词（如 "time series forecasting"）
        limit: 返回数量（默认 5）
    """
    params = _get_params_base()
    params["search"] = query
    params["per_page"] = min(limit, 25)
    params["select"] = "id,display_name,works_count,description"

    data = _request_with_retry(f"{BASE_URL}/topics", params)
    if "error" in data:
        return json.dumps(data, ensure_ascii=False)

    results = []
    for t in data.get("results", [])[:limit]:
        tid = (t.get("id") or "").rsplit("/", 1)[-1]
        results.append({
            "topic_id": tid,
            "name": t.get("display_name", ""),
            "works_count": t.get("works_count", 0),
            "description": (t.get("description") or "")[:200],
        })
    return json.dumps(results, indent=2, ensure_ascii=False)


def search_papers(query: str, limit: int = 10,
                  min_citations: int = 0, year_range: str = "",
                  sort: str = "relevance",
                  topic_id: str = "",
                  include_abstract: bool = False,
                  search_mode: str = "keyword") -> str:
    """搜索论文（OpenAlex API）

    推荐用法（两步搜索，精度最高）：
    1. 先调 search_topics("time series forecasting") 获取 topic_id
    2. 再调 search_papers(query="diffusion", topic_id="T12205") 在该 topic 内搜索

    Args:
        query: 搜索词。keyword 模式建议 2-4 个英文词；semantic 模式可用长自然语言描述；
               支持引号精确短语如 '"mean reversion" forecasting'、近邻 "A B"~5、通配符 machin*、Boolean AND/NOT
        limit: 返回数量（上限 200，semantic 模式上限 50）
        min_citations: 最低引用数过滤（默认 0 不过滤）
        year_range: 年份范围，如 "2023-"（2023至今） "2019-2024" "2023"（仅2023）
        sort: 排序方式，relevance（默认）/ citationCount:desc / publicationDate:desc
        topic_id: OpenAlex Topic ID（如 T12205），限定在该领域内搜索，大幅提高相关性
        include_abstract: 是否返回摘要（默认 False，True 时返回数据量更大）
        search_mode: 搜索模式 - "keyword"（默认，关键词搜索）/ "semantic"（语义搜索，适合长描述）/ "exact"（精确匹配，不做词干化）
    """
    # semantic 模式额外限流
    if search_mode == "semantic":
        _semantic_rate_limit()
        limit = min(limit, 50)  # semantic 搜索上限 50

    params = _get_params_base()

    # 根据 search_mode 设置不同的搜索参数
    if search_mode == "semantic":
        params["search.semantic"] = query
    elif search_mode == "exact":
        params["search.exact"] = query
    else:
        params["search"] = query

    params["per_page"] = min(limit, 200)

    # 构建 filter
    filters = ["type:article|preprint"]
    if topic_id:
        # topic_id 可能带不带前缀
        if not topic_id.startswith("T"):
            topic_id = f"T{topic_id}"
        filters.append(f"topics.id:{topic_id}")
    if min_citations > 0:
        filters.append(f"cited_by_count:>{min_citations - 1}")
    year_filter = _build_year_filter(year_range)
    if year_filter:
        filters.append(year_filter)
    params["filter"] = ",".join(filters)

    # 排序映射
    sort_map = {
        "citationCount:desc": "cited_by_count:desc",
        "citationCount:asc": "cited_by_count:asc",
        "publicationDate:desc": "publication_date:desc",
        "publicationDate:asc": "publication_date:asc",
        "relevance": "relevance_score:desc",
    }
    params["sort"] = sort_map.get(sort, "cited_by_count:desc")

    # 请求的字段
    select_fields = (
        "id,ids,doi,display_name,title,publication_year,cited_by_count,"
        "authorships,primary_location,locations,open_access,best_oa_location,"
        "referenced_works,topics"
    )
    if include_abstract:
        select_fields += ",abstract_inverted_index"
    params["select"] = select_fields

    url = f"{BASE_URL}/works"
    data = _request_with_retry(url, params)

    # 处理 400 等错误
    if "error" in data and not data.get("results"):
        return json.dumps({"error": data["error"], "hint": "尝试缩短 query 或移除 year_range"}, ensure_ascii=False)

    works = data.get("results", [])[:limit]
    papers = [_normalize_work(w, include_abstract=include_abstract) for w in works]
    return json.dumps(papers, indent=2, ensure_ascii=False)


def get_paper_references(paper_id: str, limit: int = 20) -> str:
    """获取论文引用的其他论文（参考文献）

    Args:
        paper_id: OpenAlex work ID（如 W2741809807）
    """
    # 先获取论文本身的 referenced_works 列表
    params = _get_params_base()
    params["select"] = "id,referenced_works"
    url = f"{BASE_URL}/works/{paper_id}"
    work = _request_with_retry(url, params)

    ref_ids = work.get("referenced_works", [])
    if not ref_ids:
        return json.dumps([], indent=2)

    # 批量获取引用的论文详情（用 filter=openalex:id1|id2|...）
    # OpenAlex 支持 OR 查询，但 URL 长度有限，分批
    ref_ids = ref_ids[:limit]
    # 提取短 ID
    short_ids = []
    for rid in ref_ids:
        if "/" in rid:
            short_ids.append(rid.rsplit("/", 1)[-1])
        else:
            short_ids.append(rid)

    params2 = _get_params_base()
    params2["filter"] = f"openalex:{'|'.join(short_ids)}"
    params2["per_page"] = limit
    params2["select"] = "id,ids,doi,display_name,title,publication_year,cited_by_count,authorships,primary_location,locations,open_access,best_oa_location"

    data = _request_with_retry(f"{BASE_URL}/works", params2)
    works = data.get("results", [])

    refs = [{"citedPaper": _normalize_work(w)} for w in works]
    return json.dumps(refs, indent=2, ensure_ascii=False)


def get_paper_citations(paper_id: str, limit: int = 20) -> str:
    """获取引用了该论文的论文列表

    Args:
        paper_id: OpenAlex work ID（如 W2741809807）
    """
    params = _get_params_base()
    params["filter"] = f"cites:{paper_id}"
    params["per_page"] = limit
    params["sort"] = "cited_by_count:desc"
    params["select"] = "id,ids,doi,display_name,title,publication_year,cited_by_count,authorships,primary_location,locations,open_access,best_oa_location"

    data = _request_with_retry(f"{BASE_URL}/works", params)
    works = data.get("results", [])[:limit]

    cits = [{"citingPaper": _normalize_work(w)} for w in works]
    return json.dumps(cits, indent=2, ensure_ascii=False)
