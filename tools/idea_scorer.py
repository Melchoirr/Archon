"""Idea 评分工具：文献检索 + LLM 评审，对 ideation 产出进行质量把关"""
import json
import logging
import os

from tools.openalex import search_papers
from agents.base_agent import llm_call_with_retry
from shared.models.research_tree import Score
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
    """对每个 query 调用 search_papers，去重合并"""
    seen_ids = set()
    results = []
    for query in queries:
        try:
            raw = search_papers(query, limit=5, year_range="2022-")
            papers = json.loads(raw)
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
                    })
        except Exception as e:
            logger.warning(f"搜索 '{query}' 失败: {e}")
    return results


def score_idea(client, model: str, proposal_text: str,
               prior_work: list, topic_title: str) -> dict:
    """单次 LLM 调用，结构化评分"""
    pw_text = ""
    if prior_work:
        for i, p in enumerate(prior_work[:10], 1):
            arxiv = f", arXiv:{p['arxiv_id']}" if p.get("arxiv_id") else ""
            pw_text += f"{i}. {p['title']} ({p.get('year', '?')}, {p.get('citation_count', 0)} citations{arxiv})\n"
    else:
        pw_text = "未找到高度相关的先前工作。"

    resp = llm_call_with_retry(
        client,
        model=model,
        max_tokens=500,
        messages=[{"role": "user", "content": SCORE_PROMPT.format(
            topic_title=topic_title,
            proposal=proposal_text[:8000],
            prior_work=pw_text,
        )}],
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
                     prior_work: list, rank: int, total: int):
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
        "## 检索到的相关工作",
    ]

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
                    tree_service=None, paths=None) -> list[dict]:
    """遍历所有 proposed 状态的 idea，逐个评分。

    Args:
        tree_service: ResearchTreeService 实例
        paths: PathManager 实例
    """
    tree = tree_service.load()
    ideas = tree.root.ideas
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

        # Step 2: 文献检索
        prior_work = search_prior_work(queries)
        logger.info(f"  {idea.id} 找到 {len(prior_work)} 篇相关论文")

        # Step 3: 评分
        scores = score_idea(client, model, proposal_text, prior_work, topic_title)

        scored.append({
            "idea_id": idea.id,
            "title": idea.title,
            "composite": scores["composite"],
            "scores": scores,
            "prior_work": prior_work,
            "idea_dir": str(idea_dir),
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
        )

        # 更新 tree 中的 idea
        for tree_idea in tree.root.ideas:
            if tree_idea.id == item["idea_id"]:
                tree_idea.scores = Score(
                    novelty=item["scores"].get("novelty", 3),
                    significance=item["scores"].get("significance", 3),
                    feasibility=item["scores"].get("feasibility", 3),
                    alignment=item["scores"].get("alignment", 3),
                    rank=rank,
                )
                tree_idea.status = IdeaStatus(item["status"])
                break

    tree_service.save(tree)
    return scored
