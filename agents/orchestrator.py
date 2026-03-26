"""主编排器：管理研究阶段流转和检查点（重构版：命名式分发、topic 目录、实验迭代）"""
import os
import re
import yaml
import json
import logging

from .survey_helpers import make_code_ref_agent, build_code_ref_prompt
from .survey_helpers import (
    make_search_agent, make_repo_agent, make_synthesis_agent, summarize_single_paper,
    build_search_prompt, build_repo_prompt, build_synthesis_prompt,
    make_eda_guide_agent, build_eda_guide_prompt,
)
from .ideation_agent import IdeationAgent
from .design_agent import DesignAgent
from .experiment_agent import ExperimentAgent
from .analysis_agent import AnalysisAgent
from .elaborate_agent import ElaborateAgent
from .refinement_agent import RefinementAgent
from .conclusion_agent import ConclusionAgent
from .theory_check_agent import TheoryCheckAgent
from .debug_agent import DebugAgent
from shared.utils.config_helpers import extract_topic_title
from shared.paths import PathManager
from tools.idea_registry import IdeaRegistryService
from tools.memory import query_memory, add_experience
from tools.file_ops import read_file, write_file
from tools.context_manager import ContextManager
from tools.knowledge_base import KnowledgeBaseManager, search_knowledge_base
from shared.models.tool_params import SearchKBParams
from tools.phase_logger import log_phase_start, log_phase_end

logger = logging.getLogger(__name__)


class ResearchOrchestrator:
    def __init__(self, topic_dir: str = None, config_path: str = None):
        """初始化编排器。

        Args:
            topic_dir: topic 目录路径（如 topics/T001_mean_reversion）。
                       如果为 None，尝试从现有结构推断。
            config_path: 全局 config.yaml 路径（项目根）。
        """
        self.project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.default_max_iter = 3

        # 初始化 PathManager（先用临时 topic_dir 以便 find_latest_topic）
        _tmp_paths = PathManager(self.project_root, topic_dir)
        if topic_dir:
            self.topic_dir = topic_dir
        else:
            found = _tmp_paths.find_latest_topic()
            self.topic_dir = str(found) if found else None

        # 正式构建 PathManager 和 IdeaRegistryService
        self.paths = PathManager(self.project_root, self.topic_dir)
        self.registry = IdeaRegistryService(self.paths)

        # topic title 从 md 文件链提取
        if self.topic_dir:
            self.topic_title = extract_topic_title(self.topic_dir)
        else:
            self.topic_title = ""

        # 初始化知识库管理器
        self.kb_mgr = KnowledgeBaseManager()

        # 初始化知识库
        self._ensure_knowledge_bases()

        # 初始化上下文管理器
        if self.topic_dir:
            self.ctx = ContextManager(self.paths, self.kb_mgr)
        else:
            self.ctx = None

    def _ensure_knowledge_bases(self):
        """首次运行时创建单一全局知识库（幂等）"""
        if not self.kb_mgr.enabled:
            return
        from tools.knowledge_base import SINGLE_KB_NAME
        self.kb_mgr.get_or_create_kb(SINGLE_KB_NAME, "全局研究知识库")

    def _log_phase_start(self, phase: str, idea_id: str = ""):
        """阶段开始日志"""
        if self.topic_dir:
            log_phase_start(phase, self.topic_dir, idea_id, paths=self.paths)
        logger.info(f"\n\n{'='*60}")
        logger.info(f"  Phase: {phase}" + (f" | Idea: {idea_id}" if idea_id else ""))
        logger.info(f"{'='*60}\n")

    def _log_phase_end(self, phase: str, idea_id: str = "", summary: str = ""):
        """阶段结束日志"""
        if self.topic_dir:
            log_phase_end(phase, self.topic_dir, idea_id, summary, self.kb_mgr, paths=self.paths)

    # === 阶段方法 ===

    def phase_elaborate(self, ref_topics: list = None) -> str:
        """展开调研背景"""
        self._log_phase_start("elaborate")

        # 确定输出路径
        if self.topic_dir:
            output_path = str(self.paths.context_md)
        else:
            output_path = os.path.join(self.project_root, "knowledge", "context.md")

        # 构建上下文
        context = ""
        if self.ctx:
            context = self.ctx.build_context("elaborate", ref_topics=ref_topics)

        agent = ElaborateAgent(self.topic_dir, output_path,
                               allowed_dirs=[str(self.paths.topic_dir)])

        # 读取 topic_spec.md 作为输入线索（不是约束）
        spec_content = ""
        spec_path = str(self.paths.topic_spec) if self.topic_dir else None
        if spec_path and os.path.exists(spec_path):
            spec_content = read_file(spec_path)

        prompt = agent.build_prompt(
            topic_title=self.topic_title,
            spec_content=spec_content,
            context=context,
            output_path=output_path,
        )

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
        self._log_phase_start("survey")

        topic_id = self._get_topic_id()

        # 确定输出目录
        summaries_dir = str(self.paths.summaries_dir)
        os.makedirs(summaries_dir, exist_ok=True)

        if self.topic_dir:
            survey_dir = str(self.paths.survey_dir)
            baselines_path = str(self.paths.baselines_md)
            datasets_path = str(self.paths.datasets_md)
            metrics_path = str(self.paths.metrics_md)
        else:
            survey_dir = os.path.join(self.project_root, "knowledge", "survey")
            baselines_path = os.path.join(self.project_root, "knowledge", "baselines.md")
            datasets_path = os.path.join(self.project_root, "knowledge", "datasets.md")
            metrics_path = os.path.join(self.project_root, "knowledge", "metrics.md")

        os.makedirs(survey_dir, exist_ok=True)

        # 加载/初始化进度文件
        progress_path = str(self.paths.survey_progress)
        progress = self._load_survey_progress(progress_path)
        paper_list_path = str(self.paths.paper_list_yaml)

        # 第二轮及以后：重置 progress，重新搜索和综合
        if round_num > 1:
            progress = {}
            self._save_survey_progress(progress, progress_path)

        def completed(step_key):
            return progress.get(step_key) == "completed"

        # Step 1: 搜索与收集
        if start_step <= 1 and not completed("step1_search"):
            self._survey_step1_search(survey_dir, paper_list_path, round_num, topic_id)
            papers = self._load_paper_list(paper_list_path)
            if papers:
                progress["step1_search"] = "completed"
                self._save_survey_progress(progress, progress_path)
            else:
                progress["step1_search"] = "failed"
                self._save_survey_progress(progress, progress_path)
                return "Survey aborted: Step 1 未找到任何论文"

        # Step 2+3: 并行下载→解析→总结
        if start_step <= 3 and not (completed("step2_download") and completed("step3_summarize")):
            progress["step2_download"] = "in_progress"
            progress["step3_summarize"] = "in_progress"
            self._save_survey_progress(progress, progress_path)
            self._survey_step23_parallel(paper_list_path, summaries_dir, topic_id)
            self._upload_step_artifacts(summaries_dir)
            progress["step2_download"] = "completed"
            progress["step3_summarize"] = "completed"
            self._save_survey_progress(progress, progress_path)

        # Step 4: 代码仓库调研
        if start_step <= 4 and not completed("step4_repos"):
            progress["step4_repos"] = "in_progress"
            self._save_survey_progress(progress, progress_path)
            self._survey_step4_repos(survey_dir, summaries_dir)
            self._upload_single_artifact(str(self.paths.repos_summary_md))
            progress["step4_repos"] = "completed"
            self._save_survey_progress(progress, progress_path)

        # Step 4a: EDA 规划（从论文提取分析方法）
        if start_step <= 5 and not completed("step4a_eda_guide"):
            progress["step4a_eda_guide"] = "in_progress"
            self._save_survey_progress(progress, progress_path)
            self._survey_step4a_eda_guide(summaries_dir, survey_dir,
                                           datasets_path, metrics_path)
            progress["step4a_eda_guide"] = "completed"
            self._save_survey_progress(progress, progress_path)

        # Step 4b: 数据下载 + EDA
        if start_step <= 5 and not completed("step4b_data_eda"):
            progress["step4b_data_eda"] = "in_progress"
            self._save_survey_progress(progress, progress_path)
            self._survey_step4b_data_eda(datasets_path)
            self._upload_single_artifact(str(self.paths.eda_report_md))
            progress["step4b_data_eda"] = "completed"
            self._save_survey_progress(progress, progress_path)

        # Step 5: 综合整理
        if start_step <= 5 and not completed("step5_synthesize"):
            progress["step5_synthesize"] = "in_progress"
            self._save_survey_progress(progress, progress_path)
            self._survey_step5_synthesize(survey_dir, summaries_dir, baselines_path)
            for p in [str(self.paths.survey_md),
                      str(self.paths.leaderboard_md),
                      baselines_path]:
                self._upload_single_artifact(p)
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

        add_experience(phase="survey", type="insight",
                       summary=f"Survey 流水线完成（5步），共处理论文见 {paper_list_path}",
                       topic_id=topic_id)
        paper_count = 0
        if os.path.exists(paper_list_path):
            with open(paper_list_path, "r", encoding="utf-8") as f:
                papers = yaml.safe_load(f) or []
                paper_count = len(papers)
        survey_summary = f"Survey 完成，共处理 {paper_count} 篇论文，产出见 {survey_dir}/"
        self._log_phase_end("survey", summary=survey_summary)

        print(f"\n{'='*60}")
        print("Survey 完成! 请 review:")
        print(f"  - {survey_dir}/")
        print(f"  - {summaries_dir}/ (论文总结)")
        print(f"  - {baselines_path}")
        print(f"  - {datasets_path}")
        print(f"  - {metrics_path}")
        print(f"  - {str(self.paths.eda_dir)}/ (EDA)")
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
            "step4a_eda_guide": "pending",
            "step4b_data_eda": "pending",
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

        agent = make_search_agent(self.topic_dir,
                                  allowed_dirs=[survey_dir])

        context = ""
        if self.ctx:
            context = self.ctx.build_context("survey")

        topic = self.topic_title
        past_exp = query_memory(phase="literature")

        prompt = build_search_prompt(
            topic=topic,
            round_num=round_num,
            paper_list_path=paper_list_path,
            context=context,
            past_exp=past_exp,
        )

        agent.run(prompt)

        # === 写入保障 ===
        papers = self._load_paper_list(paper_list_path)
        if len(papers) < 3:
            logger.warning(f"paper_list 仅 {len(papers)} 篇，从 agent 历史中恢复...")
            recovered = self._recover_papers_from_history(agent.get_message_history())
            if recovered:
                existing_ids = {p.get("paper_id") for p in papers}
                for rp in recovered:
                    if rp.get("paper_id") not in existing_ids:
                        papers.append(rp)
                papers.sort(key=lambda x: x.get("citation_count", 0), reverse=True)
                self._save_paper_list(papers, paper_list_path)
                logger.info(f"恢复后共 {len(papers)} 篇论文")

        print(f"  Step 1 完成: {paper_list_path}")

    def _recover_papers_from_history(self, messages: list) -> list:
        """从 agent 历史消息中提取 search_papers 返回的论文数据"""
        papers = {}  # paper_id -> dict, 自动去重
        for msg in messages:
            content = msg.get("content", "")
            if not isinstance(content, list):
                continue
            for block in content:
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    continue
                text = block.get("content", "")
                try:
                    data = json.loads(text)
                    if not isinstance(data, list):
                        continue
                    for p in data:
                        pid = p.get("paperId", "")
                        if not pid or pid in papers:
                            continue
                        ext = p.get("externalIds") or {}
                        oa = p.get("openAccessPdf") or {}
                        papers[pid] = {
                            "paper_id": pid,
                            "title": p.get("title", ""),
                            "year": p.get("year"),
                            "citation_count": p.get("citationCount", 0),
                            "arxiv_id": ext.get("ArXiv", ""),
                            "venue": p.get("venue", ""),
                            "authors": [a.get("name", "") for a in (p.get("authors") or [])[:5]],
                            "open_access_url": oa.get("url", ""),
                            "relevance": "",
                            "download_status": "pending",
                            "summary_status": "pending",
                        }
                except (json.JSONDecodeError, TypeError):
                    continue
        return list(papers.values())

    def _upload_single_artifact(self, file_path: str):
        """上传单文件到全局知识库（session 内去重，与 phase_logger 共享去重 set）"""
        from tools.phase_logger import _uploaded_artifact_set, derive_display_name
        if file_path in _uploaded_artifact_set or not os.path.exists(file_path):
            return
        from tools.knowledge_base import SINGLE_KB_NAME
        display_name = derive_display_name(file_path)
        kb_id = self.kb_mgr.get_or_create_kb(SINGLE_KB_NAME, "全局研究知识库")
        if kb_id:
            doc_id = self.kb_mgr.upload_document(kb_id, file_path, display_name=display_name)
            _uploaded_artifact_set.add(file_path)
            if doc_id:
                logger.info(f"Incremental upload: {display_name}")

    def _upload_step_artifacts(self, directory: str, pattern: str = "*.md"):
        """上传目录下匹配文件"""
        import glob
        for fpath in glob.glob(os.path.join(directory, pattern)):
            self._upload_single_artifact(fpath)

    def _survey_step23_parallel(self, paper_list_path: str, summaries_dir: str,
                                topic_id: str, max_workers: int = 5):
        """Step 2+3: 并行 下载→解析→总结（每篇论文独立流水线）"""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        import anthropic as _anthropic
        from tools.paper_manager import (
            download_paper, download_paper_by_arxiv, _load_index, _find_md_file, title_to_slug,
        )

        print(f"\n{'='*60}")
        print(f"  Step 2+3: 并行下载与总结（{max_workers} 路并发）")
        print(f"{'='*60}")

        papers = self._load_paper_list(paper_list_path)
        if not papers:
            print("  paper_list.yaml 为空，跳过")
            return

        from shared.utils.config_helpers import load_global_config
        _cfg = load_global_config()
        client = _anthropic.Anthropic(
            api_key=os.environ.get("MINIMAX_API_KEY", ""),
            base_url=_cfg.llm.base_url,
        )
        model = _cfg.llm.default_model
        topic_title = self.topic_title
        os.makedirs(summaries_dir, exist_ok=True)

        lock = threading.Lock()
        total = len(papers)

        def _process_one(idx: int, paper: dict):
            """单篇论文：下载 → 找全文 → 总结"""
            title = paper.get("title", "unknown")
            paper_id = paper.get("paper_id", "")
            arxiv_id = paper.get("arxiv_id") or ""
            slug = title_to_slug(title)
            summary_path = os.path.join(summaries_dir, f"paper_{slug}.md")
            tag = f"[{idx+1}/{total}]"

            # === 阶段 1: 下载 ===
            if paper.get("download_status") not in ("downloaded", "no_access", "no_source", "no_id"):
                if arxiv_id:
                    result = download_paper_by_arxiv(arxiv_id, paper_id=paper_id, title=title)
                elif paper_id:
                    result = download_paper(paper_id, title)
                elif paper.get("open_access_url"):
                    paper["download_status"] = "no_id"
                    return
                else:
                    paper["download_status"] = "no_source"
                    return

                if "成功" in result or "已下载" in result:
                    paper["download_status"] = "downloaded"
                elif "没有 Open Access" in result or "下载失败" in result:
                    paper["download_status"] = "no_access"
                else:
                    paper["download_status"] = "failed"
                    logger.warning(f"  {tag} 下载异常: {result[:200]}")

                print(f"  {tag} 下载: {title[:45]}... → {paper['download_status']}")

            # === 阶段 2: 总结 ===
            if paper.get("summary_status") == "done":
                return
            if os.path.exists(summary_path):
                paper["summary_status"] = "done"
                print(f"  {tag} 总结已存在，跳过")
                return

            # 找全文
            paper_text = None
            abstract_only = False

            if paper.get("download_status") == "downloaded" and paper_id:
                # 重新加载 index（下载后可能更新了）
                fresh_index = _load_index()
                entry = fresh_index.get(paper_id, {})
                md_path = entry.get("md_path")
                if md_path and os.path.exists(md_path):
                    with open(md_path, "r", encoding="utf-8") as f:
                        paper_text = f.read()

            if not paper_text:
                abstract = paper.get("relevance", "")
                if abstract:
                    paper_text = abstract
                    abstract_only = True
                else:
                    paper["summary_status"] = "skipped"
                    print(f"  {tag} 无全文也无摘要，跳过")
                    return

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
                print(f"  {tag} 总结完成（{source}）→ {os.path.basename(summary_path)}")
            except Exception as e:
                paper["summary_status"] = "failed"
                logger.warning(f"  {tag} 总结失败: {e}")

        # 提交并行任务
        futures = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for idx, paper in enumerate(papers):
                # 跳过已完成的
                if (paper.get("download_status") in ("downloaded", "no_access", "no_source", "no_id")
                        and paper.get("summary_status") == "done"):
                    print(f"  [{idx+1}/{total}] {paper.get('title', '')[:45]}... 已完成，跳过")
                    continue
                future = executor.submit(_process_one, idx, paper)
                futures[future] = idx

            # 收集结果，定期保存
            save_counter = 0
            for future in as_completed(futures):
                try:
                    future.result()  # 触发异常
                except Exception as e:
                    idx = futures[future]
                    logger.error(f"  [{idx+1}/{total}] 处理异常: {e}")

                save_counter += 1
                # 每完成 3 篇保存一次（崩溃安全 + 减少 I/O）
                if save_counter % 3 == 0:
                    with lock:
                        self._save_paper_list(papers, paper_list_path)

        # 最终保存
        self._save_paper_list(papers, paper_list_path)

        downloaded = sum(1 for p in papers if p.get("download_status") == "downloaded")
        summarized = sum(1 for p in papers if p.get("summary_status") == "done")
        print(f"  Step 2+3 完成: {downloaded}/{total} 下载, {summarized}/{total} 总结")

    def _survey_step4_repos(self, survey_dir: str, summaries_dir: str):
        """Step 4: Agent 搜索和分析代码仓库"""
        print(f"\n{'='*60}")
        print("  Step 4/5: 代码仓库调研")
        print(f"{'='*60}")

        agent = make_repo_agent(self.topic_dir,
                               allowed_dirs=[survey_dir, str(self.paths.repos_dir)])
        repos_summary_path = str(self.paths.repos_summary_md)
        paper_list_path = str(self.paths.paper_list_yaml)

        prompt = build_repo_prompt(
            paper_list_path=paper_list_path,
            summaries_dir=summaries_dir,
            repos_summary_path=repos_summary_path,
        )

        agent.run(prompt)
        print(f"  Step 4 完成: {repos_summary_path}")

    def _survey_step4a_eda_guide(self, summaries_dir: str, survey_dir: str,
                                 datasets_path: str, metrics_path: str):
        """Step 4a: 从论文提取分析方法，生成 EDA 规划"""
        print(f"\n{'='*60}")
        print("  Step 4a: EDA 规划（从论文提取分析方法）")
        print(f"{'='*60}")

        eda_dir = str(self.paths.eda_dir)
        os.makedirs(eda_dir, exist_ok=True)

        agent = make_eda_guide_agent(self.topic_dir,
                                     allowed_dirs=[eda_dir, str(self.paths.topic_dir)])
        prompt = build_eda_guide_prompt(
            summaries_dir=summaries_dir,
            repos_summary_path=str(self.paths.repos_summary_md),
            context_path=str(self.paths.context_md),
            eda_guide_path=str(self.paths.eda_guide_md),
            datasets_path=datasets_path,
            metrics_path=metrics_path,
        )
        agent.run(prompt)
        for p in [str(self.paths.eda_guide_md), datasets_path, metrics_path]:
            self._upload_single_artifact(p)
        print(f"  Step 4a 完成")

    def _survey_step4b_data_eda(self, datasets_path: str):
        """Step 4b: 根据 EDA 指南下载数据并执行 EDA"""
        print(f"\n{'='*60}")
        print("  Step 4b: 数据下载与 EDA")
        print(f"{'='*60}")

        eda_plots_dir = str(self.paths.eda_plots_dir)
        eda_scripts_dir = str(self.paths.eda_scripts_dir)
        os.makedirs(eda_plots_dir, exist_ok=True)
        os.makedirs(eda_scripts_dir, exist_ok=True)

        # 预创建 EDA venv
        eda_dir = str(self.paths.eda_dir)
        from tools.venv_manager import setup_idea_venv
        venv_path = str(self.paths.eda_venv_dir)
        setup_result = setup_idea_venv(eda_dir)
        logger.info("EDA venv setup: %s", setup_result)

        from .data_agent import DataAgent
        agent = DataAgent(
            eda_guide_path=str(self.paths.eda_guide_md),
            data_dir=str(self.paths.data_dir),
            eda_dir=eda_dir,
            eda_plots_dir=eda_plots_dir,
            eda_scripts_dir=eda_scripts_dir,
            eda_report_path=str(self.paths.eda_report_md),
            datasets_path=datasets_path,
            venv_path=venv_path if os.path.exists(os.path.join(venv_path, "bin", "activate")) else "",
            allowed_dirs=[eda_dir, str(self.paths.data_dir), str(self.paths.topic_dir)],
        )
        agent.run(agent.build_prompt())
        self._reload_config()
        print(f"  Step 4b 完成")

    def _survey_step5_synthesize(self, survey_dir: str, summaries_dir: str,
                                  baselines_path: str):
        """Step 5: Agent 综合整理，生成综述文档"""
        print(f"\n{'='*60}")
        print("  Step 5: 综合整理")
        print(f"{'='*60}")

        agent = make_synthesis_agent(self.topic_dir,
                                     allowed_dirs=[survey_dir, str(self.paths.topic_dir)])
        repos_summary_path = str(self.paths.repos_summary_md)
        repos_exists = os.path.exists(repos_summary_path)

        context_path = str(self.paths.topic_dir / "context.md")
        prompt = build_synthesis_prompt(
            summaries_dir=summaries_dir,
            repos_summary_path=repos_summary_path,
            repos_exists=repos_exists,
            survey_dir=survey_dir,
            baselines_path=baselines_path,
            context_path=context_path if os.path.exists(context_path) else None,
            eda_report_path=str(self.paths.eda_report_md),
            eda_exists=os.path.exists(str(self.paths.eda_report_md)),
            datasets_path=str(self.paths.datasets_md),
            metrics_path=str(self.paths.metrics_md),
        )

        agent.run(prompt)
        print(f"  Step 5 完成")

    def _generate_topic_index(self, paper_ids: list, survey_dir: str):
        """生成 topic 级 index.yaml"""
        from tools.paper_manager import _load_index, _get_paths

        global_index = _load_index()
        summaries_dir = _get_paths()["summaries_dir"]
        topic_papers = []

        for item in paper_ids:
            pid = item["paper_id"]
            global_entry = global_index.get(pid, {})
            entry = {
                "paper_id": pid,
                "title": item.get("title", global_entry.get("title", "")),
                "summary_path": os.path.join(summaries_dir, item["file"]),
            }
            if global_entry.get("pdf_path"):
                entry["pdf_path"] = global_entry["pdf_path"]
            if global_entry.get("md_path"):
                entry["parsed_path"] = global_entry["md_path"]
            topic_papers.append(entry)

        index_data = {"papers": topic_papers}
        index_path = str(self.paths.survey_index_yaml)
        with open(index_path, "w", encoding="utf-8") as f:
            import yaml as _yaml
            _yaml.dump(index_data, f, allow_unicode=True, default_flow_style=False)

    def phase_ideation(self, ref_topics: list = None) -> str:
        """Idea 生成（增强版：ReAct 循环、去重、关系图）"""
        self._log_phase_start("ideation")

        agent = IdeationAgent(self.topic_dir or ".",
                              allowed_dirs=[str(self.paths.ideas_dir), str(self.paths.topic_dir)])

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
                "survey": str(self.paths.survey_md),
                "baselines": str(self.paths.baselines_md),
                "datasets": str(self.paths.datasets_md),
                "metrics": str(self.paths.metrics_md),
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

        failed_path = str(self.paths.failed_ideas)
        if os.path.exists(failed_path):
            failed = read_file(failed_path)

        ideas_dir = str(self.paths.ideas_dir) if self.topic_dir else os.path.join(self.project_root, "ideas")
        os.makedirs(ideas_dir, exist_ok=True)

        prompt = agent.build_prompt(
            topic_title=self.topic_title,
            survey=survey,
            baselines=baselines,
            datasets_md=datasets_md,
            metrics_md=metrics_md,
            failed=failed,
            context=context,
            ideas_dir=ideas_dir,
        )

        result = agent.run(prompt)

        # 上传所有 idea proposal 到知识库
        if os.path.exists(ideas_dir):
            for d in os.listdir(ideas_dir):
                proposal_path = os.path.join(ideas_dir, d, "proposal.md")
                self._upload_single_artifact(proposal_path)

        # 评分与排序
        from tools.idea_scorer import score_all_ideas
        print("\n  正在对 idea 进行评分...")
        try:
            score_results = score_all_ideas(
                topic_dir=self.topic_dir,
                client=agent.client,
                model=agent.model,
                topic_title=self.topic_title,
                registry=self.registry,
                paths=self.paths,
            )
            if score_results:
                print(f"\n  {'─'*50}")
                print(f"  Idea 评分排名:")
                for sr in score_results:
                    status_icon = "★" if sr["status"] == "recommended" else ("○" if sr["status"] == "proposed" else "✗")
                    print(f"    {status_icon} {sr['idea_id']}: {sr['composite']:.2f} - {sr['title'][:50]}")
                print(f"  {'─'*50}")
        except Exception as e:
            logger.warning(f"Idea 评分失败（不影响 ideation 结果）: {e}")

        self._log_phase_end("ideation", summary=result[:200])

        print(f"\n{'='*60}")
        print(f"Ideation 完成! 请 review {ideas_dir}/ 目录下的 proposal.md 和 review.md")
        print(f"{'='*60}")
        return result

    def phase_refine(self, idea_id: str, ref_ideas: list = None,
                     ref_topics: list = None) -> str:
        """Idea 细化：理论推导 + 模块化结构 + 实验计划"""
        self._log_phase_start("refine", idea_id)

        idea_dir_path = self.paths.idea_dir(idea_id)
        if not idea_dir_path:
            return f"未找到 idea 目录: {idea_id}"
        idea_dir = str(idea_dir_path)

        agent = RefinementAgent(self.topic_dir, allowed_dirs=[idea_dir])

        # 构建上下文
        context = ""
        if self.ctx:
            context = self.ctx.build_context("refine", idea_id, ref_ideas, ref_topics)

        proposal = read_file(str(self.paths.idea_proposal(idea_id)))
        past_exp = query_memory(idea_id=idea_id)

        # 创建 refinement 目录
        refinement_dir = str(self.paths.idea_refinement_dir(idea_id))
        os.makedirs(refinement_dir, exist_ok=True)

        # 检查是否存在上一轮理论审查
        theory_review_path = ""
        review_file = self.paths.idea_refinement_dir(idea_id) / "theory_review.md"
        if review_file.exists():
            theory_review_path = str(review_file)

        # 检查 analysis.md（analyze→refine 回退时提供上下文）
        analysis_path = ""
        analysis_file = self.paths.idea_dir(idea_id) / "analysis.md"
        if analysis_file.exists():
            analysis_path = str(analysis_file)

        prompt = agent.build_prompt(
            topic_title=self.topic_title,
            dataset_names="",
            metric_names="",
            topic_dir=self.topic_dir,
            idea_dir=idea_dir,
            proposal=proposal,
            context=context,
            past_exp=past_exp,
            refinement_dir=refinement_dir,
            theory_review_path=theory_review_path,
            analysis_path=analysis_path,
        )

        result = agent.run(prompt)

        # 上传产出物到知识库
        self._upload_step_artifacts(refinement_dir)
        exp_plan_path = str(self.paths.idea_experiment_plan(idea_id))
        self._upload_single_artifact(exp_plan_path)

        self._log_phase_end("refine", idea_id, result[:200])

        print(f"\nRefine 完成! 请 review:")
        print(f"  - {refinement_dir}/")
        print(f"  - {idea_dir}/experiment_plan.md")
        return result

    def phase_code_reference(self, idea_id: str) -> str:
        """代码参考获取：clone 和摘要参考论文的代码"""
        self._log_phase_start("code_reference", idea_id)

        idea_dir_path = self.paths.idea_dir(idea_id)
        if not idea_dir_path:
            return f"未找到 idea 目录: {idea_id}"
        idea_dir = str(idea_dir_path)

        agent = make_code_ref_agent(allowed_dirs=[idea_dir, str(self.paths.repos_dir)])

        # 读取 refinement 文档
        refinement_dir = str(self.paths.idea_refinement_dir(idea_id))
        ref_content = ""
        for fname in ["theory.md", "model_modular.md"]:
            fpath = os.path.join(refinement_dir, fname)
            if os.path.exists(fpath):
                ref_content += f"\n## {fname}\n{read_file(fpath)[:20000]}\n"

        prompt = build_code_ref_prompt(ref_content=ref_content)

        result = agent.run(prompt)

        self._log_phase_end("code_reference", idea_id, result[:200])

        print(f"\nCode Reference 完成!")
        return result

    def phase_code(self, idea_id: str, ref_ideas: list = None) -> str:
        """代码编写"""
        self._log_phase_start("code", idea_id)

        idea_dir_path = self.paths.idea_dir(idea_id)
        if not idea_dir_path:
            return f"未找到 idea 目录: {idea_id}"
        idea_dir = str(idea_dir_path)

        agent = ExperimentAgent(self.topic_dir,
                                allowed_dirs=[idea_dir, str(self.paths.data_dir)])

        # 构建上下文
        context = ""
        if self.ctx:
            context = self.ctx.build_context("code", idea_id, ref_ideas)

        # 读取 refinement 文档
        design_content = ""
        refinement_dir = str(self.paths.idea_refinement_dir(idea_id))
        for fname in ["theory.md", "model_modular.md", "model_complete.md"]:
            fpath = os.path.join(refinement_dir, fname)
            if os.path.exists(fpath):
                design_content += f"\n## {fname}\n{read_file(fpath)}\n"

        plan_path = str(self.paths.idea_experiment_plan(idea_id))
        plan = read_file(plan_path) if os.path.exists(plan_path) else ""
        past_exp = query_memory(idea_id=idea_id)

        # 检查 debug_report.md（debug→code 回退时提供上下文）
        debug_report_path = ""
        debug_report_file = idea_dir_path / "src" / "debug_report.md"
        if debug_report_file.exists():
            debug_report_path = str(debug_report_file)

        prompt = agent.build_code_prompt(
            design_content=design_content,
            plan=plan,
            context=context,
            past_exp=past_exp,
            idea_dir=idea_dir,
            debug_report_path=debug_report_path,
        )

        result = agent.run(prompt)

        # 上传代码结构文档到知识库
        src_dir = self.paths.idea_src_dir(idea_id)
        structure_path = str(src_dir / "structure.md") if src_dir else None
        if structure_path:
            self._upload_single_artifact(structure_path)

        # 自动配置 venv 并安装依赖
        if src_dir:
            venv_result = self._setup_idea_env(idea_id, src_dir)
            result += f"\n\n[环境配置] {venv_result}"

        self._log_phase_end("code", idea_id, result[:200])

        print(f"\nCode 完成! 请 review {idea_dir}/src/")
        return result

    def phase_experiment(self, idea_id: str, step_id: str = None,
                         version: int = None, max_iter: int = None) -> str:
        """运行单次实验（指定步骤和版本）"""
        self._reload_config()
        idea_dir_path = self.paths.idea_dir(idea_id)
        if not idea_dir_path:
            return f"未找到 idea 目录: {idea_id}"
        idea_dir = str(idea_dir_path)

        if not step_id:
            step_id = "S01"
        if not version:
            version = 1

        self._log_phase_start("experiment", f"{idea_id}_{step_id}_V{version}")

        agent = ExperimentAgent(self.topic_dir,
                                allowed_dirs=[idea_dir, str(self.paths.data_dir)])

        # 读取实验计划
        plan_path = str(self.paths.idea_experiment_plan(idea_id))
        plan = read_file(plan_path) if os.path.exists(plan_path) else ""

        # 读取代码结构
        src_dir = self.paths.idea_src_dir(idea_id)
        structure_path = str(src_dir / "structure.md") if src_dir else None
        structure = read_file(structure_path) if structure_path and os.path.exists(structure_path) else ""

        # V2+ 读取前版本分析
        prev_analysis = ""
        if version > 1:
            prev_v_dir = self.paths.version_dir(idea_id, step_id, version - 1)
            if prev_v_dir:
                prev_analysis_path = str(prev_v_dir / "analysis.md")
                if os.path.exists(prev_analysis_path):
                    prev_analysis = read_file(prev_analysis_path)

        # 确定结果目录
        results_dir = str(self.paths.idea_results_dir(idea_id))
        os.makedirs(results_dir, exist_ok=True)

        # 确定 venv 路径
        venv_dir = self.paths.idea_venv_dir(idea_id)
        venv_path = str(venv_dir) if venv_dir and venv_dir.exists() else ""

        prompt = agent.build_experiment_prompt(
            step_id=step_id,
            version=version,
            plan=plan,
            structure=structure,
            prev_analysis=prev_analysis,
            results_dir=results_dir,
            venv_path=venv_path,
        )

        result = agent.run(prompt)

        self._log_phase_end("experiment", f"{idea_id}_{step_id}_V{version}", result[:200])

        return result

    def phase_analyze(self, idea_id: str, step_id: str = None,
                      version: int = None) -> str:
        """分析实验结果"""
        self._log_phase_start("analyze", idea_id)

        idea_dir_path = self.paths.idea_dir(idea_id)
        if not idea_dir_path:
            return f"未找到 idea 目录: {idea_id}"
        idea_dir = str(idea_dir_path)

        agent = AnalysisAgent(self.topic_dir,
                              allowed_dirs=[idea_dir, str(self.paths.memory_dir)])

        # 收集所有相关文件
        files_content = []
        for fname in ["proposal.md", "experiment_plan.md"]:
            fpath = os.path.join(idea_dir, fname)
            if os.path.exists(fpath):
                files_content.append(f"## {fname}\n{read_file(fpath)}")

        # 读取 refinement
        refinement_dir = str(self.paths.idea_refinement_dir(idea_id))
        if os.path.exists(refinement_dir):
            for fname in os.listdir(refinement_dir):
                if fname.endswith(".md"):
                    fpath = os.path.join(refinement_dir, fname)
                    files_content.append(f"## refinement/{fname}\n{read_file(fpath)[:20000]}")

        # 读取结果
        results_info = ""
        results_dir = str(self.paths.idea_results_dir(idea_id))
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

        prompt = agent.build_prompt(
            topic_title=self.topic_title,
            metric_names="",
            files_content=files_content,
            results_info=results_info,
            step_id=step_id,
            version=version,
            idea_dir=idea_dir,
        )

        result = agent.run(prompt)

        # 上传分析结果到知识库
        if step_id and version:
            v_dir = self.paths.version_dir(idea_id, step_id, version)
            if v_dir:
                analysis_path = str(v_dir / "analysis.md")
                self._upload_single_artifact(analysis_path)
        else:
            analysis_p = self.paths.idea_analysis(idea_id)
            if analysis_p:
                self._upload_single_artifact(str(analysis_p))

        self._log_phase_end("analyze", idea_id, result[:200])

        print(f"\nAnalysis 完成! 请 review {idea_dir}/")
        return result

    def phase_conclude(self, idea_id: str, ref_ideas: list = None) -> str:
        """结论总结"""
        self._log_phase_start("conclude", idea_id)

        idea_dir_path = self.paths.idea_dir(idea_id)
        if not idea_dir_path:
            return f"未找到 idea 目录: {idea_id}"
        idea_dir = str(idea_dir_path)

        agent = ConclusionAgent(self.topic_dir,
                                allowed_dirs=[idea_dir, str(self.paths.memory_dir)])

        # 构建上下文
        context = ""
        if self.ctx:
            context = self.ctx.build_context("conclude", idea_id, ref_ideas)

        prompt = agent.build_prompt(
            idea_id=idea_id,
            idea_dir=idea_dir,
            context=context,
        )

        result = agent.run(prompt)

        # 上传结论到知识库
        conclusion_path = self.paths.idea_conclusion(idea_id)
        if conclusion_path:
            self._upload_single_artifact(str(conclusion_path))

        self._log_phase_end("conclude", idea_id, result[:200])

        print(f"\nConclusion 完成! 请 review {idea_dir}/conclusion.md")
        return result

    def phase_theory_check(self, idea_id: str, feedback: str = "") -> str:
        """理论检查：对 refinement 产出进行交叉验证"""
        self._log_phase_start("theory_check", idea_id)

        idea_dir_path = self.paths.idea_dir(idea_id)
        if not idea_dir_path:
            return f"未找到 idea 目录: {idea_id}"

        refinement_dir = self.paths.idea_refinement_dir(idea_id)
        if not refinement_dir:
            return f"未找到 refinement 目录: {idea_id}"

        agent = TheoryCheckAgent(self.topic_dir,
                                 allowed_dirs=[str(idea_dir_path)])

        theory_path = str(refinement_dir / "theory.md")
        survey_path = str(self.paths.survey_md)
        proposal_path = str(self.paths.idea_proposal(idea_id))
        output_path = str(refinement_dir / "theory_review.md")

        prompt = agent.build_prompt(
            theory_path=theory_path,
            survey_path=survey_path,
            proposal_path=proposal_path,
            output_path=output_path,
            feedback=feedback,
        )

        result = agent.run(prompt)

        self._upload_single_artifact(output_path)
        self._log_phase_end("theory_check", idea_id, result[:200])

        print(f"\nTheory Check 完成! 请 review: {output_path}")
        return result

    def phase_debug(self, idea_id: str,
                    analysis_path: str = "",
                    debug_report_path: str = "") -> str:
        """调试：运行测试、修复 bug"""
        self._log_phase_start("debug", idea_id)

        idea_dir_path = self.paths.idea_dir(idea_id)
        if not idea_dir_path:
            return f"未找到 idea 目录: {idea_id}"

        agent = DebugAgent(self.topic_dir,
                           allowed_dirs=[str(idea_dir_path)])

        src_dir = str(idea_dir_path / "src")
        structure_path = str(idea_dir_path / "src" / "structure.md")
        plan_path = str(idea_dir_path / "experiment_plan.md")

        venv_dir = idea_dir_path / "src" / ".venv"
        venv_path = str(venv_dir) if venv_dir.exists() else ""

        # 自动检测回退路径（调用方可不传）
        if not analysis_path:
            f = idea_dir_path / "analysis.md"
            if f.exists():
                analysis_path = str(f)
        if not debug_report_path:
            f = idea_dir_path / "src" / "debug_report.md"
            if f.exists():
                debug_report_path = str(f)

        prompt = agent.build_prompt(
            idea_dir=str(idea_dir_path),
            src_dir=src_dir,
            structure_path=structure_path,
            plan_path=plan_path,
            analysis_path=analysis_path,
            debug_report_path=debug_report_path,
            venv_path=venv_path,
        )

        result = agent.run(prompt)

        self._log_phase_end("debug", idea_id, result[:200])

        print(f"\nDebug 完成! 请 review: {src_dir}/debug_report.md")
        return result

    def phase_deep_survey(self, queries: list = None, round_num: int = 2) -> str:
        """深度文献调研：针对特定方向补充文献

        Args:
            queries: 补充搜索关键词（暂未使用）
            round_num: 调研轮次，默认 2（表示第二轮深度调研）
        """
        self._log_phase_start("deep_survey")
        result = self.phase_survey(round_num=round_num)
        self._log_phase_end("deep_survey", summary=result[:200])
        return result

    # === 辅助方法 ===

    def _read_results_dir(self, dir_path: str) -> str:
        """读取结果目录中的文件"""
        info = ""
        if not os.path.exists(dir_path):
            return info
        for f in sorted(os.listdir(dir_path)):
            fpath = os.path.join(dir_path, f)
            if f.endswith((".txt", ".md", ".csv", ".json")) and os.path.isfile(fpath):
                info += f"\n#### {f}\n{read_file(fpath)[:10000]}\n"
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
            info += f"\n#### 综合分析\n{read_file(analysis_path)[:10000]}\n"
        return info

    def _setup_idea_env(self, idea_id: str, src_dir) -> str:
        """为 idea 创建 venv 并安装依赖"""
        from tools.venv_manager import setup_idea_venv
        from pathlib import Path
        src_dir = Path(src_dir)
        req_path = src_dir / "requirements.txt"
        if not req_path.exists():
            return "未找到 requirements.txt，跳过环境配置"
        return setup_idea_venv(idea_src_dir=str(src_dir))

    def _get_topic_id(self) -> str:
        """获取当前 topic ID"""
        if self.topic_dir:
            basename = os.path.basename(self.topic_dir)
            match = re.match(r"(T\d+)", basename)
            if match:
                return match.group(1)
        return ""

    def status(self, topic_id: str = None) -> str:
        """打印研究状态（从 idea_registry + fsm_state 读取）"""
        try:
            return self.registry.read_research_status()
        except FileNotFoundError:
            return "未找到 idea_registry.yaml。"
        except Exception as e:
            return f"读取状态失败: {e}"
