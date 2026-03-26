"""Idea 评分工具：文献检索 + LLM 评审，对 ideation 产出进行质量把关"""
import json
import logging
import os

from tools.openalex import search_papers
from agents.base_agent import llm_call_with_retry
from shared.models.idea_registry import Score
from shared.models.enums import IdeaStatus

logger = logging.getLogger(__name__)

EXTRACT_QUERIES_PROMPT = """你是学术搜索专家。根据以下研究 idea proposal，提取 2-3 个最能验证其新颖性的英文搜索查询。

## Proposal
{proposal}

要求：
- 每个查询应覆盖 proposal 核心方法的不同方面
- 使用英文学术关键词
- 查询应能找到与该 idea 最相似的已有工作

请以 JSON 数组格式返回，例如: ["query1", "query2", "query3"]
只返回 JSON 数组，不要其他内容。"""

SCORE_PROMPT = """你是 AI 科研评审专家。请对以下研究 idea 进行结构化评分。

## 研究课题
{topic_title}

## Idea Proposal
{proposal}

## 检索到的相关工作
{prior_work}

## 评分维度（各 1-5 分）

| 维度 | 权重 | 1 分锚点 | 5 分锚点 |
|------|------|----------|----------|
| Novelty | 0.35 | 已有论文描述了完全相同的方法 | 未找到任何相关先前工作 |
| Significance | 0.35 | 增量改进，<5% 提升预期 | 可能改变该领域的范式 |
| Feasibility | 0.20 | 需要全新基础设施 | 在现有代码上直接扩展 |
| Alignment | 0.10 | 与课题只有间接关联 | 直接解决课题核心问题 |

请严格按以下 JSON 格式返回评分结果，不要包含其他内容：
{{
  "novelty": <1-5>,
  "significance": <1-5>,
  "feasibility": <1-5>,
  "alignment": <1-5>,
  "rationale": {{
    "novelty": "一句话理由",
    "significance": "一句话理由",
    "feasibility": "一句话理由",
    "alignment": "一句话理由"
  }},
  "recommendation": "推荐深入 / 降低优先级 / 保持观察 / 建议合并到 IXXX"
}}"""


def extract_search_queries(client, model: str, proposal_text: str) -> list[str]:
    """单次 LLM 调用，从 proposal 提取 2-3 个英文搜索查询"""
    resp = llm_call_with_retry(
        client,
        model=model,
        max_tokens=300,
        messages=[{"role": "user", "content": EXTRACT_QUERIES_PROMPT.format(proposal=proposal_text[:8000])}],
    )
    text = resp.content[0].text.strip()
    try:
        queries = json.loads(text)
        if isinstance(queries, list):
            return [q for q in queries if isinstance(q, str)][:3]
    except json.JSONDecodeError:
        pass
    import re
    match = re.search(r'\[.*?\]', text, re.DOTALL)
    if match:
        try:
            queries = json.loads(match.group())
            return [q for q in queries if isinstance(q, str)][:3]
        except json.JSONDecodeError:
            pass
    logger.warning(f"无法解析搜索查询，使用 fallback: {text[:100]}")
    return [proposal_text[:100]]


def search_prior_work(queries: list[str]) -> list[dict]:
    """对每个 query 调用 search_papers（含 abstract），去重合并"""
    seen_ids = set()
    results = []
    for query in queries:
        try:
            raw = search_papers(query, limit=5, year_range="2022-",
                                include_abstract=True)
            papers = json.loads(raw)
            if isinstance(papers, dict) and "error" in papers:
                continue
            for p in papers:
                pid = p.get("paperId", "")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    results.append({
                        "title": p.get("title", ""),
                        "year": p.get("year"),
                        "citation_count": p.get("citationCount", 0),
                        "arxiv_id": p.get("externalIds", {}).get("ArXiv", ""),
                        "venue": p.get("venue", ""),
                        "abstract": p.get("abstract", ""),
                    })
        except Exception as e:
            logger.warning(f"搜索 '{query}' 失败: {e}")
    return results


SIMILARITY_HIGH = 0.85   # 高度重复阈值
SIMILARITY_MEDIUM = 0.75  # 中度相似阈值


def _compute_embedding_similarity(proposal_text: str,
                                  prior_work: list[dict]) -> dict:
    """计算 proposal 与 prior_work abstracts 的 embedding 相似度。

    Returns:
        {
            "max_similarity": float,
            "max_similar_paper": str,  # 最相似论文标题
            "high_similarity_papers": [...],  # >= SIMILARITY_HIGH 的论文
            "similarities": [...],  # 每篇论文的相似度
        }
    """
    from tools.embedding import compute_max_similarity

    # 收集有 abstract 的论文
    abstracts = []
    papers_with_abstract = []
    for pw in prior_work:
        abstract = pw.get("abstract", "")
        if abstract and len(abstract) > 50:
            abstracts.append(abstract)
            papers_with_abstract.append(pw)

    if not abstracts:
        logger.info("  无可用 abstract，跳过 embedding 相似度检测")
        return {"max_similarity": 0.0, "max_similar_paper": "",
                "high_similarity_papers": [], "similarities": []}

    max_sim, max_idx, all_sims = compute_max_similarity(
        proposal_text, abstracts, dimensions=1024)

    result = {
        "max_similarity": round(max_sim, 4),
        "max_similar_paper": papers_with_abstract[max_idx]["title"] if max_idx >= 0 else "",
        "high_similarity_papers": [],
        "similarities": [round(s, 4) for s in all_sims],
    }

    for i, sim in enumerate(all_sims):
        if sim >= SIMILARITY_HIGH:
            result["high_similarity_papers"].append({
                "title": papers_with_abstract[i]["title"],
                "similarity": round(sim, 4),
            })

    if result["high_similarity_papers"]:
        titles = ", ".join(p["title"][:50] for p in result["high_similarity_papers"])
        logger.warning(f"  高度相似论文: {titles}")
    elif max_sim >= SIMILARITY_MEDIUM:
        logger.info(f"  最高相似度: {max_sim:.3f} ({result['max_similar_paper'][:50]})")
    else:
        logger.info(f"  最高相似度: {max_sim:.3f}（较低，新颖性好）")

    return result


def score_idea(client, model: str, proposal_text: str,
               prior_work: list, topic_title: str,
               similarity_info: dict = None) -> dict:
    """单次 LLM 调用，结构化评分。结合 embedding 相似度信息。"""
    pw_text = ""
    if prior_work:
        for i, p in enumerate(prior_work[:10], 1):
            arxiv = f", arXiv:{p['arxiv_id']}" if p.get("arxiv_id") else ""
            pw_text += f"{i}. {p['title']} ({p.get('year', '?')}, {p.get('citation_count', 0)} citations{arxiv})\n"
    else:
        pw_text = "未找到高度相关的先前工作。"

    # 将 embedding 相似度结果加入 prompt
    sim_text = ""
    if similarity_info:
        max_sim = similarity_info.get("max_similarity", 0)
        high_papers = similarity_info.get("high_similarity_papers", [])
        if high_papers:
            sim_text = (
                f"\n\n## Embedding 相似度分析（客观指标，必须参考）\n"
                f"⚠️ 以下论文与本 proposal 的 embedding cosine similarity >= {SIMILARITY_HIGH}，"
                f"说明方法高度重复，Novelty 不应超过 2 分：\n"
            )
            for hp in high_papers:
                sim_text += f"- {hp['title']} (similarity={hp['similarity']})\n"
        elif max_sim >= SIMILARITY_MEDIUM:
            sim_text = (
                f"\n\n## Embedding 相似度分析\n"
                f"最相似论文: {similarity_info.get('max_similar_paper', '')}\n"
                f"相似度: {max_sim:.3f}（中等相似，Novelty 建议 2-3 分）\n"
            )
        else:
            sim_text = (
                f"\n\n## Embedding 相似度分析\n"
                f"最高相似度: {max_sim:.3f}（较低，未发现高度相似工作）\n"
            )

    prompt_content = SCORE_PROMPT.format(
        topic_title=topic_title,
        proposal=proposal_text[:8000],
        prior_work=pw_text + sim_text,
    )

    resp = llm_call_with_retry(
        client,
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": prompt_content}],
    )
    text = resp.content[0].text.strip()

    import re
    try:
        scores = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                scores = json.loads(match.group())
            except json.JSONDecodeError:
                logger.warning(f"无法解析评分结果: {text[:200]}")
                scores = {"novelty": 3, "significance": 3, "feasibility": 3, "alignment": 3,
                          "rationale": {"novelty": "解析失败", "significance": "解析失败",
                                        "feasibility": "解析失败", "alignment": "解析失败"},
                          "recommendation": "需人工评审"}
        else:
            scores = {"novelty": 3, "significance": 3, "feasibility": 3, "alignment": 3,
                      "rationale": {"novelty": "解析失败", "significance": "解析失败",
                                    "feasibility": "解析失败", "alignment": "解析失败"},
                      "recommendation": "需人工评审"}

    # Embedding 相似度硬约束：高相似度时强制压低 novelty
    if similarity_info:
        max_sim = similarity_info.get("max_similarity", 0)
        if max_sim >= SIMILARITY_HIGH and scores.get("novelty", 3) > 2:
            logger.info(f"  Embedding 强制: novelty {scores['novelty']} -> 2 (sim={max_sim:.3f})")
            scores["novelty"] = 2
            if "rationale" in scores:
                scores["rationale"]["novelty"] = (
                    f"Embedding 相似度 {max_sim:.3f} >= {SIMILARITY_HIGH}，"
                    f"与 '{similarity_info.get('max_similar_paper', '')[:50]}' 高度重复"
                )
        elif max_sim >= SIMILARITY_MEDIUM and scores.get("novelty", 3) > 3:
            logger.info(f"  Embedding 压低: novelty {scores['novelty']} -> 3 (sim={max_sim:.3f})")
            scores["novelty"] = 3
        scores["max_similarity"] = round(max_sim, 4)

    # 用 Score 模型校验并计算 composite
    try:
        score_model = Score(
            novelty=scores.get("novelty", 3),
            significance=scores.get("significance", 3),
            feasibility=scores.get("feasibility", 3),
            alignment=scores.get("alignment", 3),
        )
        scores["composite"] = score_model.composite
    except Exception:
        n = scores.get("novelty", 3)
        s = scores.get("significance", 3)
        f = scores.get("feasibility", 3)
        a = scores.get("alignment", 3)
        scores["composite"] = round(0.35 * n + 0.35 * s + 0.20 * f + 0.10 * a, 2)

    return scores


def _write_review_md(idea_dir: str, idea_title: str, scores: dict,
                     prior_work: list, rank: int, total: int,
                     max_similarity: float = 0.0):
    """写入 review.md"""
    rationale = scores.get("rationale", {})
    rec = scores.get("recommendation", "")

    lines = [
        f"# Review: {idea_title}",
        "",
        "## Scores",
        "| 维度 | 分数 | 理由 |",
        "|------|------|------|",
        f"| Novelty | {scores.get('novelty', '?')}/5 | {rationale.get('novelty', '')} |",
        f"| Significance | {scores.get('significance', '?')}/5 | {rationale.get('significance', '')} |",
        f"| Feasibility | {scores.get('feasibility', '?')}/5 | {rationale.get('feasibility', '')} |",
        f"| Alignment | {scores.get('alignment', '?')}/5 | {rationale.get('alignment', '')} |",
        f"| **综合** | **{scores.get('composite', '?')}** | Rank: {rank}/{total} |",
        "",
    ]

    # Embedding 相似度信息
    if max_similarity > 0:
        level = "高度重复" if max_similarity >= SIMILARITY_HIGH else (
            "中度相似" if max_similarity >= SIMILARITY_MEDIUM else "较低")
        lines.extend([
            "## Embedding 相似度",
            f"- 最高 cosine similarity: **{max_similarity:.3f}** ({level})",
            f"- 阈值: >={SIMILARITY_HIGH} 高度重复, >={SIMILARITY_MEDIUM} 中度相似",
            "",
        ])

    lines.append("## 检索到的相关工作")

    if prior_work:
        for p in prior_work[:8]:
            arxiv = f", arXiv:{p['arxiv_id']}" if p.get("arxiv_id") else ""
            lines.append(f"- {p['title']} ({p.get('year', '?')}, {p.get('citation_count', 0)} citations{arxiv})")
    else:
        lines.append("- 未找到高度相关的先前工作")

    lines.extend(["", "## 建议", rec, ""])

    os.makedirs(idea_dir, exist_ok=True)
    with open(os.path.join(idea_dir, "review.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def score_all_ideas(topic_dir: str, client, model: str, topic_title: str,
                    registry=None, paths=None) -> list[dict]:
    """遍历所有 proposed 状态的 idea，逐个评分。

    Args:
        registry: IdeaRegistryService 实例
        paths: PathManager 实例
    """
    registry_data = registry.load()
    ideas = registry_data.ideas
    if not ideas:
        logger.warning("无 idea，跳过评分")
        return []

    scored = []
    for idea in ideas:
        if idea.status != IdeaStatus.proposed:
            logger.info(f"跳过 {idea.id}（状态: {idea.status}）")
            continue

        # 通过 PathManager 找到 idea 目录
        idea_dir = paths.idea_dir(idea.id) if paths else None
        if not idea_dir:
            logger.warning(f"未找到 {idea.id} 的目录，跳过")
            continue

        proposal_path = idea_dir / "proposal.md"
        if not proposal_path.exists():
            logger.warning(f"未找到 {proposal_path}，跳过")
            continue

        proposal_text = proposal_path.read_text(encoding="utf-8")

        print(f"    评分 {idea.id}: {idea.title[:40]}...")

        # Step 1: 提取搜索查询
        queries = extract_search_queries(client, model, proposal_text)
        logger.info(f"  {idea.id} 搜索查询: {queries}")

        # Step 2: 文献检索（含 abstract）
        prior_work = search_prior_work(queries)
        logger.info(f"  {idea.id} 找到 {len(prior_work)} 篇相关论文")

        # Step 2.5: Embedding 相似度检测
        similarity_info = _compute_embedding_similarity(proposal_text, prior_work)

        # Step 3: LLM 评分（将相似度信息传入）
        scores = score_idea(client, model, proposal_text, prior_work,
                            topic_title, similarity_info=similarity_info)

        scored.append({
            "idea_id": idea.id,
            "title": idea.title,
            "composite": scores["composite"],
            "scores": scores,
            "prior_work": prior_work,
            "idea_dir": str(idea_dir),
            "max_similarity": similarity_info.get("max_similarity", 0.0),
        })

    # 排序并分配 rank
    scored.sort(key=lambda x: x["composite"], reverse=True)
    for rank, item in enumerate(scored, 1):
        item["rank"] = rank
        item["scores"]["rank"] = rank

        # 状态更新
        composite = item["composite"]
        if composite >= 3.5:
            item["status"] = "recommended"
        elif composite < 2.5:
            item["status"] = "deprioritized"
        else:
            item["status"] = "proposed"

        # 写 review.md
        _write_review_md(
            item["idea_dir"], item["title"], item["scores"],
            item["prior_work"], rank, len(scored),
            max_similarity=item.get("max_similarity", 0.0),
        )

        # 更新 registry 中的 idea
        registry.update_idea_scores(item["idea_id"], {
            "novelty": item["scores"].get("novelty", 3),
            "significance": item["scores"].get("significance", 3),
            "feasibility": item["scores"].get("feasibility", 3),
            "alignment": item["scores"].get("alignment", 3),
            "rank": rank,
        })
        registry.update_idea_status(item["idea_id"], item["status"])
    return scored
