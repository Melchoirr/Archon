"""Semantic Scholar API 工具，用于学术论文搜索和引用分析

使用 /paper/search/bulk 端点（限流宽松，支持布尔查询语法 AND/OR/NOT）。
建议设置 S2_API_KEY 环境变量以获得更高配额。
申请: https://www.semanticscholar.org/product/api#api-key-form
"""
import json
import logging
import os
import time
import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.semanticscholar.org/graph/v1"
MAX_RETRIES = 5
BASE_DELAY = 2  # 秒
_MIN_INTERVAL = 1.2  # 请求间最小间隔（秒）
_last_request_time = 0.0

# bulk search 支持的字段（不含 tldr）
_SEARCH_FIELDS = "title,abstract,year,citationCount,authors,externalIds,venue,url,openAccessPdf"
# references/citations 返回的字段
_REF_FIELDS = "title,abstract,year,citationCount,authors,externalIds,venue"


def _get_headers() -> dict:
    headers = {}
    api_key = os.environ.get("S2_API_KEY", "")
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def _rate_limit():
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_time = time.time()


def _request_with_retry(url: str, params: dict) -> dict:
    """带限流和指数退避重试的 GET 请求"""
    headers = _get_headers()
    for attempt in range(MAX_RETRIES):
        _rate_limit()
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code == 429:
            delay = BASE_DELAY * (2 ** attempt)
            logger.warning(f"S2 API 429, retry {attempt+1}/{MAX_RETRIES} after {delay}s")
            time.sleep(delay)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return {}


def search_papers(query: str, limit: int = 10,
                  min_citations: int = 0, year_range: str = "",
                  sort: str = "citationCount:desc") -> str:
    """搜索论文（bulk 端点，限流宽松）

    Args:
        query: 搜索词，支持布尔语法（AND/OR/NOT/"短语"）
        limit: 返回数量（上限 1000）
        min_citations: 最低引用数过滤（默认 0 不过滤）
        year_range: 年份范围，如 "2020-" 或 "2019-2024"
        sort: 排序方式，citationCount:desc（默认）/ publicationDate:desc
    """
    url = f"{BASE_URL}/paper/search/bulk"
    params = {
        "query": query,
        "limit": min(limit, 1000),
        "fields": _SEARCH_FIELDS,
        "sort": sort,
    }
    if min_citations > 0:
        params["minCitationCount"] = min_citations
    if year_range:
        params["year"] = year_range

    data = _request_with_retry(url, params)
    papers = data.get("data", [])[:limit]

    # 为每篇论文补充 arxiv_url 方便下载
    for p in papers:
        ext = p.get("externalIds") or {}
        arxiv_id = ext.get("ArXiv")
        if arxiv_id:
            p["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
            p["arxiv_pdf"] = f"https://arxiv.org/pdf/{arxiv_id}"

    return json.dumps(papers, indent=2, ensure_ascii=False)


def get_paper_details(paper_id: str) -> str:
    """获取单篇论文详情（注意：此端点无 key 易 429）

    paper_id 支持: S2 ID, DOI:xxx, ARXIV:xxx, CorpusId:xxx, URL
    """
    url = f"{BASE_URL}/paper/{paper_id}"
    params = {
        "fields": "title,abstract,year,citationCount,referenceCount,authors,venue,externalIds,tldr,url,openAccessPdf",
    }
    data = _request_with_retry(url, params)
    # 补充 arxiv_url
    ext = data.get("externalIds") or {}
    arxiv_id = ext.get("ArXiv")
    if arxiv_id:
        data["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
        data["arxiv_pdf"] = f"https://arxiv.org/pdf/{arxiv_id}"
    return json.dumps(data, indent=2, ensure_ascii=False)


def get_paper_references(paper_id: str, limit: int = 20) -> str:
    """获取论文引用的其他论文"""
    url = f"{BASE_URL}/paper/{paper_id}/references"
    params = {"limit": limit, "fields": _REF_FIELDS}
    data = _request_with_retry(url, params)
    refs = data.get("data", [])
    # 补充 arxiv_url
    for r in refs:
        cp = r.get("citedPaper") or {}
        ext = cp.get("externalIds") or {}
        arxiv_id = ext.get("ArXiv")
        if arxiv_id:
            cp["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
            cp["arxiv_pdf"] = f"https://arxiv.org/pdf/{arxiv_id}"
    return json.dumps(refs, indent=2, ensure_ascii=False)


def get_paper_citations(paper_id: str, limit: int = 20) -> str:
    """获取引用了该论文的论文列表"""
    url = f"{BASE_URL}/paper/{paper_id}/citations"
    params = {"limit": limit, "fields": _REF_FIELDS}
    data = _request_with_retry(url, params)
    cits = data.get("data", [])
    for c in cits:
        cp = c.get("citingPaper") or {}
        ext = cp.get("externalIds") or {}
        arxiv_id = ext.get("ArXiv")
        if arxiv_id:
            cp["arxiv_url"] = f"https://arxiv.org/abs/{arxiv_id}"
            cp["arxiv_pdf"] = f"https://arxiv.org/pdf/{arxiv_id}"
    return json.dumps(cits, indent=2, ensure_ascii=False)


# === Tool Schemas ===

SEARCH_PAPERS_SCHEMA = {
    "description": "在 Semantic Scholar 上搜索论文（bulk 端点，按引用量排序，支持 AND/OR/NOT 布尔语法）",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索词，支持布尔语法如 'transformer AND \"time series\"'"},
            "limit": {"type": "integer", "description": "返回数量（默认10，上限1000）", "default": 10},
            "min_citations": {"type": "integer", "description": "最低引用数过滤（默认0）", "default": 0},
            "year_range": {"type": "string", "description": "年份范围，如 '2020-' 或 '2019-2024'", "default": ""},
            "sort": {"type": "string", "description": "排序: citationCount:desc / publicationDate:desc", "default": "citationCount:desc"},
        },
        "required": ["query"],
    },
}

GET_PAPER_DETAILS_SCHEMA = {
    "description": "获取单篇论文详情（含 tldr 摘要）。paper_id 支持 S2 ID / ARXIV:xxx / DOI:xxx",
    "parameters": {
        "type": "object",
        "properties": {
            "paper_id": {"type": "string", "description": "论文 ID（如 ARXIV:2106.13008）"},
        },
        "required": ["paper_id"],
    },
}

GET_PAPER_REFERENCES_SCHEMA = {
    "description": "获取论文引用的其他论文列表（该论文的参考文献）",
    "parameters": {
        "type": "object",
        "properties": {
            "paper_id": {"type": "string", "description": "论文 ID"},
            "limit": {"type": "integer", "description": "返回数量", "default": 20},
        },
        "required": ["paper_id"],
    },
}

GET_PAPER_CITATIONS_SCHEMA = {
    "description": "获取引用了该论文的论文列表（谁引了它）",
    "parameters": {
        "type": "object",
        "properties": {
            "paper_id": {"type": "string", "description": "论文 ID"},
            "limit": {"type": "integer", "description": "返回数量", "default": 20},
        },
        "required": ["paper_id"],
    },
}
