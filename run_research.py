#!/usr/bin/env python3
"""
AI 驱动的时序预测科研自动化系统 - 主入口（重构版）

Idea ID 格式: T001-I001（全局唯一，两级编码：topic + idea）

用法:
    python run_research.py init --topic mean_reversion.md   # 从 topics/ 下的 md 文件初始化
    python run_research.py elaborate [--topic T001] [--ref-topics T002,T003]
    python run_research.py survey [--round N] [--topic T001]
    python run_research.py ideation [--topic T001]
    python run_research.py refine --idea T001-I001 [--ref-ideas T001-I002,T002-I003] [--ref-topics T002]
    python run_research.py code-ref --idea T001-I001
    python run_research.py code --idea T001-I001 [--ref-ideas T001-I002]
    python run_research.py experiment --idea T001-I001 [--step S01] [--version V2] [--max-iter 3]
    python run_research.py analyze --idea T001-I001 [--step S01] [--version V1]
    python run_research.py conclude --idea T001-I001 [--ref-ideas T001-I002,T002-I003]
    python run_research.py status [--topic T001]
    python run_research.py memory [--tags t1,t2] [--phase p] [--idea id] [--topic-id T001]
    python run_research.py auto --idea T001-I001 [--start refine] [--ref-ideas T001-I002] [--max-iter 3]

引用格式:
    --ref-ideas T001-I001,T002-I003   引用特定 idea
    --ref-ideas T001                   引用 T001 下的所有 idea
"""
import argparse
import json
import logging
import os
import re
import sys
import yaml


# 加载 .env 文件
def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip().upper(), value.strip())


_load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
for noisy in ["httpx", "anthropic", "primp", "duckduckgo_search", "urllib3"]:
    logging.getLogger(noisy).setLevel(logging.WARNING)
logger = logging.getLogger("research")


def _parse_idea_ref(ref: str) -> tuple:
    """Parse idea reference. Returns (topic_id, idea_id) or (topic_id, None) for all ideas."""
    if "-I" in ref:
        parts = ref.split("-", 1)
        return (parts[0], parts[1])  # ("T001", "I001")
    elif ref.startswith("T"):
        return (ref, None)  # ("T001", None) = all ideas
    return (None, ref)  # legacy fallback


def _parse_ref_list(ref_str: str) -> list:
    """解析逗号分隔的引用列表，支持 T001-I001 和 T001（全 topic）格式"""
    if not ref_str:
        return None
    return [r.strip() for r in ref_str.split(",") if r.strip()]


def _find_topic_dir(topic_id: str = None) -> str:
    """查找 topic 目录"""
    topics_dir = "topics"
    if not os.path.exists(topics_dir):
        return None
    if topic_id:
        for d in os.listdir(topics_dir):
            if d.startswith(topic_id):
                return os.path.join(topics_dir, d)
        return None
    # 返回最新的
    dirs = sorted([d for d in os.listdir(topics_dir)
                   if d.startswith("T") and os.path.isdir(os.path.join(topics_dir, d))])
    if dirs:
        return os.path.join(topics_dir, dirs[-1])
    return None


def _parse_topic_md(md_path: str) -> dict:
    """解析 topic markdown 文件，提取结构化信息。

    支持的 section:
      # 标题          → title
      ## 领域          → domain
      ## 关键词        → keywords (列表)
      ## 描述          → description (多行文本)
      ## 范围          → scope (多行文本)

    Returns:
        {"title": str, "domain": str, "keywords": list, "description": str, "scope": str}
    """
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    result = {"title": "", "domain": "", "keywords": [], "description": "", "scope": ""}

    # 提取 h1 标题
    h1 = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if h1:
        result["title"] = h1.group(1).strip()

    # 按 ## 分割 section
    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
    for section in sections[1:]:  # 跳过 h1 之前的部分
        lines = section.strip().split("\n")
        header = lines[0].strip().lower()
        body = "\n".join(lines[1:]).strip()

        if "领域" in header or "domain" in header:
            result["domain"] = body.strip()
        elif "关键词" in header or "keyword" in header:
            # 解析列表项
            result["keywords"] = [
                line.lstrip("- ").strip()
                for line in body.split("\n")
                if line.strip() and line.strip().startswith("-")
            ]
        elif "描述" in header or "description" in header:
            result["description"] = body
        elif "范围" in header or "scope" in header:
            result["scope"] = body

    return result


def cmd_init(args):
    """初始化项目：从 topic md 文件创建 topic 目录和研究树。

    用法:
      1. 在 topics/ 下创建 md 文件（参考 topics/mean_reversion.md 模板）
      2. python run_research.py init --topic mean_reversion.md
    """
    from tools.research_tree import next_topic_id, _save_tree

    print("Initializing project...")

    # 创建全局目录
    global_dirs = [
        "knowledge/papers/pdf", "knowledge/papers/parsed",
        "knowledge/papers/summaries", "knowledge/repos",
        "knowledge/dataset_cards",
        "shared/data", "shared/utils", "shared/baselines",
        "memory", "topics",
    ]
    for d in global_dirs:
        os.makedirs(d, exist_ok=True)

    # 初始化记忆文件
    for fname, content in [
        ("memory/insights.md", "# Research Insights\n\n"),
        ("memory/failed_ideas.md", "# Failed Ideas Log\n\n"),
    ]:
        if not os.path.exists(fname):
            with open(fname, "w") as f:
                f.write(content)

    if not args.topic:
        print("\n  用法: 先在 topics/ 下创建课题 md 文件，然后:")
        print("    python run_research.py init --topic mean_reversion.md")
        print("\n  md 文件模板（参考 topics/mean_reversion.md）:")
        print("    # 课题标题")
        print("    ## 领域")
        print("    ## 关键词")
        print("    ## 描述")
        print("    ## 范围")
        _verify_environment()
        return

    # 查找 md 文件：支持直接路径或 topics/ 下的文件名
    md_path = args.topic
    if not os.path.exists(md_path):
        md_path = os.path.join("topics", args.topic)
    if not os.path.exists(md_path):
        # 尝试不带 .md 后缀
        md_path = os.path.join("topics", args.topic + ".md")
    if not os.path.exists(md_path):
        print(f"  ERROR: 找不到 topic 文件: {args.topic}")
        print(f"  尝试过的路径: {args.topic}, topics/{args.topic}, topics/{args.topic}.md")
        return

    # 解析 md 文件
    topic_info = _parse_topic_md(md_path)
    if not topic_info["title"]:
        print(f"  ERROR: md 文件中没有找到 # 标题")
        return

    print(f"  读取课题文件: {md_path}")
    print(f"  标题: {topic_info['title']}")
    print(f"  领域: {topic_info['domain']}")
    print(f"  关键词: {topic_info['keywords']}")

    # 分配 topic 编号
    topic_id = next_topic_id()
    brief = _make_topic_brief(topic_info["title"], md_path)
    topic_dir = os.path.join("topics", f"{topic_id}_{brief}")
    os.makedirs(topic_dir, exist_ok=True)

    # 创建 topic 子目录
    topic_subdirs = [
        "survey/papers", "ideas", "phase_logs",
    ]
    for d in topic_subdirs:
        os.makedirs(os.path.join(topic_dir, d), exist_ok=True)
        print(f"  Created {topic_dir}/{d}/")

    # 复制原始 md 到 topic 目录作为 topic_spec.md（仅供 elaborate 阶段参考）
    import shutil
    shutil.copy2(md_path, os.path.join(topic_dir, "topic_spec.md"))
    print(f"  Copied {md_path} -> {topic_dir}/topic_spec.md")
    # context.md 由 elaborate 阶段产出，不从 md 直接生成

    # 创建 topic 级 config.yaml
    config = {
        "topic": {
            "title": topic_info["title"],
            "domain": topic_info["domain"],
            "keywords": topic_info["keywords"],
        },
        "project": {
            "name": brief,
            "author": "zhaodawei",
        },
        "llm": {
            "provider": "minimax",
            "sdk": "anthropic",
            "base_url": "https://api.minimaxi.com/anthropic",
            "default_model": "MiniMax-M2.5",
            "fast_model": "MiniMax-M2.1-highspeed",
            "max_tokens": 4096,
        },
        "environment": {"conda_env": "agent", "python": "3.10"},
        "datasets": {},
        "search": {
            "semantic_scholar_api": "https://api.semanticscholar.org/graph/v1",
            "web_search_engine": "duckduckgo",
        },
    }

    config_path = os.path.join(topic_dir, "config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # 创建 research_tree.yaml
    tree = {
        "root": {
            "topic_id": topic_id,
            "topic_brief": brief,
            "topic": topic_info["title"],
            "description": topic_info["description"],
            "status": "initialized",
            "ideas": [],
            "elaborate": {"status": "pending"},
            "survey": {"rounds": 0, "current_round": 0, "status": "pending"},
        }
    }
    _save_tree(tree, topic_dir)

    print(f"\n  Topic ID: {topic_id}")
    print(f"  目录: {topic_dir}/")
    print(f"  课题: {topic_info['title']}")

    print("\nVerifying environment...")
    _verify_environment()
    print("\nInitialization complete!")


def _make_topic_brief(title: str, md_path: str = None) -> str:
    """从标题或 md 文件名生成简短目录名（纯 ASCII）"""
    # 优先用 md 文件名（去掉 .md 后缀）
    if md_path:
        basename = os.path.basename(md_path)
        name = os.path.splitext(basename)[0]
        # 清理非 ASCII 字符
        name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        if name and len(name) >= 2:
            return name.lower()

    # 从标题提取英文关键词
    words = re.findall(r'[a-zA-Z]+', title)
    if len(words) >= 2:
        return "_".join(w.lower() for w in words[:4])

    # fallback: 用时间戳
    from datetime import datetime
    return f"topic_{datetime.now().strftime('%Y%m%d')}"


def _verify_environment():
    """验证运行环境"""
    api_key = os.environ.get("MINIMAX_API_KEY", "")
    if api_key:
        print(f"  MINIMAX_API_KEY: set ({api_key[:8]}...)")
    else:
        print("  WARNING: MINIMAX_API_KEY not set!")

    zhipu_key = os.environ.get("ZHIPU_API_KEY", "")
    if zhipu_key:
        print(f"  ZHIPU_API_KEY: set ({zhipu_key[:8]}...)")
    else:
        print("  ZHIPU_API_KEY: not set (knowledge base features disabled)")

    deps = ["anthropic", "yaml", "requests", "torch", "numpy", "pandas", "matplotlib"]
    for dep in deps:
        try:
            __import__(dep if dep != "yaml" else "yaml")
            print(f"  {dep}: OK")
        except ImportError:
            print(f"  {dep}: MISSING")

    try:
        from duckduckgo_search import DDGS
        print("  duckduckgo-search: OK")
    except ImportError:
        print("  duckduckgo-search: MISSING")

    if api_key:
        print("\n  Testing MiniMax API...")
        try:
            import anthropic
            client = anthropic.Anthropic(
                api_key=api_key,
                base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic"),
            )
            resp = client.messages.create(
                model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5"),
                max_tokens=10,
                messages=[{"role": "user", "content": "Say 'hello' in one word."}],
            )
            text = "empty"
            for block in resp.content:
                if hasattr(block, "text"):
                    text = block.text
                    break
            print(f"  MiniMax API: OK (response: {text})")
        except Exception as e:
            print(f"  MiniMax API: FAILED - {e}")


def _get_orchestrator(args, topic_id_override: str = None):
    """获取 orchestrator 实例。

    Args:
        args: argparse namespace
        topic_id_override: 从 idea ref 解析出的 topic_id，优先于 args.topic
    """
    from agents.orchestrator import ResearchOrchestrator

    topic_id = topic_id_override or getattr(args, "topic", None)
    topic_dir = _find_topic_dir(topic_id) if topic_id else _find_topic_dir()

    if topic_dir:
        config_path = os.path.join(topic_dir, "config.yaml")
        if not os.path.exists(config_path):
            config_path = "config.yaml"
        return ResearchOrchestrator(topic_dir=topic_dir, config_path=config_path)
    else:
        return ResearchOrchestrator(config_path="config.yaml")


def cmd_elaborate(args):
    """展开调研背景"""
    orch = _get_orchestrator(args)
    ref_topics = _parse_ref_list(args.ref_topics) if hasattr(args, "ref_topics") else None
    result = orch.phase_elaborate(ref_topics=ref_topics)
    print(f"\nElaborate 结果摘要:\n{result[:500]}")


def cmd_survey(args):
    """文献调研"""
    orch = _get_orchestrator(args)
    start_step = getattr(args, "step", 1) or 1
    result = orch.phase_survey(round_num=args.round, start_step=start_step)
    print(f"\nSurvey 结果摘要:\n{result[:500]}")


def cmd_ideation(args):
    """Idea 生成"""
    orch = _get_orchestrator(args)
    result = orch.phase_ideation()
    print(f"\nIdeation 结果摘要:\n{result[:500]}")


def cmd_refine(args):
    """Idea 细化"""
    topic_id, idea_id = _parse_idea_ref(args.idea)
    orch = _get_orchestrator(args, topic_id_override=topic_id)
    ref_ideas = _parse_ref_list(args.ref_ideas)
    ref_topics = _parse_ref_list(args.ref_topics)
    result = orch.phase_refine(idea_id, ref_ideas=ref_ideas, ref_topics=ref_topics)
    print(f"\nRefine 结果摘要:\n{result[:500]}")


def cmd_code_ref(args):
    """代码参考获取"""
    topic_id, idea_id = _parse_idea_ref(args.idea)
    orch = _get_orchestrator(args, topic_id_override=topic_id)
    result = orch.phase_code_reference(idea_id)
    print(f"\nCode-ref 结果摘要:\n{result[:500]}")


def cmd_code(args):
    """代码编写"""
    topic_id, idea_id = _parse_idea_ref(args.idea)
    orch = _get_orchestrator(args, topic_id_override=topic_id)
    ref_ideas = _parse_ref_list(args.ref_ideas)
    result = orch.phase_code(idea_id, ref_ideas=ref_ideas)
    print(f"\nCode 结果摘要:\n{result[:500]}")


def cmd_experiment(args):
    """实验运行"""
    topic_id, idea_id = _parse_idea_ref(args.idea)
    orch = _get_orchestrator(args, topic_id_override=topic_id)
    max_iter = args.max_iter

    if args.version:
        # 单次运行指定版本
        result = orch.phase_experiment(idea_id, step_id=args.step,
                                        version=args.version)
    elif max_iter and max_iter > 1:
        # 迭代循环
        result = orch.phase_experiment_loop(idea_id, step_id=args.step,
                                             max_iter=max_iter)
    else:
        # 默认运行一次
        result = orch.phase_experiment(idea_id, step_id=args.step, version=1)

    print(f"\nExperiment 结果摘要:\n{result[:500]}")


def cmd_analyze(args):
    """分析结果"""
    topic_id, idea_id = _parse_idea_ref(args.idea)
    orch = _get_orchestrator(args, topic_id_override=topic_id)
    result = orch.phase_analyze(idea_id, step_id=args.step, version=args.version)
    print(f"\nAnalyze 结果摘要:\n{result[:500]}")


def cmd_conclude(args):
    """结论总结"""
    topic_id, idea_id = _parse_idea_ref(args.idea)
    orch = _get_orchestrator(args, topic_id_override=topic_id)
    ref_ideas = _parse_ref_list(args.ref_ideas)
    result = orch.phase_conclude(idea_id, ref_ideas=ref_ideas)
    print(f"\nConclude 结果摘要:\n{result[:500]}")


def cmd_status(args):
    """查看状态"""
    orch = _get_orchestrator(args)
    print(orch.status())


def cmd_memory(args):
    """查询记忆"""
    from tools.memory import query_memory
    result = query_memory(
        tags=args.tags or "",
        phase=args.phase or "",
        idea_id=args.idea or "",
        topic_id=args.topic_id or "",
    )
    print(result)


def cmd_auto(args):
    """自动运行模式"""
    topic_id, idea_id = _parse_idea_ref(args.idea)
    orch = _get_orchestrator(args, topic_id_override=topic_id)
    ref_ideas = _parse_ref_list(args.ref_ideas)
    start = args.start or "refine"
    result = orch.phase_auto(idea_id, start_phase=start,
                              ref_ideas=ref_ideas, max_iter=args.max_iter)
    print(f"\nAuto 结果摘要:\n{result[:500]}")


def main():
    parser = argparse.ArgumentParser(
        description="AI-Driven Research Automation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # init
    init_p = subparsers.add_parser("init", help="Initialize project from topic md file")
    init_p.add_argument("--topic", type=str, default=None,
                        help="Topic md file (e.g. mean_reversion.md, searches in topics/)")

    # elaborate
    elaborate_p = subparsers.add_parser("elaborate", help="Elaborate research background")
    elaborate_p.add_argument("--topic", type=str, default=None, help="Topic ID (e.g. T001)")
    elaborate_p.add_argument("--ref-topics", type=str, default=None, help="Reference topics (comma-separated)")

    # survey
    survey_p = subparsers.add_parser("survey", help="Literature survey")
    survey_p.add_argument("--round", type=int, default=1, help="Survey round number")
    survey_p.add_argument("--step", type=int, default=1,
                          help="Start from step N (1=search, 2=download, 3=summarize, 4=repos, 5=synthesize)")
    survey_p.add_argument("--topic", type=str, default=None, help="Topic ID")

    # ideation
    ideation_p = subparsers.add_parser("ideation", help="Generate research ideas")
    ideation_p.add_argument("--topic", type=str, default=None, help="Topic ID")

    # refine
    refine_p = subparsers.add_parser("refine", help="Refine idea with theory and experiment design")
    refine_p.add_argument("--idea", type=str, required=True, help="Idea ID (e.g. T001-I001)")
    refine_p.add_argument("--ref-ideas", type=str, default=None, help="Reference ideas (comma-separated)")
    refine_p.add_argument("--ref-topics", type=str, default=None, help="Reference topics (comma-separated)")
    refine_p.add_argument("--topic", type=str, default=None, help="Topic ID")

    # code-ref
    coderef_p = subparsers.add_parser("code-ref", help="Get code references from papers")
    coderef_p.add_argument("--idea", type=str, required=True, help="Idea ID (e.g. T001-I001)")
    coderef_p.add_argument("--topic", type=str, default=None, help="Topic ID")

    # code
    code_p = subparsers.add_parser("code", help="Write implementation code")
    code_p.add_argument("--idea", type=str, required=True, help="Idea ID (e.g. T001-I001)")
    code_p.add_argument("--ref-ideas", type=str, default=None, help="Reference ideas")
    code_p.add_argument("--topic", type=str, default=None, help="Topic ID")

    # experiment
    exp_p = subparsers.add_parser("experiment", help="Run experiments")
    exp_p.add_argument("--idea", type=str, required=True, help="Idea ID (e.g. T001-I001)")
    exp_p.add_argument("--step", type=str, default=None, help="Step ID (e.g. S01)")
    exp_p.add_argument("--version", type=int, default=None, help="Version number (e.g. 1, 2, 3)")
    exp_p.add_argument("--max-iter", type=int, default=None, help="Max iterations (triggers loop)")
    exp_p.add_argument("--topic", type=str, default=None, help="Topic ID")

    # analyze
    analyze_p = subparsers.add_parser("analyze", help="Analyze experiment results")
    analyze_p.add_argument("--idea", type=str, required=True, help="Idea ID (e.g. T001-I001)")
    analyze_p.add_argument("--step", type=str, default=None, help="Step ID")
    analyze_p.add_argument("--version", type=int, default=None, help="Version number")
    analyze_p.add_argument("--topic", type=str, default=None, help="Topic ID")

    # conclude
    conclude_p = subparsers.add_parser("conclude", help="Generate objective conclusion")
    conclude_p.add_argument("--idea", type=str, required=True, help="Idea ID (e.g. T001-I001)")
    conclude_p.add_argument("--ref-ideas", type=str, default=None, help="Reference ideas")
    conclude_p.add_argument("--topic", type=str, default=None, help="Topic ID")

    # status
    status_p = subparsers.add_parser("status", help="Show research tree status")
    status_p.add_argument("--topic", type=str, default=None, help="Topic ID")

    # memory
    mem_p = subparsers.add_parser("memory", help="Query experience memory")
    mem_p.add_argument("--tags", type=str, default=None, help="Comma-separated tags")
    mem_p.add_argument("--phase", type=str, default=None, help="Phase filter")
    mem_p.add_argument("--idea", type=str, default=None, help="Idea ID filter")
    mem_p.add_argument("--topic-id", type=str, default=None, help="Topic ID filter")

    # auto
    auto_p = subparsers.add_parser("auto", help="Auto-run pipeline for an idea")
    auto_p.add_argument("--idea", type=str, required=True, help="Idea ID (e.g. T001-I001)")
    auto_p.add_argument("--start", type=str, default="refine",
                        help="Starting phase (refine/code_reference/code/experiment_loop/analyze/conclude)")
    auto_p.add_argument("--ref-ideas", type=str, default=None, help="Reference ideas")
    auto_p.add_argument("--max-iter", type=int, default=3, help="Max experiment iterations")
    auto_p.add_argument("--topic", type=str, default=None, help="Topic ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    commands = {
        "init": cmd_init,
        "elaborate": cmd_elaborate,
        "survey": cmd_survey,
        "ideation": cmd_ideation,
        "refine": cmd_refine,
        "code-ref": cmd_code_ref,
        "code": cmd_code,
        "experiment": cmd_experiment,
        "analyze": cmd_analyze,
        "conclude": cmd_conclude,
        "status": cmd_status,
        "memory": cmd_memory,
        "auto": cmd_auto,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
