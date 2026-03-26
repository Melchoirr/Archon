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


def search_prior_work(queries: list[str], proposal_text: str = "") -> list[dict]:
    """两轮搜索：keyword + semantic fallback，提高召回覆盖度。"""
    seen_ids = set()
    results = []

    def _collect(raw: str):
        papers = json.loads(raw)
        if isinstance(papers, dict) and "error" in papers:
            return
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

    # 第一轮：keyword 搜索
    for query in queries:
        try:
            _collect(search_papers(query, limit=8, year_range="2022-",
                                   include_abstract=True))
        except Exception as e:
            logger.warning(f"搜索 '{query}' 失败: {e}")

    # 第二轮：semantic 搜索兜底（结果不足时用 proposal 原文做语义检索）
    if len(results) < 5 and proposal_text:
        try:
            logger.info("  keyword 结果不足，启用 semantic 搜索兜底")
            _collect(search_papers(proposal_text[:500], limit=10,
                                   year_range="2020-", include_abstract=True,
                                   search_mode="semantic"))
        except Exception as e:
            logger.warning(f"semantic 搜索失败: {e}")

    return results


OVERLAP_LEVELS = ("duplicate", "high", "medium", "low", "none")

PAIRWISE_PROMPT = """你是学术创新性审查专家。请深入分析以下 Research Proposal 与已有论文的方法重叠程度。

## Research Proposal
{proposal}

## 已有论文
标题: {paper_title}
摘要: {paper_abstract}

请从以下维度逐一分析：
1. **问题定义**：两者解决的是否是同一个问题？问题的表述和范围是否相同？
2. **核心方法**：技术路线是否相同或高度相似？关键算法/模型/框架是否一致？
3. **创新增量**：如果方法有相似之处，Proposal 是否在关键环节有实质性的新贡献（而非仅换数据集/微调参数）？
4. **总体判断**：给出 overlap 等级

overlap 等级定义：
- duplicate: 核心方法完全相同，无实质新贡献
- high: 核心方法高度相似，仅有边际改进
- medium: 共享部分关键技术，但有明显差异化贡献
- low: 同一领域但技术路线不同
- none: 问题或领域都不同

请以 JSON 返回（reason 字段请详细说明分析过程）:
{{"overlap": "none|low|medium|high|duplicate",
  "reason": "详细分析：问题定义异同 → 方法对比 → 创新增量判断",
  "shared_method": "共享的核心方法（如有，否则为空字符串）"}}
只返回 JSON，不要其他内容。"""


def _pairwise_novelty_check(client, model: str, proposal_text: str,
                            prior_work: list[dict], max_papers: int = 5) -> dict:
    """对 top-N 有 abstract 的论文，逐篇让 LLM 判断方法重叠度。

    Returns:
        {
            "max_overlap": "none"|"low"|"medium"|"high"|"duplicate",
            "overlapping_papers": [{title, overlap, reason, shared_method}, ...],
        }
    """
    import re

    # 筛选有 abstract 的论文
    papers = [p for p in prior_work if p.get("abstract", "") and len(p["abstract"]) > 100]
    papers = papers[:max_papers]

    if not papers:
        logger.info("  无可用 abstract，跳过 pairwise 对比")
        return {"max_overlap": "none", "overlapping_papers": []}

    overlapping = []
    for p in papers:
        prompt = PAIRWISE_PROMPT.format(
            proposal=proposal_text[:6000],
            paper_title=p["title"],
            paper_abstract=p["abstract"][:2000],
        )
        try:
            resp = llm_call_with_retry(
                client, model=model, max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                match = re.search(r'\{.*\}', text, re.DOTALL)
                result = json.loads(match.group()) if match else None

            if result and result.get("overlap") in OVERLAP_LEVELS:
                overlapping.append({
                    "title": p["title"],
                    "overlap": result["overlap"],
                    "reason": result.get("reason", ""),
                    "shared_method": result.get("shared_method", ""),
                })
                logger.info(f"  vs '{p['title'][:50]}' → {result['overlap']}")
            else:
                logger.warning(f"  pairwise 解析失败: {text[:200]}")
                overlapping.append({
                    "title": p["title"], "overlap": "low",
                    "reason": "解析失败，默认 low", "shared_method": "",
                })
        except Exception as e:
            logger.warning(f"  pairwise 对比失败 '{p['title'][:40]}': {e}")
            overlapping.append({
                "title": p["title"], "overlap": "low",
                "reason": f"调用失败: {e}", "shared_method": "",
            })

    # 取最高 overlap 等级
    max_overlap = "none"
    for item in overlapping:
        ol = item["overlap"]
        if ol in OVERLAP_LEVELS and OVERLAP_LEVELS.index(ol) < OVERLAP_LEVELS.index(max_overlap):
            max_overlap = ol

    if max_overlap in ("duplicate", "high"):
        titles = [i["title"][:50] for i in overlapping if i["overlap"] in ("duplicate", "high")]
        logger.warning(f"  高重叠论文: {', '.join(titles)}")

    return {"max_overlap": max_overlap, "overlapping_papers": overlapping}


def score_idea(client, model: str, proposal_text: str,
               prior_work: list, topic_title: str,
               pairwise_info: dict = None) -> dict:
    """单次 LLM 调用，结构化评分。结合 pairwise 创新性对比结果。"""
    import re

    pw_text = ""
    if prior_work:
        # 构建 pairwise 结果索引（按标题查找）
        pw_overlaps = {}
        if pairwise_info:
            for item in pairwise_info.get("overlapping_papers", []):
                pw_overlaps[item["title"]] = item

        for i, p in enumerate(prior_work[:10], 1):
            arxiv = f", arXiv:{p['arxiv_id']}" if p.get("arxiv_id") else ""
            pw_text += f"{i}. {p['title']} ({p.get('year', '?')}, {p.get('citation_count', 0)} citations{arxiv})\n"
            # 加入 abstract 摘要
            abstract = p.get("abstract", "")
            if abstract:
                pw_text += f"   摘要: {abstract[:300]}...\n"
            # 加入 pairwise 对比结果
            overlap_item = pw_overlaps.get(p["title"])
            if overlap_item:
                pw_text += f"   方法重叠度: **{overlap_item['overlap']}** — {overlap_item['reason'][:200]}\n"
            pw_text += "\n"
    else:
        pw_text = "未找到高度相关的先前工作。"

    # 如果有 pairwise 发现高重叠，在 prompt 中强调
    novelty_warning = ""
    if pairwise_info:
        max_ol = pairwise_info.get("max_overlap", "none")
        if max_ol == "duplicate":
            novelty_warning = (
                "\n\n## 创新性预警（必须参考）\n"
                "⚠️ Pairwise 对比发现核心方法与已有论文**完全重复**，Novelty 不应超过 1 分。\n"
            )
        elif max_ol == "high":
            novelty_warning = (
                "\n\n## 创新性预警（必须参考）\n"
                "⚠️ Pairwise 对比发现核心方法与已有论文**高度相似**，Novelty 不应超过 2 分。\n"
            )
        elif max_ol == "medium":
            novelty_warning = (
                "\n\n## 创新性提示\n"
                "Pairwise 对比发现与已有工作共享部分关键技术，Novelty 建议 2-3 分。\n"
            )

    prompt_content = SCORE_PROMPT.format(
        topic_title=topic_title,
        proposal=proposal_text[:8000],
        prior_work=pw_text + novelty_warning,
    )

    resp = llm_call_with_retry(
        client, model=model, max_tokens=1024,
        messages=[{"role": "user", "content": prompt_content}],
    )
    text = resp.content[0].text.strip()

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

    # Pairwise 硬约束：高重叠时强制压低 novelty
    if pairwise_info:
        max_ol = pairwise_info.get("max_overlap", "none")
        # 找到触发硬约束的论文标题
        high_papers = [i for i in pairwise_info.get("overlapping_papers", [])
                       if i["overlap"] in ("duplicate", "high")]
        cap_title = high_papers[0]["title"][:50] if high_papers else ""

        if max_ol == "duplicate" and scores.get("novelty", 3) > 1:
            logger.info(f"  Pairwise 强制: novelty {scores['novelty']} -> 1 (duplicate)")
            scores["novelty"] = 1
            if "rationale" in scores:
                scores["rationale"]["novelty"] = f"与 '{cap_title}' 核心方法完全重复"
        elif max_ol == "high" and scores.get("novelty", 3) > 2:
            logger.info(f"  Pairwise 强制: novelty {scores['novelty']} -> 2 (high overlap)")
            scores["novelty"] = 2
            if "rationale" in scores:
                scores["rationale"]["novelty"] = f"与 '{cap_title}' 核心方法高度相似"
        elif max_ol == "medium" and scores.get("novelty", 3) > 3:
            logger.info(f"  Pairwise 压低: novelty {scores['novelty']} -> 3 (medium overlap)")
            scores["novelty"] = 3

        scores["max_overlap"] = max_ol

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
                     pairwise_info: dict = None):
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

    # Pairwise 创新性对比信息
    if pairwise_info and pairwise_info.get("overlapping_papers"):
        max_ol = pairwise_info.get("max_overlap", "none")
        lines.extend([
            "## 创新性对比 (Pairwise)",
            f"- 最高重叠等级: **{max_ol}**",
            "",
            "| 论文 | 重叠度 | 分析 |",
            "|------|--------|------|",
        ])
        for item in pairwise_info["overlapping_papers"]:
            reason_short = item["reason"][:100].replace("|", "/").replace("\n", " ")
            lines.append(f"| {item['title'][:60]} | {item['overlap']} | {reason_short} |")
        lines.append("")

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

        # Step 2: 文献检索（keyword + semantic 兜底）
        prior_work = search_prior_work(queries, proposal_text=proposal_text)
        logger.info(f"  {idea.id} 找到 {len(prior_work)} 篇相关论文")

        # Step 2.5: LLM Pairwise 创新性对比
        pairwise_info = _pairwise_novelty_check(client, model, proposal_text, prior_work)

        # Step 3: LLM 评分（将 pairwise 结果传入）
        scores = score_idea(client, model, proposal_text, prior_work,
                            topic_title, pairwise_info=pairwise_info)

        scored.append({
            "idea_id": idea.id,
            "title": idea.title,
            "composite": scores["composite"],
            "scores": scores,
            "prior_work": prior_work,
            "idea_dir": str(idea_dir),
            "max_overlap": pairwise_info.get("max_overlap", "none"),
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
            pairwise_info=pairwise_info,
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
