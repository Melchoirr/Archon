#!/usr/bin/env python3
"""
AI 驱动的时序预测科研自动化系统 - 主入口

Idea ID 格式: T001-I001（全局唯一，两级编码：topic + idea）

用法:
    python run_research.py --topic boosting.md                  # 从 md 初始化 + 启动 FSM
    python run_research.py --topic T001                         # 恢复 topic 级 FSM
    python run_research.py --topic T001 --auto                  # 全自动运行
    python run_research.py --idea T001-I001                     # 单 idea FSM
    python run_research.py --idea T001-I001 --auto              # 单 idea 全自动
    python run_research.py --idea T001-I001 --from refine       # 从指定阶段开始
    python run_research.py --idea T001-I001 --force conclude    # 强制跳转状态
    python run_research.py --status [--topic T001]              # 查看 FSM 状态
    python run_research.py --history [--topic T001] [--idea T001-I001]  # 转换历史
    python run_research.py --memory [--tags t1,t2] [--phase p]  # 查询经验
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


# ── 工具函数 ──────────────────────────────────────────────────

def _parse_idea_ref(ref: str) -> tuple:
    """Parse idea reference. Returns (topic_id, idea_id) or (topic_id, None)."""
    if "-I" in ref:
        parts = ref.split("-", 1)
        return (parts[0], parts[1])  # ("T001", "I001")
    elif ref.startswith("T"):
        return (ref, None)
    return (None, ref)


def _find_topic_dir(topic_id: str = None) -> str | None:
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


def _find_topic_dir_by_md(md_ref: str) -> str | None:
    """根据 md 文件名查找已初始化的 topic 目录。"""
    basename = os.path.basename(md_ref)
    stem = os.path.splitext(basename)[0].lower()
    stem_clean = re.sub(r'[^a-zA-Z0-9_-]', '_', stem)

    topics_dir = "topics"
    if not os.path.exists(topics_dir):
        return None
    for d in sorted(os.listdir(topics_dir)):
        if d.startswith("T") and os.path.isdir(os.path.join(topics_dir, d)):
            if stem_clean in d.lower():
                return os.path.join(topics_dir, d)
    return None


def _parse_topic_md(md_path: str) -> dict:
    """解析 topic markdown 文件，提取结构化信息。"""
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    result = {"title": "", "domain": "", "keywords": [], "description": "", "scope": ""}

    h1 = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if h1:
        result["title"] = h1.group(1).strip()

    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
    for section in sections[1:]:
        lines = section.strip().split("\n")
        header = lines[0].strip().lower()
        body = "\n".join(lines[1:]).strip()

        if "领域" in header or "domain" in header:
            result["domain"] = body.strip()
        elif "关键词" in header or "keyword" in header:
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


def _make_topic_brief(title: str, md_path: str = None) -> str:
    """从标题或 md 文件名生成简短目录名（纯 ASCII）"""
    if md_path:
        basename = os.path.basename(md_path)
        name = os.path.splitext(basename)[0]
        name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
        if name and len(name) >= 2:
            return name.lower()

    words = re.findall(r'[a-zA-Z]+', title)
    if len(words) >= 2:
        return "_".join(w.lower() for w in words[:4])

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


def _get_fsm(topic_id: str = None, auto: bool = False):
    """获取 FSM 实例"""
    from agents.fsm_engine import ResearchFSM
    from shared.paths import PathManager
    from tools.research_tree import ResearchTreeService

    topic_dir = _find_topic_dir(topic_id) if topic_id else _find_topic_dir()
    if not topic_dir:
        print("ERROR: 未找到 topic 目录，请先用 --topic xxx.md 初始化")
        sys.exit(1)

    config_path = os.path.join(topic_dir, "config.yaml")
    if not os.path.exists(config_path):
        print(f"ERROR: 找不到配置文件: {config_path}")
        print(f"  请确认 topic 目录完整，或重新用 --topic xxx.md 初始化")
        sys.exit(1)

    project_root = os.path.dirname(os.path.abspath(__file__))
    paths = PathManager(project_root, topic_dir)
    tree_service = ResearchTreeService(paths)
    return ResearchFSM(paths, tree_service, config_path, auto=auto)


# ── 初始化 ────────────────────────────────────────────────────

def do_init(md_ref: str) -> str:
    """从 topic md 文件初始化项目，返回 topic_id。"""
    from tools.research_tree import ResearchTreeService
    from shared.paths import PathManager
    from shared.models.research_tree import ResearchTree, ResearchRoot

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

    # 查找 md 文件
    md_path = md_ref
    if not os.path.exists(md_path):
        md_path = os.path.join("topics", md_ref)
    if not os.path.exists(md_path):
        md_path = os.path.join("topics", md_ref + ".md")
    if not os.path.exists(md_path):
        print(f"  ERROR: 找不到 topic 文件: {md_ref}")
        sys.exit(1)

    # 解析 md
    topic_info = _parse_topic_md(md_path)
    if not topic_info["title"]:
        print(f"  ERROR: md 文件中没有找到 # 标题")
        sys.exit(1)

    print(f"  读取课题文件: {md_path}")
    print(f"  标题: {topic_info['title']}")
    print(f"  领域: {topic_info['domain']}")
    print(f"  关键词: {topic_info['keywords']}")

    # 分配 topic 编号
    project_root = os.path.dirname(os.path.abspath(__file__))
    _pm = PathManager(project_root)
    _ts = ResearchTreeService(_pm)
    topic_id = _ts.next_topic_id()
    brief = _make_topic_brief(topic_info["title"], md_path)
    topic_dir = os.path.join("topics", f"{topic_id}_{brief}")
    os.makedirs(topic_dir, exist_ok=True)

    # 创建 topic 子目录
    for d in ["survey/papers", "ideas", "phase_logs"]:
        os.makedirs(os.path.join(topic_dir, d), exist_ok=True)
        print(f"  Created {topic_dir}/{d}/")

    # 复制原始 md
    import shutil
    shutil.copy2(md_path, os.path.join(topic_dir, "topic_spec.md"))
    print(f"  Copied {md_path} -> {topic_dir}/topic_spec.md")

    # 创建 config.yaml
    config = {
        "topic": {
            "title": topic_info["title"],
            "domain": topic_info["domain"],
            "keywords": topic_info["keywords"],
        },
        "project": {"name": brief},
        "llm": {
            "provider": "minimax",
            "sdk": "anthropic",
            "base_url": "https://api.minimaxi.com/anthropic",
            "default_model": "MiniMax-M2.5",
            "fast_model": "MiniMax-M2.1-highspeed",
            "max_tokens": 8192,
        },
        "environment": {"conda_env": "agent", "python": "3.10"},
        "datasets": {},
        "search": {
            "openalex_api": "https://api.openalex.org",
            "web_search_engine": "duckduckgo",
        },
    }

    config_path = os.path.join(topic_dir, "config.yaml")
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # 创建 research_tree.yaml
    tree = ResearchTree(root=ResearchRoot(
        topic_id=topic_id,
        topic_brief=brief,
        topic=topic_info["title"],
        description=topic_info["description"],
    ))
    topic_paths = PathManager(project_root, topic_dir)
    topic_ts = ResearchTreeService(topic_paths)
    topic_ts.save(tree)

    print(f"\n  Topic ID: {topic_id}")
    print(f"  目录: {topic_dir}/")
    print(f"  课题: {topic_info['title']}")

    print("\nVerifying environment...")
    _verify_environment()
    print("\nInitialization complete!")
    return topic_id


# ── 辅助查询 ──────────────────────────────────────────────────

def do_status(topic_id: str = None):
    """显示 FSM 状态"""
    fsm = _get_fsm(topic_id)
    print(fsm.status())


def do_history(topic_id: str = None, idea_ref: str = None):
    """显示状态转换历史"""
    idea_id = None
    if idea_ref:
        tid, idea_id = _parse_idea_ref(idea_ref)
        topic_id = topic_id or tid

    fsm = _get_fsm(topic_id)
    records = fsm.history(idea_id)
    if not records:
        print("无转换历史")
        return
    for r in records[-20:]:
        idea_str = f" [{r.idea_id}]" if r.idea_id else ""
        print(f"  {r.timestamp[:19]}{idea_str} "
              f"{r.from_state} → {r.to_state} ({r.trigger})")


def do_memory(tags: str = None, phase: str = None, idea: str = None, topic_id: str = None):
    """查询经验记忆"""
    from tools.memory import query_memory
    result = query_memory(
        tags=tags or "",
        phase=phase or "",
        idea_id=idea or "",
        topic_id=topic_id or "",
    )
    print(result)


# ── 主入口 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AI-Driven Research Automation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s --topic boosting.md                  # 初始化 + 交互式运行
  %(prog)s --topic boosting.md --auto           # 初始化 + 全自动运行
  %(prog)s --topic T001                         # 恢复 topic 级 FSM
  %(prog)s --idea T001-I001                     # 单 idea FSM
  %(prog)s --idea T001-I001 --auto              # 单 idea 全自动
  %(prog)s --idea T001-I001 --from refine       # 从指定阶段开始
  %(prog)s --idea T001-I001 --force conclude    # 强制跳转状态
  %(prog)s --status                             # 查看 FSM 状态
  %(prog)s --history --idea T001-I001           # 查看转换历史
  %(prog)s --memory --tags hyperparameter       # 查询经验
""",
    )

    # 运行参数
    parser.add_argument("--topic", type=str, default=None,
                        help="Topic md 文件（初始化）或 Topic ID（恢复运行）")
    parser.add_argument("--idea", type=str, default=None,
                        help="Idea ID (e.g. T001-I001)")
    parser.add_argument("--auto", action="store_true",
                        help="全自动运行，跳过用户确认")
    parser.add_argument("--from", type=str, default=None, dest="from_state",
                        help="从指定状态开始")
    parser.add_argument("--force", type=str, default=None,
                        help="强制跳转到指定状态")
    parser.add_argument("--feedback", type=str, default="",
                        help="强制跳转时的 feedback")

    # 辅助查询
    parser.add_argument("--status", action="store_true", help="查看 FSM 状态")
    parser.add_argument("--history", action="store_true", help="查看状态转换历史")
    parser.add_argument("--memory", action="store_true", help="查询经验记忆")
    parser.add_argument("--tags", type=str, default=None, help="Memory: 标签过滤")
    parser.add_argument("--phase", type=str, default=None, help="Memory: 阶段过滤")

    args = parser.parse_args()

    # ── 辅助查询 ──
    if args.status:
        topic_id = args.topic if args.topic and not args.topic.endswith(".md") else None
        do_status(topic_id)
        return

    if args.history:
        topic_id = args.topic if args.topic and not args.topic.endswith(".md") else None
        do_history(topic_id, args.idea)
        return

    if args.memory:
        topic_id = args.topic if args.topic and not args.topic.endswith(".md") else None
        do_memory(tags=args.tags, phase=args.phase, idea=args.idea, topic_id=topic_id)
        return

    # ── 无参数：打印帮助 ──
    if not args.topic and not args.idea:
        parser.print_help()
        return

    # ── 初始化（.md 文件） ──
    topic_id = None
    if args.topic and args.topic.endswith(".md"):
        # 检查是否已初始化
        topic_dir = _find_topic_dir_by_md(args.topic)
        if topic_dir:
            topic_id_match = re.match(r"(T\d+)", os.path.basename(topic_dir))
            if topic_id_match:
                topic_id = topic_id_match.group(1)
                print(f"已存在 topic 目录: {topic_dir} ({topic_id})，跳过初始化")
        if not topic_id:
            topic_id = do_init(args.topic)
    elif args.topic:
        topic_id = args.topic

    # ── 从 idea ref 推断 topic_id ──
    idea_id = None
    if args.idea:
        tid, idea_id = _parse_idea_ref(args.idea)
        topic_id = topic_id or tid

    # ── 强制跳转 ──
    if args.force and idea_id:
        fsm = _get_fsm(topic_id, auto=args.auto)
        fsm.force_transition(idea_id, args.force, feedback=args.feedback)
        print(f"强制跳转到 {args.force}")
        return

    # ── 运行 FSM ──
    fsm = _get_fsm(topic_id, auto=args.auto)

    if idea_id:
        result = fsm.run_idea(idea_id, start_state=args.from_state)
        print(f"\nFSM 运行完成:\n{result}")
    else:
        result = fsm.run_topic(start_state=args.from_state)
        print(f"\nFSM 运行完成:\n{result}")


if __name__ == "__main__":
    main()
