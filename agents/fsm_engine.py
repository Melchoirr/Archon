"""FSM 引擎：管理 topic 和 idea 级别的状态流转

三层分离架构：
- 工作 Agent（执行任务）→ 评估 Agent（做判断）→ FSM 引擎（路由 + 持久化）
"""

import os
import json
import logging
from datetime import datetime

import yaml

from shared.models.fsm import (
    FSMState, FSMSnapshot, IdeaFSMState, TransitionRecord,
    AnalysisVerdict, TheoryVerdict, DebugVerdict, SurveyVerdict,
    AnalysisDecision, DebugDecision,
)
from shared.models.enums import PhaseState
from shared.paths import PathManager
from tools.research_tree import ResearchTreeService
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
    ("debug", "refine"),
    # 用户选择
    ("survey", "ideation"),
}

# FSM 状态到 research_tree IdeaPhases 字段的映射
STATE_TO_PHASE = {
    "refine": "refinement",
    "theory_check": "theory_check",
    "code_reference": "code_reference",
    "code": "coding",
    "debug": "debug",
    "experiment": "experiment",
    "analyze": "analysis",
    "conclude": "conclusion",
}


class ResearchFSM:
    """有限状态机引擎，管理 topic 和 idea 级别的状态流转"""

    def __init__(self, paths: PathManager, tree_service: ResearchTreeService,
                 config_path: str):
        self.paths = paths
        self.tree = tree_service
        self.config_path = config_path
        self.snapshot = self._load_snapshot()

        # 延迟初始化评估器（避免循环导入）
        self._evaluators = None

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

            # 用户确认
            if self._needs_user_confirm(state, next_state):
                next_state = self._prompt_user_topic(state, next_state, decision)

            # 用户选择退出：保留当前状态，不记录转换
            if next_state == "_quit":
                print(f"\n[FSM] 用户退出，当前状态保留为 {state}")
                break

            # 记录转换
            self._record_transition(state, next_state, "auto:linear",
                                     decision_snapshot=decision if isinstance(decision, dict) else None)

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

        while state not in ("completed", "abandoned", "conclude"):
            print(f"\n[FSM] {idea_id} 状态: {state} "
                  f"(S{idea_fsm.step_id}/V{idea_fsm.version})")

            # 执行当前状态
            result = self._execute_idea_state(state, idea_id, idea_fsm)
            results.append(f"{state}: done")

            # 标记阶段完成
            self._mark_phase_completed(state, idea_id)

            # 评估转换
            next_state, decision = self._evaluate_idea_transition(
                state, idea_id, idea_fsm)

            # 处理版本递增
            if state == "analyze" and next_state == "experiment":
                idea_fsm.version += 1

            # 用户确认
            if self._needs_user_confirm(state, next_state):
                final = self._prompt_user_idea(
                    state, next_state, decision, idea_id, idea_fsm)
                next_state = final

            # 用户选择退出：保留当前状态，不记录转换
            if next_state == "_quit":
                print(f"\n[FSM] 用户退出，{idea_id} 状态保留为 {state}")
                break

            # 记录
            trigger = f"eval:{decision.get('verdict', 'auto')}" if isinstance(decision, dict) and "verdict" in decision else "auto:linear"
            self._record_transition(state, next_state, trigger,
                                     idea_id=idea_id,
                                     decision_snapshot=decision if isinstance(decision, dict) else None)

            # 更新 retry count（无条件递增，防止跨状态回退死循环）
            idea_fsm.retry_counts[next_state] = idea_fsm.retry_counts.get(next_state, 0) + 1

            # 传递 feedback
            if isinstance(decision, dict):
                idea_fsm.feedback = decision.get("next_action_detail", "") or \
                                    "; ".join(decision.get("revision_suggestions", []))
            else:
                idea_fsm.feedback = ""

            idea_fsm.current_state = next_state
            self._persist_snapshot()
            state = next_state

        # 处理终态
        if state == "conclude":
            result = self._execute_idea_state("conclude", idea_id, idea_fsm)
            results.append("conclude: done")
            self._mark_phase_completed("conclude", idea_id)
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

            self._execute_idea_state(state, idea_id, idea_fsm)
            self._mark_phase_completed(state, idea_id)
            next_state, decision = self._evaluate_idea_transition(state, idea_id, idea_fsm)

            if self._needs_user_confirm(state, next_state):
                next_state = self._prompt_user_idea(state, next_state, decision, idea_id, idea_fsm)

            if next_state == "_quit":
                print(f"\n[FSM] 用户退出，{idea_id} 状态保留为 {state}")
                return None

            trigger = f"eval:{decision.get('verdict', 'auto')}" if isinstance(decision, dict) and "verdict" in decision else "auto:linear"
            record = self._record_transition(state, next_state, trigger, idea_id=idea_id,
                                              decision_snapshot=decision if isinstance(decision, dict) else None)

            # 更新 retry count（与 run_idea 保持一致）
            idea_fsm.retry_counts[next_state] = idea_fsm.retry_counts.get(next_state, 0) + 1

            # 传递 feedback（与 run_idea 保持一致）
            if isinstance(decision, dict):
                idea_fsm.feedback = decision.get("next_action_detail", "") or \
                                    "; ".join(decision.get("revision_suggestions", []))
            else:
                idea_fsm.feedback = ""
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

            if self._needs_user_confirm(state, next_state):
                next_state = self._prompt_user_topic(state, next_state, decision)

            record = self._record_transition(state, next_state, "auto:linear")
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
                                 idea_id=idea_id, feedback=feedback)

        idea_fsm.current_state = target_state
        idea_fsm.feedback = feedback
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
        """查看状态转换历史"""
        records = self.snapshot.transition_history
        if idea_id:
            records = [r for r in records if r.idea_id == idea_id]
        return records

    # ── 状态执行 ─────────────────────────────────────────────

    def _execute_topic_state(self, state: str) -> str:
        """调用 orchestrator 方法执行 topic 级状态"""
        from agents.orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator(
            topic_dir=str(self.paths.topic_dir),
            config_path=self.config_path,
        )

        if state == "elaborate":
            return orch.phase_elaborate()
        elif state in ("survey", "deep_survey"):
            # 计算这是第几轮 survey（从 transition_history 中统计）
            round_num = sum(
                1 for r in self.snapshot.transition_history
                if r.from_state in ("survey", "deep_survey")
            ) + 1
            return orch.phase_survey(round_num=round_num)
        elif state == "ideation":
            return orch.phase_ideation()
        else:
            logger.warning(f"未知的 topic 状态: {state}")
            return ""

    def _execute_idea_state(self, state: str, idea_id: str,
                            idea_fsm: IdeaFSMState) -> str:
        """调用 orchestrator 方法执行 idea 级状态"""
        from agents.orchestrator import ResearchOrchestrator
        orch = ResearchOrchestrator(
            topic_dir=str(self.paths.topic_dir),
            config_path=self.config_path,
        )

        if state == "refine":
            return orch.phase_refine(idea_id, feedback=idea_fsm.feedback)
        elif state == "theory_check":
            return self._run_theory_check(idea_id, idea_fsm)
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

    def _run_theory_check(self, idea_id: str, idea_fsm: IdeaFSMState) -> str:
        """运行 TheoryCheckAgent"""
        from agents.theory_check_agent import TheoryCheckAgent

        agent = TheoryCheckAgent(self.config_path)

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
            feedback=idea_fsm.feedback,
        )

        return agent.run(prompt)

    def _run_debug(self, idea_id: str, idea_fsm: IdeaFSMState) -> str:
        """运行 DebugAgent"""
        from agents.debug_agent import DebugAgent

        agent = DebugAgent(self.config_path)

        idea_dir = self.paths.idea_dir(idea_id)
        if not idea_dir:
            return f"未找到 idea 目录: {idea_id}"

        src_dir = str(idea_dir / "src")
        structure_path = str(idea_dir / "src" / "structure.md")
        plan_path = str(idea_dir / "experiment_plan.md")

        venv_dir = idea_dir / "src" / ".venv"
        venv_path = str(venv_dir) if venv_dir.exists() else ""

        prompt = agent.build_prompt(
            idea_dir=str(idea_dir),
            src_dir=src_dir,
            structure_path=structure_path,
            plan_path=plan_path,
            feedback=idea_fsm.feedback,
            venv_path=venv_path,
        )

        return agent.run(prompt)

    # ── 转换评估 ─────────────────────────────────────────────

    def _evaluate_topic_transition(self, state: str) -> tuple[str, dict]:
        """评估 topic 级转换"""
        if state == "survey":
            # 调用 SurveyEvaluator
            ctx = self._gather_survey_eval_context()
            raw = self.evaluators["survey"].evaluate(ctx)
            decision = self.evaluators["survey"].parse_decision(raw)

            if decision.verdict == SurveyVerdict.sufficient:
                return "ideation", raw
            else:
                survey_rounds = sum(
                    1 for r in self.snapshot.transition_history
                    if r.to_state in ("survey", "deep_survey"))
                if survey_rounds >= MAX_RETRIES.get("survey", 3):
                    return "ideation", raw  # 超限，强制前进
                return "survey", raw
        else:
            # 线性推进
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
            # 线性推进
            next_state = IDEA_LINEAR_TRANSITIONS.get(state, "completed")
            return next_state, {}

    def _route_analysis(self, idea_id: str, idea_fsm: IdeaFSMState,
                         retry_count: int) -> tuple[str, dict]:
        """ANALYZE 后的路由决策"""
        ctx = self._gather_analysis_eval_context(idea_id, idea_fsm)
        raw = self.evaluators["analyze"].evaluate(ctx)
        decision = self.evaluators["analyze"].parse_decision(raw)

        max_retries = MAX_RETRIES["experiment"]
        met_ratio = decision.expectations_met_ratio
        trend = decision.iteration_trend

        if decision.verdict == AnalysisVerdict.success and met_ratio >= 0.7:
            return "conclude", raw

        if decision.verdict == AnalysisVerdict.tune:
            if trend == "degrading" and retry_count >= 2:
                return "refine", raw
            if retry_count < max_retries:
                return "experiment", raw
            # 超限
            if met_ratio >= 0.3:
                return "conclude", raw
            return "abandoned", raw

        if decision.verdict == AnalysisVerdict.code_bug or \
           decision.failure_category == "implementation":
            return "debug", raw

        if decision.verdict in (AnalysisVerdict.enrich, AnalysisVerdict.restructure):
            return "refine", raw

        if decision.verdict == AnalysisVerdict.need_literature:
            return "deep_survey", raw

        if decision.verdict == AnalysisVerdict.abandon:
            return "abandoned", raw

        # 兜底：超限判断
        if retry_count >= max_retries:
            if met_ratio >= 0.3:
                return "conclude", raw
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

        if decision.verdict == TheoryVerdict.weak:
            max_retries = MAX_RETRIES["theory_check"]
            if retry_count < max_retries:
                return "refine", raw
            return "abandoned", raw

        if decision.verdict == TheoryVerdict.derivative:
            max_retries = MAX_RETRIES["theory_check"]
            if retry_count < max_retries:
                return "refine", raw  # 回去差异化
            return "abandoned", raw   # 多次仍重复 → 放弃

        if decision.verdict == TheoryVerdict.flawed:
            return "abandoned", raw

        return "code_reference", raw

    def _route_debug(self, idea_id: str, idea_fsm: IdeaFSMState,
                      retry_count: int) -> tuple[str, dict]:
        """DEBUG 后的路由决策（规则判断，无 LLM）"""
        decision = self._parse_debug_report(idea_id)
        raw = decision.model_dump()

        if decision.verdict == DebugVerdict.tests_pass:
            return "experiment", raw

        max_retries = MAX_RETRIES["debug"]

        if decision.verdict == DebugVerdict.fixable:
            if retry_count < max_retries:
                return "debug", raw
            return "code", raw  # 超限 → 重写

        if decision.verdict == DebugVerdict.needs_rewrite:
            return "code", raw

        if decision.verdict == DebugVerdict.design_issue:
            return "refine", raw

        # 兜底
        if retry_count >= max_retries:
            return "code", raw
        return "debug", raw

    # ── 上下文收集 ───────────────────────────────────────────

    def _gather_survey_eval_context(self) -> dict:
        """收集 SurveyEvaluator 需要的上下文"""
        survey = self._safe_read(str(self.paths.survey_md))
        paper_list = self._safe_read(str(self.paths.paper_list_yaml))
        context = self._safe_read(str(self.paths.context_md))
        return {"survey": survey, "paper_list": paper_list, "context": context}

    def _gather_analysis_eval_context(self, idea_id: str,
                                       idea_fsm: IdeaFSMState) -> dict:
        """收集 AnalysisEvaluator 需要的上下文"""
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

            # 读取当前版本的 metrics
            v_dir = self.paths.version_dir(idea_id, idea_fsm.step_id, idea_fsm.version)
            if v_dir:
                metrics_path = v_dir / "metrics.json"
                if metrics_path.exists():
                    metrics_json = read_file(str(metrics_path))
                # 也读取版本级 analysis
                v_analysis = v_dir / "analysis.md"
                if v_analysis.exists():
                    analysis_md = read_file(str(v_analysis))

        # 构建迭代历史
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
        """收集 TheoryEvaluator 需要的上下文"""
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
        """收集同 batch 其他 idea 的摘要，用于跨 idea 去重"""
        summaries = []
        for idea_id, idea_fsm in self.snapshot.idea_states.items():
            if idea_id == current_idea_id:
                continue

            parts = []

            # 读取 proposal（前 500 字）
            proposal_path = self.paths.idea_proposal(idea_id)
            if proposal_path and proposal_path.exists():
                proposal_text = read_file(str(proposal_path))
                parts.append(f"Proposal: {proposal_text[:500]}")

            # 读取 theory_review（前 300 字，如果存在）
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
        """构建迭代历史摘要"""
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
        """解析 debug_report.md，返回 DebugDecision（规则判断）"""
        idea_dir = self.paths.idea_dir(idea_id)
        if not idea_dir:
            return DebugDecision(verdict=DebugVerdict.fixable)

        report_path = idea_dir / "src" / "debug_report.md"
        if not report_path.exists():
            return DebugDecision(verdict=DebugVerdict.fixable,
                                 details="debug_report.md 不存在")

        content = read_file(str(report_path))
        content_lower = content.lower()

        # 简单规则判断
        if "all tests pass" in content_lower or "所有测试通过" in content:
            return DebugDecision(verdict=DebugVerdict.tests_pass, details=content[:500])

        if "design issue" in content_lower or "设计问题" in content or "设计层面" in content:
            return DebugDecision(verdict=DebugVerdict.design_issue, details=content[:500])

        if "needs rewrite" in content_lower or "需要重写" in content or "重写模块" in content:
            return DebugDecision(verdict=DebugVerdict.needs_rewrite, details=content[:500])

        return DebugDecision(verdict=DebugVerdict.fixable, details=content[:500])

    # ── 用户交互 ─────────────────────────────────────────────

    def _needs_user_confirm(self, from_state: str, to_state: str) -> bool:
        """判断此转换是否需要用户确认"""
        return (from_state, to_state) in USER_CONFIRM_TRANSITIONS

    def _prompt_user_topic(self, from_state: str, to_state: str,
                            decision: dict) -> str:
        """Topic 级用户确认"""
        print(f"\n[FSM] {from_state.upper()} 完成")
        if decision:
            verdict = decision.get("verdict", "")
            print(f"  判定: {verdict}")
            if decision.get("gap_areas"):
                print(f"  缺失方向: {', '.join(decision['gap_areas'])}")

        print(f"\n  推荐 → {to_state.upper()}")
        print(f"  可选: [s]urvey | [i]deation | [q]uit")

        try:
            choice = input("\n  Enter 接受推荐，或输入选项: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  [FSM] 中断，保留当前状态")
            return "_quit"
        if choice == "q":
            return "_quit"
        elif choice == "s":
            return "survey"
        elif choice == "i":
            return "ideation"
        return to_state

    def _prompt_user_idea(self, from_state: str, to_state: str,
                           decision: dict, idea_id: str,
                           idea_fsm: IdeaFSMState) -> str:
        """Idea 级用户确认"""
        print(f"\n[FSM] {from_state.upper()} 完成 — {idea_id} "
              f"S{idea_fsm.step_id}/V{idea_fsm.version}")

        if isinstance(decision, dict):
            # 显示指标摘要
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

        try:
            choice = input("\n  Enter 接受推荐，或输入选项: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  [FSM] 中断，保留当前状态")
            return "_quit"

        mapping = {
            "e": "experiment",
            "r": "refine",
            "d": "deep_survey",
            "a": "abandoned",
            "c": "conclude",
            "q": "_quit",
        }
        return mapping.get(choice, to_state)

    # ── 持久化 ───────────────────────────────────────────────

    def _persist_snapshot(self):
        """保存 FSM 状态到 {topic_dir}/fsm_state.yaml"""
        snapshot_path = self.paths.topic_dir / "fsm_state.yaml"
        data = self.snapshot.model_dump()
        with open(snapshot_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    def _load_snapshot(self) -> FSMSnapshot:
        """加载 FSM 状态，支持崩溃恢复"""
        snapshot_path = self.paths.topic_dir / "fsm_state.yaml"
        if snapshot_path.exists():
            try:
                with open(snapshot_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                return FSMSnapshot(**data)
            except Exception as e:
                logger.warning(f"FSM 快照加载失败: {e}，尝试从 research_tree 恢复")
                return self._recover_from_tree()
        return FSMSnapshot()

    def _recover_from_tree(self) -> FSMSnapshot:
        """从 research_tree 重建 FSM 状态"""
        snapshot = FSMSnapshot()
        try:
            tree = self.tree.load()
        except Exception:
            return snapshot

        # 推断 topic 状态
        if tree.root.survey.status == "completed":
            snapshot.topic_state = "completed"
        elif tree.root.elaborate.status == "completed":
            snapshot.topic_state = "survey"
        else:
            snapshot.topic_state = "elaborate"

        # 推断 idea 状态
        for idea in tree.root.ideas:
            phases = idea.phases
            # 从后往前找最后一个 completed 的阶段
            phase_order = [
                ("conclusion", "completed"),
                ("analysis", "conclude"),
                ("experiment", "analyze"),
                ("debug", "experiment"),
                ("coding", "debug"),
                ("code_reference", "code"),
                ("theory_check", "code_reference"),
                ("refinement", "theory_check"),
            ]
            current = "refine"
            for phase_name, next_state in phase_order:
                if getattr(phases, phase_name, None) == PhaseState.completed:
                    current = next_state
                    break

            snapshot.idea_states[idea.id] = IdeaFSMState(current_state=current)

        return snapshot

    def _record_transition(self, from_state: str, to_state: str,
                            trigger: str, idea_id: str = "",
                            feedback: str = "",
                            decision_snapshot: dict = None) -> TransitionRecord:
        """记录状态转换"""
        record = TransitionRecord(
            timestamp=datetime.now().isoformat(),
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            idea_id=idea_id,
            feedback=feedback,
            decision_snapshot=decision_snapshot,
        )
        self.snapshot.transition_history.append(record)
        return record

    def _mark_phase_completed(self, state: str, idea_id: str):
        """更新 research_tree 中的阶段状态"""
        phase_name = STATE_TO_PHASE.get(state)
        if not phase_name:
            return

        try:
            tree = self.tree.load()
            for idea in tree.root.ideas:
                if idea.id == idea_id or idea.id.endswith(f"-{idea_id}"):
                    setattr(idea.phases, phase_name, PhaseState.completed)
                    self.tree.save(tree)
                    return
        except Exception as e:
            logger.warning(f"更新 research_tree 失败: {e}")

    def _mark_idea_abandoned(self, idea_id: str):
        """标记 idea 为 abandoned"""
        try:
            tree = self.tree.load()
            for idea in tree.root.ideas:
                if idea.id == idea_id or idea.id.endswith(f"-{idea_id}"):
                    idea.status = "failed"
                    self.tree.save(tree)
                    return
        except Exception as e:
            logger.warning(f"标记 abandoned 失败: {e}")

    # ── 工具方法 ─────────────────────────────────────────────

    def _safe_read(self, path: str) -> str:
        """安全读取文件，不存在返回空字符串"""
        if os.path.exists(path):
            return read_file(path)
        return ""
