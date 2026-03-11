"""主编排器：管理研究阶段流转和检查点（重构版：命名式分发、topic 目录、实验迭代）"""
import os
import re
import yaml
import logging

from .literature_agent import LiteratureAgent
from .survey_helpers import make_search_agent, make_repo_agent, make_synthesis_agent, summarize_single_paper
from .data_agent import DataAgent
from .ideation_agent import IdeationAgent
from .design_agent import DesignAgent
from .experiment_agent import ExperimentAgent
from .analysis_agent import AnalysisAgent
from .elaborate_agent import ElaborateAgent
from .refinement_agent import RefinementAgent
from .conclusion_agent import ConclusionAgent
from shared.utils.config_helpers import load_topic_config
from tools.research_tree import (
    read_tree, update_tree, add_idea_to_tree,
    next_topic_id, next_idea_id, next_step_id,
    add_experiment_step, update_iteration,
    _load_tree, _save_tree,
)
from tools.memory import query_memory, add_experience
from tools.file_ops import read_file, write_file
from tools.config_updater import update_config_section
from tools.context_manager import ContextManager
from tools.knowledge_base import KnowledgeBaseManager, search_knowledge_base, SEARCH_KB_SCHEMA
from tools.phase_logger import log_phase_start, log_phase_end

logger = logging.getLogger(__name__)


class ResearchOrchestrator:
    def __init__(self, topic_dir: str = None, config_path: str = None):
        """初始化编排器。

        Args:
            topic_dir: topic 目录路径（如 topics/T001_mean_reversion）。
                       如果为 None，尝试从 config 或现有结构推断。
            config_path: config.yaml 路径。如果为 None，从 topic_dir 推断。
        """
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.topic_dir = topic_dir
        self.default_max_iter = 3

        # 推断 topic_dir 和 config_path
        if topic_dir:
            self.config_path = config_path or os.path.join(topic_dir, "config.yaml")
            if not os.path.exists(self.config_path):
                # 回退到项目根目录的 config
                self.config_path = os.path.join(self.project_root, "config.yaml")
        else:
            self.config_path = config_path or os.path.join(self.project_root, "config.yaml")
            # 尝试找最新的 topic 目录
            self.topic_dir = self._find_latest_topic()

        self._reload_config()

        # 初始化知识库管理器
        self.kb_mgr = KnowledgeBaseManager()

        # 初始化知识库
        self._ensure_knowledge_bases()

        # 初始化上下文管理器
        if self.topic_dir:
            self.ctx = ContextManager(self.topic_dir, self.project_root, self.kb_mgr)
        else:
            self.ctx = None

    def _ensure_knowledge_bases(self):
        """首次运行时创建单一全局知识库（幂等）"""
        if not self.kb_mgr.enabled:
            return
        from tools.knowledge_base import SINGLE_KB_NAME
        self.kb_mgr.get_or_create_kb(SINGLE_KB_NAME, "全局研究知识库")

    def _find_latest_topic(self) -> str:
        """查找最新创建的 topic 目录"""
        topics_dir = os.path.join(self.project_root, "topics")
        if not os.path.exists(topics_dir):
            return None
        topic_dirs = sorted([
            d for d in os.listdir(topics_dir)
            if d.startswith("T") and os.path.isdir(os.path.join(topics_dir, d))
        ])
        if topic_dirs:
            return os.path.join(topics_dir, topic_dirs[-1])
        return None

    def _reload_config(self):
        """重新加载配置"""
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
            self.topic_config = load_topic_config(self.config_path)
        else:
            self.config = {}
            self.topic_config = {
                "topic_title": "(未设置)", "topic_domain": "",
                "search_keywords": [], "dataset_names": "",
                "metric_names": "", "quick_test_desc": "",
                "datasets": {}, "metrics": {}, "experiment": {}, "config": {},
            }

    def _idea_dir(self, idea_id: str) -> str:
        """获取 idea 目录路径"""
        if self.topic_dir:
            ideas_dir = os.path.join(self.topic_dir, "ideas")
        else:
            ideas_dir = os.path.join(self.project_root, "ideas")
        if os.path.exists(ideas_dir):
            for d in os.listdir(ideas_dir):
                if d.startswith(idea_id):
                    return os.path.join(ideas_dir, d)
        return None

    def _step_dir(self, idea_id: str, step_id: str) -> str:
        """获取实验步骤目录"""
        idea_dir = self._idea_dir(idea_id)
        if not idea_dir:
            return None
        results_dir = os.path.join(idea_dir, "results")
        if os.path.exists(results_dir):
            for d in os.listdir(results_dir):
                if d.startswith(step_id):
                    return os.path.join(results_dir, d)
        return None

    def _version_dir(self, idea_id: str, step_id: str, version: int) -> str:
        """获取实验版本目录"""
        step_d = self._step_dir(idea_id, step_id)
        if step_d:
            return os.path.join(step_d, f"V{version}")
        return None

    def _log_phase_start(self, phase: str, idea_id: str = ""):
        """阶段开始日志"""
        if self.topic_dir:
            log_phase_start(phase, self.topic_dir, idea_id)
        logger.info(f"\n\n{'='*60}")
        logger.info(f"  Phase: {phase}" + (f" | Idea: {idea_id}" if idea_id else ""))
        logger.info(f"{'='*60}\n")

    def _log_phase_end(self, phase: str, idea_id: str = "", summary: str = ""):
        """阶段结束日志"""
        if self.topic_dir:
            log_phase_end(phase, self.topic_dir, idea_id, summary, self.kb_mgr)

    # === 阶段方法 ===

    def phase_elaborate(self, ref_topics: list = None) -> str:
        """展开调研背景"""
        self._reload_config()
        self._log_phase_start("elaborate")

        # 确定输出路径
        if self.topic_dir:
            output_path = os.path.join(self.topic_dir, "context.md")
        else:
            output_path = os.path.join(self.project_root, "knowledge", "context.md")

        # 构建上下文
        context = ""
        if self.ctx:
            context = self.ctx.build_context("elaborate", ref_topics=ref_topics)

        agent = ElaborateAgent(self.config_path, output_path)

        prompt = f"开始展开调研背景。\n\n课题: {self.topic_config['topic_title']}\n\n"

        # 读取 topic_spec.md 作为输入线索（不是约束）
        spec_path = os.path.join(self.topic_dir, "topic_spec.md") if self.topic_dir else None
        if spec_path and os.path.exists(spec_path):
            spec_content = read_file(spec_path)
            prompt += f"""以下是用户对课题的初步描述，仅作为线索参考，不要被其限制：

---
{spec_content}
---

注意：以上只是出发点，你需要更广泛地探索问题空间，不要局限于上述描述的方向。

"""
        if context:
            prompt += f"\n{context}\n"
        prompt += f"\n请将结果写入 {output_path}"

        result = agent.run(prompt)

        self._log_phase_end("elaborate", summary=result[:200])

        print(f"\n{'='*60}")
        print(f"Elaborate 完成! 请 review: {output_path}")
        print(f"{'='*60}")
        return result

    def phase_survey(self, round_num: int = 1, start_step: int = 1) -> str:
        """文献调研（流水线版：5 步分步执行，支持断点恢复）

        Args:
            round_num: 调研轮次
            start_step: 从第几步开始（1-5），用于断点恢复
        """
        self._reload_config()
        self._log_phase_start("survey")

        topic_id = self._get_topic_id()

        # 确定输出目录
        summaries_dir = os.path.join(self.project_root, "knowledge", "papers", "summaries")
        os.makedirs(summaries_dir, exist_ok=True)

        if self.topic_dir:
            survey_dir = os.path.join(self.topic_dir, "survey")
            baselines_path = os.path.join(self.topic_dir, "baselines.md")
            datasets_path = os.path.join(self.topic_dir, "datasets.md")
            metrics_path = os.path.join(self.topic_dir, "metrics.md")
        else:
            survey_dir = os.path.join(self.project_root, "knowledge", "survey")
            baselines_path = os.path.join(self.project_root, "knowledge", "baselines.md")
            datasets_path = os.path.join(self.project_root, "knowledge", "datasets.md")
            metrics_path = os.path.join(self.project_root, "knowledge", "metrics.md")

        os.makedirs(survey_dir, exist_ok=True)

        # 加载/初始化进度文件
        progress_path = os.path.join(survey_dir, "progress.yaml")
        progress = self._load_survey_progress(progress_path)
        paper_list_path = os.path.join(survey_dir, "paper_list.yaml")

        def completed(step_key):
            return progress.get(step_key) == "completed"

        # Step 1: 搜索与收集
        if start_step <= 1 and not completed("step1_search"):
            self._survey_step1_search(survey_dir, paper_list_path, round_num, topic_id)
            progress["step1_search"] = "completed"
            self._save_survey_progress(progress, progress_path)

        # Step 2: 下载与解析
        if start_step <= 2 and not completed("step2_download"):
            progress["step2_download"] = "in_progress"
            self._save_survey_progress(progress, progress_path)
            self._survey_step2_download(paper_list_path)
            progress["step2_download"] = "completed"
            self._save_survey_progress(progress, progress_path)

        # Step 3: 逐篇精读总结
        if start_step <= 3 and not completed("step3_summarize"):
            progress["step3_summarize"] = "in_progress"
            self._save_survey_progress(progress, progress_path)
            self._survey_step3_summarize(paper_list_path, summaries_dir, topic_id)
            progress["step3_summarize"] = "completed"
            self._save_survey_progress(progress, progress_path)

        # Step 4: 代码仓库调研
        if start_step <= 4 and not completed("step4_repos"):
            progress["step4_repos"] = "in_progress"
            self._save_survey_progress(progress, progress_path)
            self._survey_step4_repos(survey_dir, summaries_dir)
            progress["step4_repos"] = "completed"
            self._save_survey_progress(progress, progress_path)

        # Step 5: 综合整理
        if start_step <= 5 and not completed("step5_synthesize"):
            progress["step5_synthesize"] = "in_progress"
            self._save_survey_progress(progress, progress_path)
            self._survey_step5_synthesize(survey_dir, summaries_dir,
                                          baselines_path, datasets_path, metrics_path)
            progress["step5_synthesize"] = "completed"
            self._save_survey_progress(progress, progress_path)

        # 确定性后处理：更新全局索引
        try:
            from tools.paper_manager import update_global_index, extract_paper_ids_from_summaries
            paper_ids = extract_paper_ids_from_summaries(summaries_dir, topic_id)
            if paper_ids:
                update_global_index(paper_ids, topic_id)
                self._generate_topic_index(paper_ids, survey_dir)
                print(f"  全局/Topic 级索引已更新")
        except Exception as e:
            logger.warning(f"索引更新失败: {e}")

        # Data Agent 下载数据（无用户确认）
        if os.path.exists(datasets_path):
            print(f"\n{'='*60}")
            print("启动 Data Agent 下载和准备数据集...")
            print(f"{'='*60}")
            data_agent = DataAgent(config_path=self.config_path, datasets_path=datasets_path)
            data_prompt = f"请阅读 {datasets_path}，下载所有推荐的数据集，探查格式，写入 dataset cards，并更新 config.yaml（config_path={self.config_path}）。"
            data_agent.run(data_prompt)
            self._reload_config()

        # 更新研究树
        if self.topic_dir:
            tree = _load_tree(self.topic_dir)
            if tree:
                tree.setdefault("root", {})
                tree["root"]["survey"] = {"status": "completed", "rounds": round_num}
                _save_tree(tree, self.topic_dir)

        add_experience(phase="survey", type="insight",
                       summary=f"Survey 流水线完成（5步），共处理论文见 {paper_list_path}",
                       topic_id=topic_id)
        self._log_phase_end("survey", summary="Survey pipeline completed")

        print(f"\n{'='*60}")
        print("Survey 完成! 请 review:")
        print(f"  - {survey_dir}/")
        print(f"  - {summaries_dir}/ (论文总结)")
        print(f"  - {baselines_path}")
        print(f"  - {datasets_path}")
        print(f"  - {metrics_path}")
        print(f"{'='*60}")
        return "Survey pipeline completed"

    # --- Survey 流水线子步骤 ---

    def _load_survey_progress(self, progress_path: str) -> dict:
        """加载 survey 进度文件"""
        if os.path.exists(progress_path):
            with open(progress_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {
            "step1_search": "pending",
            "step2_download": "pending",
            "step3_summarize": "pending",
            "step4_repos": "pending",
            "step5_synthesize": "pending",
        }

    def _save_survey_progress(self, progress: dict, progress_path: str):
        """保存 survey 进度文件"""
        with open(progress_path, "w", encoding="utf-8") as f:
            yaml.dump(progress, f, allow_unicode=True, default_flow_style=False)

    def _load_paper_list(self, paper_list_path: str) -> list:
        """加载 paper_list.yaml"""
        if os.path.exists(paper_list_path):
            with open(paper_list_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("papers", [])
        return []

    def _save_paper_list(self, papers: list, paper_list_path: str):
        """保存 paper_list.yaml"""
        with open(paper_list_path, "w", encoding="utf-8") as f:
            yaml.dump({"papers": papers}, f, allow_unicode=True, default_flow_style=False)

    def _survey_step1_search(self, survey_dir: str, paper_list_path: str,
                             round_num: int, topic_id: str):
        """Step 1: Agent 搜索论文，产出 paper_list.yaml"""
        print(f"\n{'='*60}")
        print("  Step 1/5: 搜索与收集论文")
        print(f"{'='*60}")

        agent = make_search_agent(self.config_path)

        context = ""
        if self.ctx:
            context = self.ctx.build_context("survey")

        topic = self.topic_config["topic_title"]
        past_exp = query_memory(phase="literature")

        prompt = f"开始搜索论文（第 {round_num} 轮）。\n\n研究课题: {topic}\n\n"
        if context:
            prompt += f"\n{context}\n"
        prompt += f"\n请将论文列表写入 {paper_list_path}\n"
        if round_num > 1:
            prompt += f"\n这是第 {round_num} 轮调研，请扩大搜索范围。先读取已有的 paper_list.yaml 了解已覆盖的论文。"
        if past_exp and "No matching" not in past_exp:
            prompt += f"\n\n历史经验:\n{past_exp}"

        agent.run(prompt)
        print(f"  Step 1 完成: {paper_list_path}")

    def _survey_step2_download(self, paper_list_path: str):
        """Step 2: 确定性下载 PDF + MinerU 解析（0 轮 LLM）"""
        print(f"\n{'='*60}")
        print("  Step 2/5: 下载与解析 PDF")
        print(f"{'='*60}")

        from tools.paper_manager import (
            download_paper, download_paper_by_arxiv, _load_index,
        )
        import time

        papers = self._load_paper_list(paper_list_path)
        if not papers:
            print("  paper_list.yaml 为空，跳过下载")
            return

        total = len(papers)
        for idx, paper in enumerate(papers):
            if paper.get("download_status") in ("downloaded", "no_access"):
                print(f"  [{idx+1}/{total}] {paper.get('title', '')[:50]}... 已处理，跳过")
                continue

            title = paper.get("title", "")
            paper_id = paper.get("paper_id", "")
            arxiv_id = paper.get("arxiv_id") or ""

            print(f"  [{idx+1}/{total}] 下载: {title[:50]}...")

            # 优先用 arxiv_id 直接下载
            if arxiv_id:
                result = download_paper_by_arxiv(arxiv_id, paper_id=paper_id, title=title)
            else:
                # 走 S2 openAccessPdf
                if paper_id:
                    result = download_paper(paper_id, title)
                elif paper.get("open_access_url"):
                    # 有直接 URL 但无 paper_id，跳过（少见情况）
                    paper["download_status"] = "no_id"
                    self._save_paper_list(papers, paper_list_path)
                    continue
                else:
                    paper["download_status"] = "no_source"
                    self._save_paper_list(papers, paper_list_path)
                    continue

            # 判断结果
            if "成功" in result:
                paper["download_status"] = "downloaded"
            elif "没有 Open Access" in result or "下载失败" in result:
                paper["download_status"] = "no_access"
            elif "已下载" in result:
                paper["download_status"] = "downloaded"
            else:
                paper["download_status"] = "failed"
                logger.warning(f"  下载异常: {result[:200]}")

            # 每篇下载后立即更新（崩溃安全）
            self._save_paper_list(papers, paper_list_path)
            time.sleep(2)

        downloaded = sum(1 for p in papers if p.get("download_status") == "downloaded")
        print(f"  Step 2 完成: {downloaded}/{total} 篇已下载")

    def _survey_step3_summarize(self, paper_list_path: str, summaries_dir: str,
                                topic_id: str):
        """Step 3: 逐篇精读总结（每篇 1 次 LLM 调用）"""
        print(f"\n{'='*60}")
        print("  Step 3/5: 逐篇精读总结")
        print(f"{'='*60}")

        import anthropic as _anthropic
        from tools.paper_manager import _load_index, _find_md_file, title_to_slug

        papers = self._load_paper_list(paper_list_path)
        if not papers:
            print("  paper_list.yaml 为空，跳过总结")
            return

        client = _anthropic.Anthropic(
            api_key=os.environ.get("MINIMAX_API_KEY", ""),
            base_url=os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/anthropic"),
        )
        model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
        topic_title = self.topic_config["topic_title"]
        index = _load_index()
        os.makedirs(summaries_dir, exist_ok=True)

        total = len(papers)
        for idx, paper in enumerate(papers):
            if paper.get("summary_status") == "done":
                print(f"  [{idx+1}/{total}] {paper.get('title', '')[:50]}... 已总结，跳过")
                continue

            title = paper.get("title", "unknown")
            paper_id = paper.get("paper_id", "")
            slug = title_to_slug(title)
            summary_path = os.path.join(summaries_dir, f"paper_{slug}.md")

            # 如果总结文件已存在，也标记为完成
            if os.path.exists(summary_path):
                paper["summary_status"] = "done"
                self._save_paper_list(papers, paper_list_path)
                print(f"  [{idx+1}/{total}] {title[:50]}... 总结文件已存在，跳过")
                continue

            print(f"  [{idx+1}/{total}] 总结: {title[:50]}...")

            # 尝试读取 parsed markdown 全文
            paper_text = None
            abstract_only = False

            if paper.get("download_status") == "downloaded" and paper_id:
                # 从 index.yaml 找 md_path
                entry = index.get(paper_id, {})
                md_path = entry.get("md_path")
                if md_path and os.path.exists(md_path):
                    with open(md_path, "r", encoding="utf-8") as f:
                        paper_text = f.read()

            if not paper_text:
                # 没有全文，尝试用 relevance 字段作为简要摘要
                abstract = paper.get("relevance", "")
                if abstract:
                    paper_text = abstract
                    abstract_only = True
                else:
                    paper["summary_status"] = "skipped"
                    self._save_paper_list(papers, paper_list_path)
                    print(f"    无全文也无摘要，跳过")
                    continue

            try:
                summary = summarize_single_paper(
                    client=client,
                    model=model,
                    paper_title=title,
                    paper_text=paper_text,
                    topic_title=topic_title,
                    topic_id=topic_id,
                    abstract_only=abstract_only,
                )
                write_file(summary_path, summary)
                paper["summary_status"] = "done"
                source = "摘要" if abstract_only else "全文"
                print(f"    完成（{source}）→ {summary_path}")
            except Exception as e:
                paper["summary_status"] = "failed"
                logger.warning(f"    总结失败: {e}")

            # 每篇写完后立即更新（崩溃安全）
            self._save_paper_list(papers, paper_list_path)

        done = sum(1 for p in papers if p.get("summary_status") == "done")
        print(f"  Step 3 完成: {done}/{total} 篇已总结")

    def _survey_step4_repos(self, survey_dir: str, summaries_dir: str):
        """Step 4: Agent 搜索和分析代码仓库"""
        print(f"\n{'='*60}")
        print("  Step 4/5: 代码仓库调研")
        print(f"{'='*60}")

        agent = make_repo_agent(self.config_path)
        repos_summary_path = os.path.join(survey_dir, "repos_summary.md")

        prompt = f"""请调研与本课题相关的开源代码仓库。

论文总结目录: {summaries_dir}
请先用 list_directory 查看总结文件，然后读取关键论文的总结，识别有代码的论文。

将调研结果写入 {repos_summary_path}"""

        agent.run(prompt)
        print(f"  Step 4 完成: {repos_summary_path}")

    def _survey_step5_synthesize(self, survey_dir: str, summaries_dir: str,
                                  baselines_path: str, datasets_path: str,
                                  metrics_path: str):
        """Step 5: Agent 综合整理，生成综述文档"""
        print(f"\n{'='*60}")
        print("  Step 5/5: 综合整理")
        print(f"{'='*60}")

        agent = make_synthesis_agent(self.config_path)
        repos_summary_path = os.path.join(survey_dir, "repos_summary.md")

        prompt = f"""请基于以下材料生成综合文档:

## 材料目录
- 论文总结: {summaries_dir}/
- 代码仓库调研: {repos_summary_path}

## 输出文件
1. {survey_dir}/survey.md - 综合文献综述
2. {survey_dir}/leaderboard.md - 排行榜
3. {baselines_path} - Baseline 方法
4. {datasets_path} - 推荐数据集
5. {metrics_path} - 推荐评估指标

请先用 list_directory 和 read_file 阅读所有总结文件和仓库调研报告，再生成综合文档。"""

        agent.run(prompt)
        print(f"  Step 5 完成")

    def _generate_topic_index(self, paper_ids: list, survey_dir: str):
        """生成 topic 级 index.yaml"""
        from tools.paper_manager import _load_index, SUMMARIES_DIR

        global_index = _load_index()
        topic_papers = []

        for item in paper_ids:
            pid = item["paper_id"]
            global_entry = global_index.get(pid, {})
            entry = {
                "paper_id": pid,
                "title": item.get("title", global_entry.get("title", "")),
                "summary_path": os.path.join(SUMMARIES_DIR, item["file"]),
            }
            if global_entry.get("pdf_path"):
                entry["pdf_path"] = global_entry["pdf_path"]
            if global_entry.get("md_path"):
                entry["parsed_path"] = global_entry["md_path"]
            topic_papers.append(entry)

        index_data = {"papers": topic_papers}
        index_path = os.path.join(survey_dir, "index.yaml")
        with open(index_path, "w", encoding="utf-8") as f:
            import yaml as _yaml
            _yaml.dump(index_data, f, allow_unicode=True, default_flow_style=False)

    def phase_ideation(self, ref_topics: list = None) -> str:
        """Idea 生成（增强版：ReAct 循环、去重、关系图）"""
        self._reload_config()
        self._log_phase_start("ideation")

        agent = IdeationAgent(self.config_path)

        # 收集上下文
        context = ""
        if self.ctx:
            context = self.ctx.build_context("ideation", ref_topics=ref_topics)

        # 收集各文件内容
        survey, baselines, failed = "", "", ""
        datasets_md, metrics_md = "", ""

        # 根据是否有 topic_dir 确定路径
        if self.topic_dir:
            paths = {
                "survey": os.path.join(self.topic_dir, "survey", "survey.md"),
                "baselines": os.path.join(self.topic_dir, "baselines.md"),
                "datasets": os.path.join(self.topic_dir, "datasets.md"),
                "metrics": os.path.join(self.topic_dir, "metrics.md"),
            }
        else:
            paths = {
                "survey": os.path.join(self.project_root, "knowledge", "survey.md"),
                "baselines": os.path.join(self.project_root, "knowledge", "baselines.md"),
                "datasets": os.path.join(self.project_root, "knowledge", "datasets.md"),
                "metrics": os.path.join(self.project_root, "knowledge", "metrics.md"),
            }

        for key, path in paths.items():
            if os.path.exists(path):
                content = read_file(path)
                if key == "survey": survey = content
                elif key == "baselines": baselines = content
                elif key == "datasets": datasets_md = content
                elif key == "metrics": metrics_md = content

        failed_path = os.path.join(self.project_root, "memory", "failed_ideas.md")
        if os.path.exists(failed_path):
            failed = read_file(failed_path)

        tc = self.topic_config
        ideas_dir = os.path.join(self.topic_dir, "ideas") if self.topic_dir else os.path.join(self.project_root, "ideas")
        os.makedirs(ideas_dir, exist_ok=True)

        prompt = f"""基于以下综述生成研究 idea:

## 研究课题
{tc["topic_title"]}

## 综述
{survey[:4000]}

## Baselines
{baselines[:2000]}

## 可用数据集
{datasets_md[:1000]}

## 评估指标
{metrics_md[:1000]}

## 已失败的方向（避免重复）
{failed}

{context}

根据 survey 和 context.md 的内容，从多个研究角度生成 idea:
- 分析 survey 中各方法的不足，针对性提出改进
- 从理论/方法/实验/应用等不同层面思考
- 每个 idea 只包含一个核心创新点

每个 idea 创建对应的 {ideas_dir}/{{idea_id}}_{{shortname}}/proposal.md，
并用 add_idea_to_tree 注册到研究树。
生成完毕后用 add_idea_relationship 记录 idea 间的关系，
最后用 get_idea_graph 生成关系图。"""

        result = agent.run(prompt)

        self._log_phase_end("ideation", summary=result[:200])

        print(f"\n{'='*60}")
        print(f"Ideation 完成! 请 review {ideas_dir}/ 目录下的 proposal.md")
        print(f"{'='*60}")
        return result

    def phase_refine(self, idea_id: str, ref_ideas: list = None,
                     ref_topics: list = None) -> str:
        """Idea 细化：理论推导 + 模块化结构 + 实验计划"""
        self._reload_config()
        self._log_phase_start("refine", idea_id)

        idea_dir = self._idea_dir(idea_id)
        if not idea_dir:
            return f"未找到 idea 目录: {idea_id}"

        agent = RefinementAgent(self.config_path)

        # 构建上下文
        context = ""
        if self.ctx:
            context = self.ctx.build_context("refine", idea_id, ref_ideas, ref_topics)

        proposal = read_file(os.path.join(idea_dir, "proposal.md"))
        past_exp = query_memory(idea_id=idea_id)

        # 创建 refinement 目录
        refinement_dir = os.path.join(idea_dir, "refinement")
        os.makedirs(refinement_dir, exist_ok=True)

        tc = self.topic_config

        prompt = f"""请将以下 idea 展开为完整技术方案。

## 研究课题
{tc["topic_title"]}

## 可用数据集
{tc["dataset_names"]}

## 评估指标
{tc["metric_names"]}

## Proposal
{proposal}

{context}

## 历史经验
{past_exp}

请输出:
1. {refinement_dir}/theory.md - 理论推导
2. {refinement_dir}/model_modular.md - 模块化结构设计
3. {refinement_dir}/model_complete.md - 完整结构设计
4. {idea_dir}/experiment_plan.md - 阶段性实验计划（含预期结果）"""

        result = agent.run(prompt)

        # 更新研究树
        self._update_idea_phase(idea_id, "refinement", "completed")

        self._log_phase_end("refine", idea_id, result[:200])

        print(f"\nRefine 完成! 请 review:")
        print(f"  - {refinement_dir}/")
        print(f"  - {idea_dir}/experiment_plan.md")
        return result

    def phase_code_reference(self, idea_id: str) -> str:
        """代码参考获取：clone 和摘要参考论文的代码"""
        self._reload_config()
        self._log_phase_start("code_reference", idea_id)

        idea_dir = self._idea_dir(idea_id)
        if not idea_dir:
            return f"未找到 idea 目录: {idea_id}"

        # 使用 LiteratureAgent 来获取代码参考
        agent = LiteratureAgent(self.config_path)

        # 读取 refinement 文档
        refinement_dir = os.path.join(idea_dir, "refinement")
        ref_content = ""
        for fname in ["theory.md", "model_modular.md"]:
            fpath = os.path.join(refinement_dir, fname)
            if os.path.exists(fpath):
                ref_content += f"\n## {fname}\n{read_file(fpath)[:2000]}\n"

        prompt = f"""根据以下 idea 的 refinement 文档，找到相关论文的开源代码:

{ref_content}

请:
1. 搜索相关论文的 GitHub 仓库
2. 用 clone_repo 拉取代码
3. 用 summarize_repo 生成代码摘要
4. 重点关注模型结构和训练方法的实现"""

        result = agent.run(prompt)

        self._update_idea_phase(idea_id, "code_reference", "completed")
        self._log_phase_end("code_reference", idea_id, result[:200])

        print(f"\nCode Reference 完成!")
        return result

    def phase_code(self, idea_id: str, ref_ideas: list = None) -> str:
        """代码编写"""
        self._reload_config()
        self._log_phase_start("code", idea_id)

        idea_dir = self._idea_dir(idea_id)
        if not idea_dir:
            return f"未找到 idea 目录: {idea_id}"

        agent = ExperimentAgent(self.config_path)

        # 构建上下文
        context = ""
        if self.ctx:
            context = self.ctx.build_context("code", idea_id, ref_ideas)

        # 读取 refinement 文档
        design_content = ""
        refinement_dir = os.path.join(idea_dir, "refinement")
        for fname in ["theory.md", "model_modular.md", "model_complete.md"]:
            fpath = os.path.join(refinement_dir, fname)
            if os.path.exists(fpath):
                design_content += f"\n## {fname}\n{read_file(fpath)}\n"

        plan_path = os.path.join(idea_dir, "experiment_plan.md")
        plan = read_file(plan_path) if os.path.exists(plan_path) else ""
        past_exp = query_memory(idea_id=idea_id)

        prompt = f"""根据设计方案和实验计划，实现代码。

## 技术方案
{design_content}

## 实验计划
{plan}

{context}

## 历史经验
{past_exp}

代码放在 {idea_dir}/src/（model/ 和 experiment/ 子目录），
先生成 {idea_dir}/src/structure.md 记录代码结构。"""

        result = agent.run(prompt)

        self._update_idea_phase(idea_id, "coding", "completed")
        self._log_phase_end("code", idea_id, result[:200])

        print(f"\nCode 完成! 请 review {idea_dir}/src/")
        return result

    def phase_experiment(self, idea_id: str, step_id: str = None,
                         version: int = None, max_iter: int = None) -> str:
        """运行单次实验（指定步骤和版本）"""
        self._reload_config()
        idea_dir = self._idea_dir(idea_id)
        if not idea_dir:
            return f"未找到 idea 目录: {idea_id}"

        if not step_id:
            step_id = "S01"
        if not version:
            version = 1

        self._log_phase_start("experiment", f"{idea_id}_{step_id}_V{version}")

        agent = ExperimentAgent(self.config_path)

        # 读取实验计划
        plan_path = os.path.join(idea_dir, "experiment_plan.md")
        plan = read_file(plan_path) if os.path.exists(plan_path) else ""

        # 读取代码结构
        structure_path = os.path.join(idea_dir, "src", "structure.md")
        structure = read_file(structure_path) if os.path.exists(structure_path) else ""

        # V2+ 读取前版本分析
        prev_analysis = ""
        if version > 1:
            step_d = self._step_dir(idea_id, step_id)
            if step_d:
                prev_v_dir = os.path.join(step_d, f"V{version - 1}")
                prev_analysis_path = os.path.join(prev_v_dir, "analysis.md")
                if os.path.exists(prev_analysis_path):
                    prev_analysis = read_file(prev_analysis_path)

        # 确定结果目录
        results_dir = os.path.join(idea_dir, "results")
        os.makedirs(results_dir, exist_ok=True)

        prompt = f"""运行实验步骤 {step_id}，版本 V{version}。

## 实验计划
{plan}

## 代码结构
{structure}
"""
        if prev_analysis:
            prompt += f"""
## 前版本 (V{version-1}) 分析结果
{prev_analysis}

请根据上述分析结果，微调实验设置后重新运行。
将配置差异记录到 config_diff.md。
"""

        prompt += f"""
结果存储到 {results_dir}/{step_id}_*/V{version}/
包含: metrics.json, plots/, log.txt"""
        if version > 1:
            prompt += f", config_diff.md"

        result = agent.run(prompt)

        # 更新迭代状态
        update_iteration(idea_id, step_id, version, "completed", topic_dir=self.topic_dir)

        self._log_phase_end("experiment", f"{idea_id}_{step_id}_V{version}", result[:200])

        return result

    def phase_experiment_loop(self, idea_id: str, step_id: str = None,
                              max_iter: int = None) -> str:
        """实验迭代循环：experiment → analyze → experiment → analyze → ..."""
        if max_iter is None:
            max_iter = self.default_max_iter

        if not step_id:
            step_id = "S01"

        # 注册实验步骤
        step_name = step_id.replace("S", "step_")
        add_experiment_step(idea_id, step_name, max_iter, self.topic_dir)

        results = []
        for v in range(1, max_iter + 1):
            print(f"\n--- 实验迭代 V{v}/{max_iter} ---")

            # 运行实验
            exp_result = self.phase_experiment(idea_id, step_id, version=v)
            results.append(f"V{v} experiment: {exp_result[:100]}")

            # 分析结果
            analysis_result = self.phase_analyze(idea_id, step_id=step_id, version=v)
            results.append(f"V{v} analysis: {analysis_result[:100]}")

            # 检查是否提前终止（分析建议停止）
            idea_dir = self._idea_dir(idea_id)
            if idea_dir:
                step_d = self._step_dir(idea_id, step_id)
                if step_d:
                    v_analysis = os.path.join(step_d, f"V{v}", "analysis.md")
                    if os.path.exists(v_analysis):
                        analysis_content = read_file(v_analysis)
                        if "建议停止" in analysis_content or "无需继续" in analysis_content:
                            print(f"分析建议停止迭代，在 V{v} 终止。")
                            # 标记剩余迭代为 skipped
                            for sv in range(v + 1, max_iter + 1):
                                update_iteration(idea_id, step_id, sv, "skipped",
                                                 topic_dir=self.topic_dir)
                            break

        return "\n".join(results)

    def phase_analyze(self, idea_id: str, step_id: str = None,
                      version: int = None) -> str:
        """分析实验结果"""
        self._reload_config()
        self._log_phase_start("analyze", idea_id)

        idea_dir = self._idea_dir(idea_id)
        if not idea_dir:
            return f"未找到 idea 目录: {idea_id}"

        agent = AnalysisAgent(self.config_path)

        # 收集所有相关文件
        files_content = []
        for fname in ["proposal.md", "experiment_plan.md"]:
            fpath = os.path.join(idea_dir, fname)
            if os.path.exists(fpath):
                files_content.append(f"## {fname}\n{read_file(fpath)}")

        # 读取 refinement
        refinement_dir = os.path.join(idea_dir, "refinement")
        if os.path.exists(refinement_dir):
            for fname in os.listdir(refinement_dir):
                if fname.endswith(".md"):
                    fpath = os.path.join(refinement_dir, fname)
                    files_content.append(f"## refinement/{fname}\n{read_file(fpath)[:2000]}")

        # 读取结果
        results_info = ""
        results_dir = os.path.join(idea_dir, "results")
        if os.path.exists(results_dir):
            if step_id:
                # 逐步分析
                for d in os.listdir(results_dir):
                    if d.startswith(step_id):
                        step_path = os.path.join(results_dir, d)
                        if version:
                            v_dir = os.path.join(step_path, f"V{version}")
                            if os.path.exists(v_dir):
                                results_info += f"\n### {d}/V{version}\n"
                                results_info += self._read_results_dir(v_dir)
                        else:
                            results_info += self._read_step_results(step_path)
            else:
                # 全量分析
                for d in sorted(os.listdir(results_dir)):
                    step_path = os.path.join(results_dir, d)
                    if os.path.isdir(step_path):
                        results_info += f"\n### {d}\n"
                        results_info += self._read_step_results(step_path)

        tc = self.topic_config

        prompt = f"""分析以下实验结果，提供决策建议。

## 研究课题
{tc["topic_title"]}

## 评估指标
{tc["metric_names"]}

{chr(10).join(files_content)}

## 实验结果
{results_info}

请:
1. 对比 baseline 的定量结果
2. 与 experiment_plan.md 中的预期结果对比
3. 对 results/ 下的图片调用 analyze_image 分析
"""
        if step_id and version:
            prompt += f"""4. 这是 {step_id} 的 V{version} 版本分析
5. 将单版本分析写入 results/{step_id}_*/V{version}/analysis.md
6. 如果还有后续迭代，给出下一版本的微调建议"""
        else:
            prompt += f"""4. 将总体分析写入 {idea_dir}/analysis.md
5. 给出明确的决策建议（继续深化/调整方向/放弃/发表）
6. 将关键经验记录到 memory"""

        result = agent.run(prompt)

        if not step_id:
            self._update_idea_phase(idea_id, "analysis", "completed")

        self._log_phase_end("analyze", idea_id, result[:200])

        print(f"\nAnalysis 完成! 请 review {idea_dir}/")
        return result

    def phase_conclude(self, idea_id: str, ref_ideas: list = None) -> str:
        """结论总结"""
        self._reload_config()
        self._log_phase_start("conclude", idea_id)

        idea_dir = self._idea_dir(idea_id)
        if not idea_dir:
            return f"未找到 idea 目录: {idea_id}"

        agent = ConclusionAgent(self.config_path)

        # 构建上下文
        context = ""
        if self.ctx:
            context = self.ctx.build_context("conclude", idea_id, ref_ideas)

        prompt = f"""请对 idea {idea_id} 进行客观总结。

Idea 目录: {idea_dir}

请阅读以下文件链路:
1. {idea_dir}/proposal.md
2. {idea_dir}/refinement/ (theory.md, model_modular.md, model_complete.md)
3. {idea_dir}/experiment_plan.md
4. {idea_dir}/src/ (代码实现)
5. {idea_dir}/results/ (实验结果)
6. {idea_dir}/analysis.md

{context}

将结论写入 {idea_dir}/conclusion.md"""

        result = agent.run(prompt)

        self._update_idea_phase(idea_id, "conclusion", "completed")
        self._log_phase_end("conclude", idea_id, result[:200])

        print(f"\nConclusion 完成! 请 review {idea_dir}/conclusion.md")
        return result

    def phase_auto(self, idea_id: str, start_phase: str = "refine",
                   ref_ideas: list = None, max_iter: int = None) -> str:
        """自动执行从指定阶段到结论的完整流程"""
        phases = ["refine", "code_reference", "code", "experiment_loop", "analyze", "conclude"]
        start_idx = 0
        for i, p in enumerate(phases):
            if p == start_phase:
                start_idx = i
                break

        results = []
        for phase in phases[start_idx:]:
            print(f"\n{'='*60}")
            print(f"  Auto: 执行 {phase}")
            print(f"{'='*60}")

            if phase == "refine":
                r = self.phase_refine(idea_id, ref_ideas)
            elif phase == "code_reference":
                r = self.phase_code_reference(idea_id)
            elif phase == "code":
                r = self.phase_code(idea_id, ref_ideas)
            elif phase == "experiment_loop":
                r = self.phase_experiment_loop(idea_id, max_iter=max_iter)
            elif phase == "analyze":
                r = self.phase_analyze(idea_id)
            elif phase == "conclude":
                r = self.phase_conclude(idea_id, ref_ideas)
            else:
                r = ""

            results.append(f"{phase}: {r[:100]}")

            # 暂停让用户确认
            action = input(f"\n{phase} 完成。[继续(c) / 退出(q)]: ").strip().lower()
            if action == "q":
                break

        return "\n".join(results)

    # === 辅助方法 ===

    def _read_results_dir(self, dir_path: str) -> str:
        """读取结果目录中的文件"""
        info = ""
        if not os.path.exists(dir_path):
            return info
        for f in sorted(os.listdir(dir_path)):
            fpath = os.path.join(dir_path, f)
            if f.endswith((".txt", ".md", ".csv", ".json")) and os.path.isfile(fpath):
                info += f"\n#### {f}\n{read_file(fpath)[:1000]}\n"
        return info

    def _read_step_results(self, step_path: str) -> str:
        """读取步骤下所有版本的结果"""
        info = ""
        for d in sorted(os.listdir(step_path)):
            v_dir = os.path.join(step_path, d)
            if os.path.isdir(v_dir) and d.startswith("V"):
                info += f"\n#### {d}\n"
                info += self._read_results_dir(v_dir)
        # 步骤级分析
        analysis_path = os.path.join(step_path, "analysis.md")
        if os.path.exists(analysis_path):
            info += f"\n#### 综合分析\n{read_file(analysis_path)[:1000]}\n"
        return info

    def _update_idea_phase(self, idea_id: str, phase_name: str, status: str):
        """更新研究树中 idea 的阶段状态"""
        tree = _load_tree(self.topic_dir)
        if not tree:
            return

        if tree:
            for i, idea in enumerate(tree.get("root", {}).get("ideas", [])):
                if idea["id"] == idea_id:
                    idea.setdefault("phases", {})
                    idea["phases"][phase_name] = status
                    _save_tree(tree, self.topic_dir)
                    return

    def _get_topic_id(self) -> str:
        """获取当前 topic ID"""
        if self.topic_dir:
            basename = os.path.basename(self.topic_dir)
            match = re.match(r"(T\d+)", basename)
            if match:
                return match.group(1)
        return ""

    def status(self, topic_id: str = None) -> str:
        """打印研究树当前状态"""
        # 尝试从 topic 目录加载
        if topic_id and self.topic_dir:
            tree = _load_tree(self.topic_dir)
        elif self.topic_dir:
            tree = _load_tree(self.topic_dir)
        else:
            tree = _load_tree()

        if not tree:
            return "未找到研究树。"

        lines = []
        root = tree.get("root", {})
        lines.append(f"课题: {root.get('topic', root.get('topic_brief', ''))}")
        lines.append(f"Topic ID: {root.get('topic_id', 'N/A')}")

        # elaborate 状态
        elaborate = root.get("elaborate", {})
        if elaborate:
            lines.append(f"展开调研: {elaborate.get('status', 'N/A')}")

        # survey 状态
        survey = root.get("survey", root.get("literature", {}))
        if survey:
            lines.append(f"文献调研: {survey.get('status', 'N/A')} (轮次: {survey.get('rounds', 'N/A')})")

        # ideas
        ideas = root.get("ideas", [])
        lines.append(f"\nIdeas ({len(ideas)} 个):")
        for idea in ideas:
            lines.append(f"  [{idea.get('id')}] {idea.get('title')} ({idea.get('status', '')})")
            phases = idea.get("phases", {})
            for p, s in phases.items():
                lines.append(f"    - {p}: {s}")
            # 实验步骤
            steps = idea.get("experiment_steps", [])
            for step in steps:
                lines.append(f"    实验 {step['step_id']} ({step['name']}): {step['status']}")
                for it in step.get("iterations", []):
                    lines.append(f"      V{it['version']}: {it['status']}")

        return "\n".join(lines)
