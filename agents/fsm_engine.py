"""FSM 引擎：管理 topic 和 idea 级别的状态流转

三层分离架构：
- 工作 Agent（执行任务）→ 评估 Agent（做判断）→ FSM 引擎（路由 + 持久化）
"""

import os
import json
import logging
import tempfile
from datetime import datetime

import yaml

from shared.models.fsm import (
    FSMState, FSMSnapshot, IdeaFSMState,
    AnalysisVerdict, TheoryVerdict, DebugVerdict, SurveyVerdict,
)
from shared.models.decisions import AnalysisDecision, DebugDecision
from shared.models.audit import TransitionRecord
from shared.models.enums import IdeaStatus
from shared.paths import PathManager
from tools.file_ops import read_file

logger = logging.getLogger(__name__)


# 最大重试次数
MAX_RETRIES = {
    "refine": 4,
    "theory_check": 3,
    "debug": 6,
    "experiment": 6,  # tune loop
    "survey": 4,      # deep survey rounds
}

# Topic 级线性转换表
TOPIC_TRANSITIONS = {
    "elaborate": "survey",
    "survey": "ideation",       # 经过 SurveyEvaluator 可能回到 survey
    "deep_survey": "ideation",  # deep_survey 完成后进入 ideation
    "ideation": "completed",    # spawn per-idea FSM
}

# Idea 级线性转换表（无评估器的自动转换）
IDEA_LINEAR_TRANSITIONS = {
    "refine": "theory_check",
    "code_reference": "code",
    "code": "debug",
    "experiment": "analyze",
}

# 需要用户确认的转换（from_state, to_state）
USER_CONFIRM_TRANSITIONS = {
    # 回退跳转
    ("analyze", "refine"),
    ("analyze", "deep_survey"),
    ("analyze", "abandoned"),
    ("theory_check", "abandoned"),
    ("theory_check", "refine"),
    ("debug", "refine"),
    # 用户选择
    ("survey", "ideation"),
}


class ResearchFSM:
    """有限状态机引擎，管理 topic 和 idea 级别的状态流转"""

    def __init__(self, paths: PathManager, config_path: str = "",
                 auto: bool = False):
        self.paths = paths
        self.auto = auto
        self.snapshot = self._load_snapshot()

        # 延迟初始化评估器（避免循环导入）
        self._evaluators = None
        # 延迟初始化 IdeaRegistryService（避免循环导入）
        self._registry = None

    @property
    def registry(self):
        if self._registry is None:
            from tools.idea_registry import IdeaRegistryService
            self._registry = IdeaRegistryService(self.paths)
        return self._registry

    @property
    def evaluators(self):
        if self._evaluators is None:
            from agents.evaluators import (
                AnalysisEvaluator, TheoryEvaluator, SurveyEvaluator,
            )
            self._evaluators = {
                "analyze": AnalysisEvaluator(),
                "theory_check": TheoryEvaluator(),
                "survey": SurveyEvaluator(),
            }
        return self._evaluators

    # ── 公开接口 ─────────────────────────────────────────────

    def run_topic(self, start_state: str = None) -> str:
        """运行 topic 级 FSM (elaborate → survey → ideation)"""
        if start_state:
            self.snapshot.topic_state = start_state
            self._persist_snapshot()

        state = self.snapshot.topic_state
        results = []

        while state not in ("completed", "ideation"):
            print(f"\n[FSM] Topic 状态: {state}")

            # 执行当前状态
            result = self._execute_topic_state(state)
            results.append(f"{state}: done")

            # 评估转换
            next_state, decision = self._evaluate_topic_transition(state)

            # auto 模式：施加重试上限
            if self.auto and state in MAX_RETRIES:
                survey_rounds = self.snapshot.topic_retry_counts.get("survey", 0)
                if survey_rounds >= MAX_RETRIES.get("survey", 3):
                    next_state = "ideation"

            # 用户确认（仅 interactive 模式）
            if not self.auto:
                next_state = self._prompt_user_topic(state, next_state, decision)

            # 用户选择退出：保留当前状态，不记录转换
            if next_state == "_quit":
                return f"用户退出，当前状态保留为 {state}"

            # 记录转换
            verdict_summary = self._extract_summary(decision)
            trigger = f"eval:{decision.get('verdict', 'auto')}" if isinstance(decision, dict) and decision.get("verdict") else "auto:linear"
            self._record_transition(state, next_state, trigger,
                                     verdict_summary=verdict_summary)

            # 更新 topic retry count
            self.snapshot.topic_retry_counts[state] = \
                self.snapshot.topic_retry_counts.get(state, 0) + 1

            self.snapshot.topic_state = next_state
            self._persist_snapshot()
            state = next_state

        if state == "ideation":
            # 执行 ideation
            result = self._execute_topic_state("ideation")
            results.append("ideation: done")
            self.snapshot.topic_state = "completed"
            self._persist_snapshot()

        return "\n".join(results)

    def run_idea(self, idea_id: str, start_state: str = None) -> str:
        """运行单个 idea 的 FSM"""
        # 初始化或恢复 idea FSM 状态
        if idea_id not in self.snapshot.idea_states:
            self.snapshot.idea_states[idea_id] = IdeaFSMState()

        idea_fsm = self.snapshot.idea_states[idea_id]
        if start_state:
            idea_fsm.current_state = start_state
            self._persist_snapshot()

        state = idea_fsm.current_state
        results = []
        feedback = ""  # 运行时内存传递，不持久化

        while state not in ("completed", "abandoned", "conclude"):
            print(f"\n[FSM] {idea_id} 状态: {state} "
                  f"(S{idea_fsm.step_id}/V{idea_fsm.version})")

            # 执行当前状态
            result = self._execute_idea_state(state, idea_id, idea_fsm, feedback)
            results.append(f"{state}: done")

            # 评估转换
            next_state, decision = self._evaluate_idea_transition(
                state, idea_id, idea_fsm)

            # auto 模式：施加重试上限
            if self.auto and state in MAX_RETRIES:
                retry_count = idea_fsm.retry_counts.get(state, 0)
                if retry_count >= MAX_RETRIES[state]:
                    if state == "analyze":
                        met_ratio = decision.get("expectations_met_ratio", 0) \
                            if isinstance(decision, dict) else 0
                        next_state = "conclude" if met_ratio >= 0.3 else "abandoned"
                    else:
                        next_state = "abandoned"

            # 处理版本递增
            if state == "analyze" and next_state == "experiment":
                idea_fsm.version += 1

            # 用户确认（仅 interactive 模式）
            if not self.auto and self._needs_user_confirm(state, next_state):
                final = self._prompt_user_idea(
                    state, next_state, decision, idea_id, idea_fsm)
                next_state = final

            # 用户选择退出：保留当前状态，不记录转换
            if next_state == "_quit":
                return f"用户退出，{idea_id} 状态保留为 {state}"

            # 记录
            verdict_summary = self._extract_summary(decision)
            trigger = f"eval:{decision.get('verdict', 'auto')}" if isinstance(decision, dict) and "verdict" in decision else "auto:linear"
            self._record_transition(state, next_state, trigger,
                                     idea_id=idea_id,
                                     verdict_summary=verdict_summary)

            # 更新 retry count
            idea_fsm.retry_counts[state] = idea_fsm.retry_counts.get(state, 0) + 1

            # 提取 feedback（运行时传递，不持久化）
            if isinstance(decision, dict):
                feedback = decision.get("next_action_detail", "") or \
                           "; ".join(decision.get("revision_suggestions", []))
            else:
                feedback = ""

            idea_fsm.current_state = next_state
            self._persist_snapshot()
            state = next_state

        # 处理终态
        if state == "conclude":
            result = self._execute_idea_state("conclude", idea_id, idea_fsm, feedback)
            results.append("conclude: done")
            idea_fsm.current_state = "completed"
            self._persist_snapshot()
        elif state == "abandoned":
            results.append("abandoned")
            self._mark_idea_abandoned(idea_id)

        return "\n".join(results)

    def step(self, idea_id: str = None) -> TransitionRecord | None:
        """执行一步状态转换"""
        if idea_id:
            if idea_id not in self.snapshot.idea_states:
                self.snapshot.idea_states[idea_id] = IdeaFSMState()
            idea_fsm = self.snapshot.idea_states[idea_id]
            state = idea_fsm.current_state

            if state in ("completed", "abandoned"):
                print(f"[FSM] {idea_id} 已在终态: {state}")
                return None

            self._execute_idea_state(state, idea_id, idea_fsm, "")
            next_state, decision = self._evaluate_idea_transition(state, idea_id, idea_fsm)

            # auto 模式：施加重试上限
            if self.auto and state in MAX_RETRIES:
                retry_count = idea_fsm.retry_counts.get(state, 0)
                if retry_count >= MAX_RETRIES[state]:
                    if state == "analyze":
                        met_ratio = decision.get("expectations_met_ratio", 0) \
                            if isinstance(decision, dict) else 0
                        next_state = "conclude" if met_ratio >= 0.3 else "abandoned"
                    else:
                        next_state = "abandoned"

            if not self.auto and self._needs_user_confirm(state, next_state):
                next_state = self._prompt_user_idea(state, next_state, decision, idea_id, idea_fsm)

            if next_state == "_quit":
                print(f"\n[FSM] 用户退出，{idea_id} 状态保留为 {state}")
                return None

            verdict_summary = self._extract_summary(decision)
            trigger = f"eval:{decision.get('verdict', 'auto')}" if isinstance(decision, dict) and "verdict" in decision else "auto:linear"
            record = self._record_transition(state, next_state, trigger, idea_id=idea_id,
                                              verdict_summary=verdict_summary)

            idea_fsm.retry_counts[state] = idea_fsm.retry_counts.get(state, 0) + 1
            idea_fsm.current_state = next_state
            if state == "analyze" and next_state == "experiment":
                idea_fsm.version += 1
            self._persist_snapshot()
            return record
        else:
            # topic step
            state = self.snapshot.topic_state
            if state == "completed":
                print("[FSM] Topic 已完成")
                return None

            self._execute_topic_state(state)
            next_state, decision = self._evaluate_topic_transition(state)

            # auto 模式：施加重试上限
            if self.auto and state in MAX_RETRIES:
                survey_rounds = self.snapshot.topic_retry_counts.get("survey", 0)
                if survey_rounds >= MAX_RETRIES.get("survey", 3):
                    next_state = "ideation"

            if not self.auto:
                next_state = self._prompt_user_topic(state, next_state, decision)

            if next_state == "_quit":
                print(f"\n[FSM] 用户退出，Topic 状态保留为 {state}")
                return None

            verdict_summary = self._extract_summary(decision)
            trigger = f"eval:{decision.get('verdict', 'auto')}" if isinstance(decision, dict) and decision.get("verdict") else "auto:linear"
            record = self._record_transition(state, next_state, trigger,
                                              verdict_summary=verdict_summary)
            self.snapshot.topic_retry_counts[state] = \
                self.snapshot.topic_retry_counts.get(state, 0) + 1
            self.snapshot.topic_state = next_state
            self._persist_snapshot()
            return record

    def force_transition(self, idea_id: str, target_state: str, feedback: str = ""):
        """用户强制跳转到指定状态"""
        if idea_id not in self.snapshot.idea_states:
            self.snapshot.idea_states[idea_id] = IdeaFSMState()

        idea_fsm = self.snapshot.idea_states[idea_id]
        from_state = idea_fsm.current_state

        self._record_transition(from_state, target_state,
                                 f"user:force_to_{target_state}",
                                 idea_id=idea_id)

        idea_fsm.current_state = target_state
        self._persist_snapshot()

        print(f"[FSM] {idea_id}: {from_state} → {target_state} (forced)")

    def status(self) -> str:
        """打印所有 FSM 状态"""
        lines = [f"[FSM Status]",
                 f"  Topic: {self.snapshot.topic_state}"]

        for idea_id, state in sorted(self.snapshot.idea_states.items()):
            retries = ", ".join(f"{k}:{v}" for k, v in state.retry_counts.items() if v > 0)
            retry_str = f" retries=[{retries}]" if retries else ""
            lines.append(
                f"  {idea_id}: {state.current_state} "
                f"(S{state.step_id}/V{state.version}){retry_str}")

        return "\n".join(lines)

    def history(self, idea_id: str = None) -> list[TransitionRecord]:
        """从 audit_log.yaml 读取状态转换历史"""
        audit_path = self.paths.audit_log_yaml
        if not audit_path.exists():
            return []
        try:
            raw = yaml.safe_load(audit_path.read_text(encoding="utf-8")) or {}
            records = [TransitionRecord(**r) for r in raw.get("records", [])]
        except Exception:
            return []
        if idea_id:
            records = [r for r in records if r.idea_id == idea_id]
        return records

    # ── 状态执行 ─────────────────────────────────────────────

    def _execute_topic_state(self, state: str) -> str:
        """调用 orchestrator 方法执行 topic 级状态"""
        from agents.orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator(
            topic_dir=str(self.paths.topic_dir),
        )

        if state == "elaborate":
            return orch.phase_elaborate()
        elif state in ("survey", "deep_survey"):
            round_num = self.snapshot.topic_retry_counts.get("survey", 0) + 1
            return orch.phase_survey(round_num=round_num)
        elif state == "ideation":
            return orch.phase_ideation()
        else:
            logger.warning(f"未知的 topic 状态: {state}")
            return ""

    def _execute_idea_state(self, state: str, idea_id: str,
                            idea_fsm: IdeaFSMState, feedback: str = "") -> str:
        """调用 orchestrator 方法执行 idea 级状态"""
        from agents.orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator(
            topic_dir=str(self.paths.topic_dir),
        )

        if state == "refine":
            return orch.phase_refine(idea_id)
        elif state == "theory_check":
            return self._run_theory_check(idea_id, idea_fsm, feedback)
        elif state == "code_reference":
            return orch.phase_code_reference(idea_id)
        elif state == "code":
            return orch.phase_code(idea_id)
        elif state == "debug":
            return self._run_debug(idea_id, idea_fsm)
        elif state == "experiment":
            return orch.phase_experiment(
                idea_id, step_id=idea_fsm.step_id, version=idea_fsm.version)
        elif state == "analyze":
            return orch.phase_analyze(
                idea_id, step_id=idea_fsm.step_id, version=idea_fsm.version)
        elif state == "deep_survey":
            return orch.phase_survey()
        elif state == "conclude":
            return orch.phase_conclude(idea_id)
        else:
            logger.warning(f"未知的 idea 状态: {state}")
            return ""

    def _run_theory_check(self, idea_id: str, idea_fsm: IdeaFSMState,
                          feedback: str = "") -> str:
        """运行 TheoryCheckAgent"""
        from agents.theory_check_agent import TheoryCheckAgent

        agent = TheoryCheckAgent(str(self.paths.topic_dir))

        refinement_dir = self.paths.idea_refinement_dir(idea_id)
        if not refinement_dir:
            return f"未找到 refinement 目录: {idea_id}"

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

        return agent.run(prompt)

    def _run_debug(self, idea_id: str, idea_fsm: IdeaFSMState) -> str:
        """运行 DebugAgent"""
        from agents.orchestrator import ResearchOrchestrator

        orch = ResearchOrchestrator(
            topic_dir=str(self.paths.topic_dir),
        )

        idea_dir = self.paths.idea_dir(idea_id)
        if not idea_dir:
            return f"未找到 idea 目录: {idea_id}"

        analysis_path = ""
        analysis_file = idea_dir / "analysis.md"
        if analysis_file.exists():
            analysis_path = str(analysis_file)

        debug_report_path = ""
        debug_report_file = idea_dir / "src" / "debug_report.md"
        if debug_report_file.exists():
            debug_report_path = str(debug_report_file)

        return orch.phase_debug(
            idea_id,
            analysis_path=analysis_path,
            debug_report_path=debug_report_path,
        )

    # ── 转换评估 ─────────────────────────────────────────────

    def _evaluate_topic_transition(self, state: str) -> tuple[str, dict]:
        """评估 topic 级转换"""
        if state == "survey":
            ctx = self._gather_survey_eval_context()
            raw = self.evaluators["survey"].evaluate(ctx)
            decision = self.evaluators["survey"].parse_decision(raw)

            if decision.verdict == SurveyVerdict.sufficient:
                return "ideation", raw
            else:
                survey_rounds = self.snapshot.topic_retry_counts.get("survey", 0)
                if survey_rounds >= MAX_RETRIES.get("survey", 3):
                    return "ideation", raw
                return "survey", raw
        else:
            next_state = TOPIC_TRANSITIONS.get(state, "completed")
            return next_state, {}

    def _evaluate_idea_transition(self, state: str, idea_id: str,
                                   idea_fsm: IdeaFSMState) -> tuple[str, dict]:
        """评估 idea 级转换"""
        retry_count = idea_fsm.retry_counts.get(state, 0)

        if state == "analyze":
            return self._route_analysis(idea_id, idea_fsm, retry_count)
        elif state == "theory_check":
            return self._route_theory_check(idea_id, idea_fsm, retry_count)
        elif state == "debug":
            return self._route_debug(idea_id, idea_fsm, retry_count)
        else:
            next_state = IDEA_LINEAR_TRANSITIONS.get(state, "completed")
            return next_state, {}

    def _route_analysis(self, idea_id: str, idea_fsm: IdeaFSMState,
                         retry_count: int) -> tuple[str, dict]:
        """ANALYZE 后的路由决策"""
        ctx = self._gather_analysis_eval_context(idea_id, idea_fsm)
        raw = self.evaluators["analyze"].evaluate(ctx)
        decision = self.evaluators["analyze"].parse_decision(raw)

        met_ratio = decision.expectations_met_ratio

        if decision.verdict == AnalysisVerdict.success and met_ratio >= 0.7:
            return "conclude", raw
        if decision.verdict == AnalysisVerdict.tune:
            return "experiment", raw
        if decision.verdict == AnalysisVerdict.code_bug or \
           decision.failure_category == "implementation":
            return "debug", raw
        if decision.verdict in (AnalysisVerdict.enrich, AnalysisVerdict.restructure):
            return "refine", raw
        if decision.verdict == AnalysisVerdict.need_literature:
            return "deep_survey", raw
        if decision.verdict == AnalysisVerdict.abandon:
            return "abandoned", raw
        return "experiment", raw

    def _route_theory_check(self, idea_id: str, idea_fsm: IdeaFSMState,
                             retry_count: int) -> tuple[str, dict]:
        """THEORY_CHECK 后的路由决策"""
        ctx = self._gather_theory_eval_context(idea_id)
        raw = self.evaluators["theory_check"].evaluate(ctx)
        decision = self.evaluators["theory_check"].parse_decision(raw)

        if decision.verdict == TheoryVerdict.sound:
            return "code_reference", raw
        if decision.verdict == TheoryVerdict.flawed:
            return "abandoned", raw
        return "refine", raw

    def _route_debug(self, idea_id: str, idea_fsm: IdeaFSMState,
                      retry_count: int) -> tuple[str, dict]:
        """DEBUG 后的路由决策"""
        decision = self._parse_debug_report(idea_id)
        raw = decision.model_dump()

        if decision.verdict == DebugVerdict.tests_pass:
            return "experiment", raw
        if decision.verdict == DebugVerdict.fixable:
            return "debug", raw
        if decision.verdict == DebugVerdict.needs_rewrite:
            return "code", raw
        if decision.verdict == DebugVerdict.design_issue:
            return "refine", raw
        return "debug", raw

    # ── 上下文收集 ───────────────────────────────────────────

    def _gather_survey_eval_context(self) -> dict:
        survey = self._safe_read(str(self.paths.survey_md))
        paper_list = self._safe_read(str(self.paths.paper_list_yaml))
        context = self._safe_read(str(self.paths.context_md))
        return {"survey": survey, "paper_list": paper_list, "context": context}

    def _gather_analysis_eval_context(self, idea_id: str,
                                       idea_fsm: IdeaFSMState) -> dict:
        idea_dir = self.paths.idea_dir(idea_id)
        analysis_md = ""
        metrics_json = ""
        experiment_plan = ""

        if idea_dir:
            analysis_path = idea_dir / "analysis.md"
            if analysis_path.exists():
                analysis_md = read_file(str(analysis_path))

            plan_path = idea_dir / "experiment_plan.md"
            if plan_path.exists():
                experiment_plan = read_file(str(plan_path))

            v_dir = self.paths.version_dir(idea_id, idea_fsm.step_id, idea_fsm.version)
            if v_dir:
                metrics_path = v_dir / "metrics.json"
                if metrics_path.exists():
                    metrics_json = read_file(str(metrics_path))
                v_analysis = v_dir / "analysis.md"
                if v_analysis.exists():
                    analysis_md = read_file(str(v_analysis))

        iteration_history = self._build_iteration_history(idea_id, idea_fsm)

        return {
            "analysis_md": analysis_md,
            "metrics_json": metrics_json,
            "experiment_plan": experiment_plan,
            "iteration_history": iteration_history,
            "retry_count": idea_fsm.retry_counts.get("experiment", 0),
            "max_retries": MAX_RETRIES["experiment"],
        }

    def _gather_theory_eval_context(self, idea_id: str) -> dict:
        refinement_dir = self.paths.idea_refinement_dir(idea_id)
        theory_review = ""
        if refinement_dir:
            review_path = refinement_dir / "theory_review.md"
            if review_path.exists():
                theory_review = read_file(str(review_path))

        survey = self._safe_read(str(self.paths.survey_md))
        proposal_path = self.paths.idea_proposal(idea_id)
        proposal = read_file(str(proposal_path)) if proposal_path and proposal_path.exists() else ""

        other_ideas_summary = self._gather_other_ideas_summary(idea_id)

        return {
            "theory_review": theory_review,
            "survey": survey,
            "proposal": proposal,
            "other_ideas_summary": other_ideas_summary,
        }

    def _gather_other_ideas_summary(self, current_idea_id: str) -> str:
        summaries = []
        for idea_id, idea_fsm in self.snapshot.idea_states.items():
            if idea_id == current_idea_id:
                continue

            parts = []

            proposal_path = self.paths.idea_proposal(idea_id)
            if proposal_path and proposal_path.exists():
                proposal_text = read_file(str(proposal_path))
                parts.append(f"Proposal: {proposal_text[:500]}")

            refinement_dir = self.paths.idea_refinement_dir(idea_id)
            if refinement_dir:
                review_path = refinement_dir / "theory_review.md"
                if review_path.exists():
                    review_text = read_file(str(review_path))
                    parts.append(f"Theory Review: {review_text[:300]}")

            if parts:
                summaries.append(f"### {idea_id}\n" + "\n".join(parts))

        return "\n\n".join(summaries) if summaries else ""

    def _build_iteration_history(self, idea_id: str,
                                  idea_fsm: IdeaFSMState) -> str:
        lines = []
        results_dir = self.paths.idea_results_dir(idea_id)
        if not results_dir or not results_dir.exists():
            return "无历史迭代数据"

        step_dir = self.paths.step_dir(idea_id, idea_fsm.step_id)
        if not step_dir or not step_dir.exists():
            return "无历史迭代数据"

        for v in range(1, idea_fsm.version + 1):
            v_dir = step_dir / f"V{v}"
            if not v_dir.exists():
                continue
            metrics_path = v_dir / "metrics.json"
            if metrics_path.exists():
                try:
                    metrics = json.loads(read_file(str(metrics_path)))
                    lines.append(f"V{v}: {json.dumps(metrics, ensure_ascii=False)}")
                except (json.JSONDecodeError, Exception):
                    lines.append(f"V{v}: metrics 解析失败")

        return "\n".join(lines) if lines else "无历史迭代数据"

    def _parse_debug_report(self, idea_id: str) -> DebugDecision:
        idea_dir = self.paths.idea_dir(idea_id)
        if not idea_dir:
            return DebugDecision(verdict=DebugVerdict.fixable)

        report_path = idea_dir / "src" / "debug_report.md"
        if not report_path.exists():
            return DebugDecision(verdict=DebugVerdict.fixable,
                                 details="debug_report.md 不存在")

        content = read_file(str(report_path))
        content_lower = content.lower()

        if "all tests pass" in content_lower or "所有测试通过" in content:
            return DebugDecision(verdict=DebugVerdict.tests_pass, details=content[:500])

        if "design issue" in content_lower or "设计问题" in content or "设计层面" in content:
            return DebugDecision(verdict=DebugVerdict.design_issue, details=content[:500])

        if "needs rewrite" in content_lower or "需要重写" in content or "重写模块" in content:
            return DebugDecision(verdict=DebugVerdict.needs_rewrite, details=content[:500])

        return DebugDecision(verdict=DebugVerdict.fixable, details=content[:500])

    # ── 用户交互 ─────────────────────────────────────────────

    def _needs_user_confirm(self, from_state: str, to_state: str) -> bool:
        return (from_state, to_state) in USER_CONFIRM_TRANSITIONS

    def _prompt_user_topic(self, from_state: str, to_state: str,
                            decision: dict) -> str:
        print(f"\n[FSM] {from_state.upper()} 完成")

        if isinstance(decision, dict) and decision:
            verdict = decision.get("verdict", "")
            confidence = decision.get("confidence", "")
            print(f"\n  判定: {verdict}" +
                  (f" (confidence: {confidence})" if confidence else ""))

            if decision.get("gap_areas"):
                print(f"  缺失方向: {', '.join(decision['gap_areas'])}")

            if decision.get("coverage_summary"):
                print(f"  覆盖情况: {decision['coverage_summary']}")

            detail = decision.get("next_action_detail", "")
            if detail:
                print(f"  建议: {detail}")

            suggestions = decision.get("revision_suggestions", [])
            if suggestions:
                print(f"  改进方向:")
                for s in suggestions[:3]:
                    print(f"    - {s}")

        survey_rounds = self.snapshot.topic_retry_counts.get("survey", 0)
        if survey_rounds > 0:
            print(f"\n  已完成 survey 轮次: {survey_rounds}/{MAX_RETRIES.get('survey', 3)}")

        print(f"\n  推荐 → {to_state.upper()}")
        print(f"  可选: [e]laborate | [s]urvey | [d]eep-survey | [i]deation | [q]uit")

        mapping = {
            "e": "elaborate",
            "s": "survey",
            "d": "deep_survey",
            "i": "ideation",
            "q": "_quit",
        }
        while True:
            try:
                choice = input("\n  Enter 接受推荐，或输入选项: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n  [FSM] 中断，保留当前状态")
                return "_quit"
            if not choice:
                return to_state
            if choice in mapping:
                return mapping[choice]
            print(f"  无效输入 '{choice}'，请选择: e/s/d/i/q")

    def _prompt_user_idea(self, from_state: str, to_state: str,
                           decision: dict, idea_id: str,
                           idea_fsm: IdeaFSMState) -> str:
        print(f"\n[FSM] {from_state.upper()} 完成 — {idea_id} "
              f"S{idea_fsm.step_id}/V{idea_fsm.version}")

        if isinstance(decision, dict):
            verdict = decision.get("verdict", "")
            confidence = decision.get("confidence", "")
            print(f"\n  判定: {verdict}" +
                  (f" (confidence: {confidence})" if confidence else ""))

            metrics_b = decision.get("metrics_vs_baseline", {})
            metrics_e = decision.get("metrics_vs_expectation", {})
            if metrics_b:
                print(f"\n  指标摘要:")
                for m, v in metrics_b.items():
                    if isinstance(v, dict):
                        baseline = v.get("baseline", "?")
                        actual = v.get("actual", "?")
                        delta = v.get("delta_pct", "?")
                        met = ""
                        if m in metrics_e and isinstance(metrics_e[m], dict):
                            met = " ✓" if metrics_e[m].get("met") else " ✗"
                        print(f"    {m}: baseline {baseline} → actual {actual} "
                              f"({delta}%){met}")

            trend = decision.get("iteration_trend", "")
            if trend:
                print(f"\n  迭代趋势: {trend}")

            detail = decision.get("next_action_detail", "")
            if detail:
                print(f"  建议: {detail}")

            issues = decision.get("issues", [])
            if issues:
                print(f"  问题: {', '.join(str(i) for i in issues[:3])}")

        print(f"\n  推荐 → {to_state.upper()}")
        print(f"  可选: [e]xperiment | [r]efine | [d]eep-survey | "
              f"[a]bandon | [c]onclude | [q]uit")

        mapping = {
            "e": "experiment",
            "r": "refine",
            "d": "deep_survey",
            "a": "abandoned",
            "c": "conclude",
            "q": "_quit",
        }
        while True:
            try:
                choice = input("\n  Enter 接受推荐，或输入选项: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n  [FSM] 中断，保留当前状态")
                return "_quit"
            if not choice:
                return to_state
            if choice in mapping:
                return mapping[choice]
            print(f"  无效输入 '{choice}'，请选择: e/r/d/a/c/q")

    # ── 持久化 ───────────────────────────────────────────────

    def _persist_snapshot(self):
        """原子写入 FSM 快照到 {topic_dir}/fsm_state.yaml"""
        snapshot_path = self.paths.topic_dir / "fsm_state.yaml"
        data = self.snapshot.model_dump(mode="json")
        content = yaml.dump(data, allow_unicode=True, default_flow_style=False)
        # 原子写入：先写临时文件，再 rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.paths.topic_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
            os.replace(tmp_path, str(snapshot_path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _load_snapshot(self) -> FSMSnapshot:
        """加载 FSM 快照，支持崩溃恢复"""
        snapshot_path = self.paths.topic_dir / "fsm_state.yaml"
        if snapshot_path.exists():
            try:
                with open(snapshot_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                # 兼容旧版：忽略已移除的字段
                data.pop("transition_history", None)
                for idea_state in data.get("idea_states", {}).values():
                    if isinstance(idea_state, dict):
                        idea_state.pop("feedback", None)
                return FSMSnapshot(**data)
            except Exception as e:
                logger.warning(f"FSM 快照加载失败: {e}，尝试从文件系统恢复")
                snapshot = self._recover_from_filesystem()
                self.snapshot = snapshot
                self._persist_snapshot()
                return snapshot
        return FSMSnapshot()

    def _recover_from_filesystem(self) -> FSMSnapshot:
        """从文件系统推断 FSM 状态（不依赖 research_tree）"""
        snapshot = FSMSnapshot()

        # 推断 topic 状态
        ideas_dir = self.paths.ideas_dir
        if ideas_dir.exists() and any(ideas_dir.iterdir()):
            snapshot.topic_state = "completed"
        elif self.paths.survey_md.exists():
            snapshot.topic_state = "ideation"
        elif self.paths.context_md.exists():
            snapshot.topic_state = "survey"
        else:
            snapshot.topic_state = "elaborate"

        # 推断 idea 状态
        if not ideas_dir.exists():
            return snapshot

        for idea_id in self.paths.list_idea_ids():
            idea_dir = self.paths.idea_dir(idea_id)
            if not idea_dir:
                continue

            # 从产出文件推断阶段（从后往前检查）
            if (idea_dir / "conclusion.md").exists():
                current = "completed"
            elif (idea_dir / "analysis.md").exists():
                current = "conclude"
            elif self.paths.idea_results_dir(idea_id) and \
                 self.paths.idea_results_dir(idea_id).exists():
                current = "analyze"
            elif (idea_dir / "src").exists():
                current = "debug"
            elif (idea_dir / "code_reference.md").exists():
                current = "code"
            elif self.paths.idea_refinement_dir(idea_id) and \
                 (self.paths.idea_refinement_dir(idea_id) / "theory_review.md").exists():
                current = "code_reference"
            elif (idea_dir / "proposal.md").exists():
                current = "theory_check"
            else:
                current = "refine"

            snapshot.idea_states[idea_id] = IdeaFSMState(current_state=current)

        return snapshot

    def _record_transition(self, from_state: str, to_state: str,
                            trigger: str, idea_id: str = "",
                            verdict_summary: str = "") -> TransitionRecord:
        """记录状态转换到 audit_log.yaml（唯一写入点）"""
        record = TransitionRecord(
            timestamp=datetime.now().isoformat(),
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            idea_id=idea_id,
            verdict_summary=verdict_summary,
        )

        # Append 到 audit_log.yaml
        audit_path = self.paths.audit_log_yaml
        try:
            if audit_path.exists():
                raw = yaml.safe_load(audit_path.read_text(encoding="utf-8")) or {}
            else:
                raw = {}
            records = raw.get("records", [])
            records.append(record.model_dump(mode="json"))
            raw["records"] = records
            audit_path.write_text(
                yaml.dump(raw, allow_unicode=True, default_flow_style=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"写入 audit_log 失败: {e}")

        return record

    def _mark_idea_abandoned(self, idea_id: str):
        """标记 idea 为 abandoned（更新 idea_registry）"""
        try:
            self.registry.update_idea_status(idea_id, "failed")
        except Exception as e:
            logger.warning(f"标记 abandoned 失败: {e}")

    def _extract_summary(self, decision: dict | None) -> str:
        """从 decision dict 提取一行摘要"""
        if not isinstance(decision, dict) or not decision:
            return ""
        # 尝试用 Decision 模型的 to_summary()
        verdict = decision.get("verdict", "")
        parts = [str(verdict)] if verdict else []
        if "coverage_score" in decision:
            parts.append(f"coverage={decision['coverage_score']}")
            gaps = decision.get("gap_areas", [])
            if gaps:
                parts.append(f"gaps: {', '.join(str(g) for g in gaps[:3])}")
        elif "confidence" in decision:
            parts.append(f"confidence={decision['confidence']}")
            if "expectations_met_ratio" in decision:
                parts.append(f"met_ratio={decision['expectations_met_ratio']}")
        elif "tests_passed" in decision:
            parts.append(f"{decision['tests_passed']}/{decision.get('tests_total', '?')} passed")
        elif "novelty_score" in decision:
            parts.append(f"novelty={decision['novelty_score']}")
        return ", ".join(parts)

    # ── 工具方法 ─────────────────────────────────────────────

    def _safe_read(self, path: str) -> str:
        if os.path.exists(path):
            return read_file(path)
        return ""
