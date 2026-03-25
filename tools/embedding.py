"""文本 Embedding 工具：调用智谱 Embedding-3 API 计算向量和相似度"""
import logging
import os
import requests
import numpy as np

logger = logging.getLogger(__name__)

ZHIPU_EMBEDDING_URL = "https://open.bigmodel.cn/api/paas/v4/embeddings"
EMBEDDING_MODEL = "embedding-3"
MAX_BATCH = 16  # 智谱单次最多 16 条


def _get_api_key() -> str:
    return os.environ.get("ZHIPU_API_KEY", "")


def get_embeddings(texts: list[str], dimensions: int = 1024) -> list[list[float]] | None:
    """批量获取文本向量。

    Args:
        texts: 待编码文本列表
        dimensions: 向量维度（256/512/1024/2048），越小越快

    Returns:
        向量列表，失败返回 None
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("ZHIPU_API_KEY 未设置，无法计算 embedding")
        return None

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    all_embeddings = []

    for i in range(0, len(texts), MAX_BATCH):
        batch = texts[i:i + MAX_BATCH]
        # 截断过长文本（embedding-3 最大 8192 tokens ≈ 16K 字符）
        batch = [t[:16000] for t in batch]
        try:
            resp = requests.post(
                ZHIPU_EMBEDDING_URL,
                headers=headers,
                json={"model": EMBEDDING_MODEL, "input": batch, "dimensions": dimensions},
                timeout=30,
            )
            data = resp.json()
            if "data" in data and data["data"]:
                # 按 index 排序确保顺序
                sorted_data = sorted(data["data"], key=lambda x: x.get("index", 0))
                all_embeddings.extend([d["embedding"] for d in sorted_data])
            else:
                logger.warning(f"Embedding API 返回异常: {data}")
                return None
        except Exception as e:
            logger.warning(f"Embedding API 调用失败: {e}")
            return None

    return all_embeddings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度"""
    va = np.array(a)
    vb = np.array(b)
    dot = np.dot(va, vb)
    norm = np.linalg.norm(va) * np.linalg.norm(vb)
    if norm == 0:
        return 0.0
    return float(dot / norm)


def compute_max_similarity(query_text: str, candidate_texts: list[str],
                           dimensions: int = 1024) -> tuple[float, int, list[float]]:
    """计算 query 与一组 candidate 文本的最大余弦相似度。

    Args:
        query_text: 查询文本（如 proposal）
        candidate_texts: 候选文本列表（如论文 abstract 列表）
        dimensions: embedding 维度

    Returns:
        (max_similarity, max_index, all_similarities)
        如果 embedding 失败，返回 (0.0, -1, [])
    """
    if not candidate_texts:
        return 0.0, -1, []

    # 把 query 和所有 candidates 一次性编码
    all_texts = [query_text] + candidate_texts
    embeddings = get_embeddings(all_texts, dimensions=dimensions)
    if not embeddings or len(embeddings) != len(all_texts):
        return 0.0, -1, []

    query_emb = embeddings[0]
    similarities = [cosine_similarity(query_emb, emb) for emb in embeddings[1:]]

    if not similarities:
        return 0.0, -1, []

    max_sim = max(similarities)
    max_idx = similarities.index(max_sim)
    return max_sim, max_idx, similarities
