"""网页搜索工具，使用 DuckDuckGo（免费，无需 API key）"""
import json
import warnings
warnings.filterwarnings("ignore", message=".*renamed.*ddgs.*")


def web_search(query: str, max_results: int = 10) -> str:
    """使用 DuckDuckGo 搜索网页"""
    # 优先用新包名 ddgs，fallback 到旧包名
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS

    try:
        results = DDGS().text(query, max_results=max_results)
        if results:
            return json.dumps(results, indent=2, ensure_ascii=False)
        return json.dumps({"error": "No results found", "query": query})
    except Exception as e:
        return json.dumps({"error": str(e), "query": query})
