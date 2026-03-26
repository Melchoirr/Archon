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
    "experiment": 6,
    "survey": 4,
}

# Topic 级线性转换表
TOPIC_TRANSITIONS = {
    "elaborate": "survey",
    "survey": "ideation",
    "deep_survey": "ideation",
    "ideation": "completed",
}

# Idea 级线性转换表（无评估器的自动转换）
IDEA_LINEAR_TRANSITIONS = {
    "refine": "theory_check",
    "code_reference": "code",
    "code": "debug",
    "experiment": "analyze",
}

# 需要用户确认的转换
USER_CONFIRM_TRANSITIONS = {
    ("analyze", "refine"),
    ("analyze", "deep_survey"),
    ("analyze", "abandoned"),
    ("theory_check", "abandoned"),
    ("theory_check", "refine"),
    ("debug", "refine"),
    ("survey", "ideation"),
}

# 用户交互选项
TOPIC_OPTIONS = {
    "e": "elaborate", "s": "survey", "d": "deep_survey",
    "i": "ideation", "q": "_quit",
}
IDEA_OPTIONS = {
    "e": "experiment", "r": "refine", "d": "deep_survey",
    "a": "abandoned", "c": "conclude", "q": "_quit",
}


class ResearchFSM:
    """有限状态机引擎，管理 topic 和 idea 级别的状态流转"""

    def __init__(self, paths: PathManager, config_path: str = "",
                 auto: bool = False):
        self.paths = paths
        self.auto = auto
        self.snapshot = self._load_snapshot()
        self._orch = None
        self._evaluators = None
        self._registry = None

    @property
    def orch(self):
        if self._orch is None:
            from agents.orchestrator import ResearchOrchestrator
            self._orch = ResearchOrchestrator(topic_dir=str(self.paths.topic_dir))
        return self._orch

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

        results = []
        while self.snapshot.topic_state not in ("completed", "ideation"):
            record = self._step_topic()
            if record is None:
                return f"用户退出，当前状态保留为 {self.snapshot.topic_state}"
            results.append(f"{record.from_state}: done")

        if self.snapshot.topic_state == "ideation":
            self._execute_topic_state("ideation")
            results.append("ideation: done")
            self.snapshot.topic_state = "completed"
            self._persist_snapshot()

        return "\n".join(results)

    def run_idea(self, idea_id: str, start_state: str = None) -> str:
        """运行单个 idea 的 FSM"""
        idea_fsm = self._ensure_idea(idea_id)
        if start_state:
            idea_fsm.current_state = start_state
            self._persist_snapshot()

        results = []
        feedback = ""

        while idea_fsm.current_state not in ("completed", "abandoned", "conclude"):
            record, feedback = self._step_idea(idea_id, feedback)
            if record is None:
                return f"用户退出，{idea_id} 状态保留为 {idea_fsm.current_state}"
            results.append(f"{record.from_state}: done")

        if idea_fsm.current_state == "conclude":
            self._execute_idea_state("conclude", idea_id, idea_fsm, feedback)
            results.append("conclude: done")
            idea_fsm.current_state = "completed"
            self._persist_snapshot()
        elif idea_fsm.current_state == "abandoned":
            results.append("abandoned")
            self._mark_idea_abandoned(idea_id)

        return "\n".join(results)

    def step(self, idea_id: str = None) -> TransitionRecord | None:
        """执行一步状态转换"""
        if idea_id:
            idea_fsm = self._ensure_idea(idea_id)
            if idea_fsm.current_state in ("completed", "abandoned"):
                print(f"[FSM] {idea_id} 已在终态: {idea_fsm.current_state}")
                return None
            record, _ = self._step_idea(idea_id, "")
            return record
        else:
            if self.snapshot.topic_state == "completed":
                print("[FSM] Topic 已完成")
                return None
            return self._step_topic()

    def force_transition(self, idea_id: str, target_state: str, feedback: str = ""):
        """用户强制跳转到指定状态"""
        idea_fsm = self._ensure_idea(idea_id)
        from_state = idea_fsm.current_state
        self._record_transition(from_state, target_state,
                                 f"user:force_to_{target_state}", idea_id=idea_id)
        idea_fsm.current_state = target_state
        self._persist_snapshot()
        print(f"[FSM] {idea_id}: {from_state} → {target_state} (forced)")

    def status(self) -> str:
        """打印所有 FSM 状态"""
        lines = ["[FSM Status]", f"  Topic: {self.snapshot.topic_state}"]
        for idea_id, state in sorted(self.snapshot.idea_states.items()):
            retries = ", ".join(f"{k}:{v}" for k, v in state.retry_counts.items() if v > 0)
            retry_str = f" retries=[{retries}]" if retries else ""
            lines.append(f"  {idea_id}: {state.current_state} "
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

    # ── 单步核心逻辑 ─────────────────────────────────────────

    def _step_topic(self) -> TransitionRecord | None:
        """Topic 级单步：执行 → 评估 → 确认 → 记录 → 更新"""
        state = self.snapshot.topic_state
        print(f"\n[FSM] Topic 状态: {state}")

        self._execute_topic_state(state)
        next_state, decision = self._evaluate_topic_transition(state)

        # auto 重试上限
        next_state = self._apply_topic_retry_limit(state, next_state)

        # 用户确认
        if not self.auto:
            next_state = self._prompt_user(
                state, next_state, decision, TOPIC_OPTIONS,
                extra_info=self._topic_prompt_info())
        if next_state == "_quit":
            return None

        # 记录 + 更新
        record = self._record_transition(
            state, next_state, self._build_trigger(decision),
            verdict_summary=self._extract_summary(decision))
        self.snapshot.topic_retry_counts[state] = \
            self.snapshot.topic_retry_counts.get(state, 0) + 1
        self.snapshot.topic_state = next_state
        self._persist_snapshot()
        return record

    def _step_idea(self, idea_id: str, feedback: str) -> tuple[TransitionRecord | None, str]:
        """Idea 级单步：执行 → 评估 → 确认 → 记录 → 更新。返回 (record, next_feedback)"""
        idea_fsm = self.snapshot.idea_states[idea_id]
        state = idea_fsm.current_state
        print(f"\n[FSM] {idea_id} 状态: {state} (S{idea_fsm.step_id}/V{idea_fsm.version})")

        self._execute_idea_state(state, idea_id, idea_fsm, feedback)
        next_state, decision = self._evaluate_idea_transition(state, idea_id, idea_fsm)

        # auto 重试上限
        next_state = self._apply_idea_retry_limit(state, next_state, idea_fsm, decision)

        # 版本递增
        if state == "analyze" and next_state == "experiment":
            idea_fsm.version += 1

        # 用户确认
        if not self.auto and (state, next_state) in USER_CONFIRM_TRANSITIONS:
            next_state = self._prompt_user(
                state, next_state, decision, IDEA_OPTIONS,
                extra_info=f"{idea_id} S{idea_fsm.step_id}/V{idea_fsm.version}")
        if next_state == "_quit":
            return None, ""

        # 记录 + 更新
        record = self._record_transition(
            state, next_state, self._build_trigger(decision),
            idea_id=idea_id, verdict_summary=self._extract_summary(decision))
        idea_fsm.retry_counts[state] = idea_fsm.retry_counts.get(state, 0) + 1

        # 提取 feedback
        next_feedback = ""
        if isinstance(decision, dict):
            next_feedback = decision.get("next_action_detail", "") or \
                            "; ".join(decision.get("revision_suggestions", []))

        idea_fsm.current_state = next_state
        self._persist_snapshot()
        return record, next_feedback

    # ── 状态执行（纯委托）────────────────────────────────────

    def _execute_topic_state(self, state: str) -> str:
        if state == "elaborate":
            return self.orch.phase_elaborate()
        elif state in ("survey", "deep_survey"):
            round_num = self.snapshot.topic_retry_counts.get("survey", 0) + 1
            return self.orch.phase_survey(round_num=round_num)
        elif state == "ideation":
            return self.orch.phase_ideation()
        else:
            logger.warning(f"未知的 topic 状态: {state}")
            return ""

    def _execute_idea_state(self, state: str, idea_id: str,
                            idea_fsm: IdeaFSMState, feedback: str = "") -> str:
        dispatch = {
            "refine": lambda: self.orch.phase_refine(idea_id),
            "theory_check": lambda: self.orch.phase_theory_check(idea_id, feedback=feedback),
            "code_reference": lambda: self.orch.phase_code_reference(idea_id),
            "code": lambda: self.orch.phase_code(idea_id),
            "debug": lambda: self.orch.phase_debug(idea_id),
            "experiment": lambda: self.orch.phase_experiment(
                idea_id, step_id=idea_fsm.step_id, version=idea_fsm.version),
            "analyze": lambda: self.orch.phase_analyze(
                idea_id, step_id=idea_fsm.step_id, version=idea_fsm.version),
            "deep_survey": lambda: self.orch.phase_survey(),
            "conclude": lambda: self.orch.phase_conclude(idea_id),
        }
        handler = dispatch.get(state)
        if handler:
            return handler()
        logger.warning(f"未知的 idea 状态: {state}")
        return ""

    # ── 转换评估 ─────────────────────────────────────────────

    def _evaluate_topic_transition(self, state: str) -> tuple[str, dict]:
        if state == "survey":
            ctx = self._gather_survey_eval_context()
            raw = self.evaluators["survey"].evaluate(ctx)
            decision = self.evaluators["survey"].parse_decision(raw)
            if decision.verdict == SurveyVerdict.sufficient:
                return "ideation", raw
            survey_rounds = self.snapshot.topic_retry_counts.get("survey", 0)
            if survey_rounds >= MAX_RETRIES.get("survey", 3):
                return "ideation", raw
            return "survey", raw
        return TOPIC_TRANSITIONS.get(state, "completed"), {}

    def _evaluate_idea_transition(self, state: str, idea_id: str,
                                   idea_fsm: IdeaFSMState) -> tuple[str, dict]:
        if state == "analyze":
            return self._route_analysis(idea_id, idea_fsm)
        elif state == "theory_check":
            return self._route_theory_check(idea_id)
        elif state == "debug":
            return self._route_debug(idea_id)
        return IDEA_LINEAR_TRANSITIONS.get(state, "completed"), {}

    def _route_analysis(self, idea_id: str, idea_fsm: IdeaFSMState) -> tuple[str, dict]:
        ctx = self._gather_analysis_eval_context(idea_id, idea_fsm)
        raw = self.evaluators["analyze"].evaluate(ctx)
        decision = self.evaluators["analyze"].parse_decision(raw)
        verdict_map = {
            AnalysisVerdict.tune: "experiment",
            AnalysisVerdict.code_bug: "debug",
            AnalysisVerdict.enrich: "refine",
            AnalysisVerdict.restructure: "refine",
            AnalysisVerdict.need_literature: "deep_survey",
            AnalysisVerdict.abandon: "abandoned",
        }
        if decision.verdict == AnalysisVerdict.success and decision.expectations_met_ratio >= 0.7:
            return "conclude", raw
        if decision.failure_category == "implementation":
            return "debug", raw
        return verdict_map.get(decision.verdict, "experiment"), raw

    def _route_theory_check(self, idea_id: str) -> tuple[str, dict]:
        ctx = self._gather_theory_eval_context(idea_id)
        raw = self.evaluators["theory_check"].evaluate(ctx)
        decision = self.evaluators["theory_check"].parse_decision(raw)
        if decision.verdict == TheoryVerdict.sound:
            return "code_reference", raw
        if decision.verdict == TheoryVerdict.flawed:
            return "abandoned", raw
        return "refine", raw

    def _route_debug(self, idea_id: str) -> tuple[str, dict]:
        decision = self._parse_debug_report(idea_id)
        raw = decision.model_dump()
        verdict_map = {
            DebugVerdict.tests_pass: "experiment",
            DebugVerdict.fixable: "debug",
            DebugVerdict.needs_rewrite: "code",
            DebugVerdict.design_issue: "refine",
        }
        return verdict_map.get(decision.verdict, "debug"), raw

    # ── 重试上限 ─────────────────────────────────────────────

    def _apply_topic_retry_limit(self, state: str, next_state: str) -> str:
        if not self.auto or state not in MAX_RETRIES:
            return next_state
        if self.snapshot.topic_retry_counts.get("survey", 0) >= MAX_RETRIES.get("survey", 3):
            return "ideation"
        return next_state

    def _apply_idea_retry_limit(self, state: str, next_state: str,
                                 idea_fsm: IdeaFSMState, decision) -> str:
        if not self.auto or state not in MAX_RETRIES:
            return next_state
        if idea_fsm.retry_counts.get(state, 0) < MAX_RETRIES[state]:
            return next_state
        if state == "analyze":
            met_ratio = decision.get("expectations_met_ratio", 0) \
                if isinstance(decision, dict) else 0
            return "conclude" if met_ratio >= 0.3 else "abandoned"
        return "abandoned"

    # ── 用户交互（统一）─────────────────────────────────────

    def _prompt_user(self, from_state: str, to_state: str,
                     decision: dict, options: dict,
                     extra_info: str = "") -> str:
        """通用用户确认交互"""
        header = f"\n[FSM] {from_state.upper()} 完成"
        if extra_info:
            header += f" — {extra_info}"
        print(header)

        if isinstance(decision, dict) and decision:
            self._print_decision_summary(decision)

        print(f"\n  推荐 → {to_state.upper()}")
        labels = " | ".join(f"[{k}]{v[1:]}" for k, v in options.items())
        print(f"  可选: {labels}")

        while True:
            try:
                choice = input("\n  Enter 接受推荐，或输入选项: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n  [FSM] 中断，保留当前状态")
                return "_quit"
            if not choice:
                return to_state
            if choice in options:
                return options[choice]
            print(f"  无效输入 '{choice}'")

    def _print_decision_summary(self, decision: dict):
        """打印评估器决策摘要"""
        verdict = decision.get("verdict", "")
        confidence = decision.get("confidence", "")
        print(f"\n  判定: {verdict}" +
              (f" (confidence: {confidence})" if confidence else ""))

        for key, label in [("gap_areas", "缺失方向"), ("coverage_summary", "覆盖情况")]:
            val = decision.get(key)
            if val:
                print(f"  {label}: {', '.join(val) if isinstance(val, list) else val}")

        detail = decision.get("next_action_detail", "")
        if detail:
            print(f"  建议: {detail}")

        for key, label in [("revision_suggestions", "改进方向"), ("issues", "问题")]:
            items = decision.get(key, [])
            if items:
                print(f"  {label}: {', '.join(str(i) for i in items[:3])}")

        metrics_b = decision.get("metrics_vs_baseline", {})
        metrics_e = decision.get("metrics_vs_expectation", {})
        if metrics_b:
            print(f"\n  指标摘要:")
            for m, v in metrics_b.items():
                if isinstance(v, dict):
                    met = ""
                    if m in metrics_e and isinstance(metrics_e[m], dict):
                        met = " ✓" if metrics_e[m].get("met") else " ✗"
                    print(f"    {m}: {v.get('baseline','?')} → {v.get('actual','?')} "
                          f"({v.get('delta_pct','?')}%){met}")

        trend = decision.get("iteration_trend", "")
        if trend:
            print(f"  迭代趋势: {trend}")

    def _topic_prompt_info(self) -> str:
        rounds = self.snapshot.topic_retry_counts.get("survey", 0)
        if rounds > 0:
            return f"survey {rounds}/{MAX_RETRIES.get('survey', 3)}"
        return ""

    # ── 上下文收集 ───────────────────────────────────────────

    def _gather_survey_eval_context(self) -> dict:
        return {
            "survey": self._safe_read(str(self.paths.survey_md)),
            "paper_list": self._safe_read(str(self.paths.paper_list_yaml)),
            "context": self._safe_read(str(self.paths.context_md)),
        }

    def _gather_analysis_eval_context(self, idea_id: str,
                                       idea_fsm: IdeaFSMState) -> dict:
        idea_dir = self.paths.idea_dir(idea_id)
        analysis_md = ""
        metrics_json = ""
        experiment_plan = ""

        if idea_dir:
            for path, target in [
                (idea_dir / "analysis.md", "analysis"),
                (idea_dir / "experiment_plan.md", "plan"),
            ]:
                if path.exists():
                    content = read_file(str(path))
                    if target == "analysis":
                        analysis_md = content
                    else:
                        experiment_plan = content

            v_dir = self.paths.version_dir(idea_id, idea_fsm.step_id, idea_fsm.version)
            if v_dir:
                for path, target in [
                    (v_dir / "metrics.json", "metrics"),
                    (v_dir / "analysis.md", "v_analysis"),
                ]:
                    if path.exists():
                        content = read_file(str(path))
                        if target == "metrics":
                            metrics_json = content
                        else:
                            analysis_md = content

        return {
            "analysis_md": analysis_md,
            "metrics_json": metrics_json,
            "experiment_plan": experiment_plan,
            "iteration_history": self._build_iteration_history(idea_id, idea_fsm),
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

        return {
            "theory_review": theory_review,
            "survey": survey,
            "proposal": proposal,
            "other_ideas_summary": self._gather_other_ideas_summary(idea_id),
        }

    def _gather_other_ideas_summary(self, current_idea_id: str) -> str:
        summaries = []
        for idea_id in self.snapshot.idea_states:
            if idea_id == current_idea_id:
                continue
            parts = []
            proposal_path = self.paths.idea_proposal(idea_id)
            if proposal_path and proposal_path.exists():
                parts.append(f"Proposal: {read_file(str(proposal_path))[:500]}")
            refinement_dir = self.paths.idea_refinement_dir(idea_id)
            if refinement_dir:
                review_path = refinement_dir / "theory_review.md"
                if review_path.exists():
                    parts.append(f"Theory Review: {read_file(str(review_path))[:300]}")
            if parts:
                summaries.append(f"### {idea_id}\n" + "\n".join(parts))
        return "\n\n".join(summaries) if summaries else ""

    def _build_iteration_history(self, idea_id: str, idea_fsm: IdeaFSMState) -> str:
        step_dir = self.paths.step_dir(idea_id, idea_fsm.step_id)
        if not step_dir or not step_dir.exists():
            return "无历史迭代数据"
        lines = []
        for v in range(1, idea_fsm.version + 1):
            metrics_path = step_dir / f"V{v}" / "metrics.json"
            if metrics_path.exists():
                try:
                    metrics = json.loads(read_file(str(metrics_path)))
                    lines.append(f"V{v}: {json.dumps(metrics, ensure_ascii=False)}")
                except Exception:
                    lines.append(f"V{v}: metrics 解析失败")
        return "\n".join(lines) if lines else "无历史迭代数据"

    def _parse_debug_report(self, idea_id: str) -> DebugDecision:
        idea_dir = self.paths.idea_dir(idea_id)
        if not idea_dir:
            return DebugDecision(verdict=DebugVerdict.fixable)
        report_path = idea_dir / "src" / "debug_report.md"
        if not report_path.exists():
            return DebugDecision(verdict=DebugVerdict.fixable, details="debug_report.md 不存在")
        content = read_file(str(report_path))
        content_lower = content.lower()
        for keyword, verdict in [
            ("all tests pass", DebugVerdict.tests_pass),
            ("所有测试通过", DebugVerdict.tests_pass),
            ("design issue", DebugVerdict.design_issue),
            ("设计问题", DebugVerdict.design_issue),
            ("设计层面", DebugVerdict.design_issue),
            ("needs rewrite", DebugVerdict.needs_rewrite),
            ("需要重写", DebugVerdict.needs_rewrite),
            ("重写模块", DebugVerdict.needs_rewrite),
        ]:
            if keyword in (content_lower if keyword.isascii() else content):
                return DebugDecision(verdict=verdict, details=content[:500])
        return DebugDecision(verdict=DebugVerdict.fixable, details=content[:500])

    # ── 持久化 ───────────────────────────────────────────────

    def _persist_snapshot(self):
        """原子写入 FSM 快照"""
        snapshot_path = self.paths.topic_dir / "fsm_state.yaml"
        content = yaml.dump(self.snapshot.model_dump(mode="json"),
                            allow_unicode=True, default_flow_style=False)
        fd, tmp_path = tempfile.mkstemp(dir=str(self.paths.topic_dir), suffix=".tmp")
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
                data = yaml.safe_load(snapshot_path.read_text(encoding="utf-8")) or {}
                data.pop("transition_history", None)
                for s in data.get("idea_states", {}).values():
                    if isinstance(s, dict):
                        s.pop("feedback", None)
                return FSMSnapshot(**data)
            except Exception as e:
                logger.warning(f"FSM 快照加载失败: {e}，尝试从文件系统恢复")
                snapshot = self._recover_from_filesystem()
                self.snapshot = snapshot
                self._persist_snapshot()
                return snapshot
        return FSMSnapshot()

    def _recover_from_filesystem(self) -> FSMSnapshot:
        """从文件系统推断 FSM 状态"""
        snapshot = FSMSnapshot()
        ideas_dir = self.paths.ideas_dir
        if ideas_dir.exists() and any(ideas_dir.iterdir()):
            snapshot.topic_state = "completed"
        elif self.paths.survey_md.exists():
            snapshot.topic_state = "ideation"
        elif self.paths.context_md.exists():
            snapshot.topic_state = "survey"

        if not ideas_dir.exists():
            return snapshot

        # 产出文件 → 阶段映射（从后往前检查）
        for idea_id in self.paths.list_idea_ids():
            idea_dir = self.paths.idea_dir(idea_id)
            if not idea_dir:
                continue
            checks = [
                (idea_dir / "conclusion.md", "completed"),
                (idea_dir / "analysis.md", "conclude"),
            ]
            results_dir = self.paths.idea_results_dir(idea_id)
            if results_dir and results_dir.exists():
                snapshot.idea_states[idea_id] = IdeaFSMState(current_state="analyze")
                continue
            more_checks = [
                (idea_dir / "src", "debug"),
                (idea_dir / "code_reference.md", "code"),
            ]
            refinement_dir = self.paths.idea_refinement_dir(idea_id)
            if refinement_dir:
                more_checks.append((refinement_dir / "theory_review.md", "code_reference"))
            more_checks.append((idea_dir / "proposal.md", "theory_check"))

            current = "refine"
            for path, state in checks + more_checks:
                if path.exists():
                    current = state
                    break
            snapshot.idea_states[idea_id] = IdeaFSMState(current_state=current)
        return snapshot

    def _record_transition(self, from_state: str, to_state: str,
                            trigger: str, idea_id: str = "",
                            verdict_summary: str = "") -> TransitionRecord:
        """记录状态转换到 audit_log.yaml"""
        record = TransitionRecord(
            timestamp=datetime.now().isoformat(),
            from_state=from_state, to_state=to_state,
            trigger=trigger, idea_id=idea_id,
            verdict_summary=verdict_summary,
        )
        audit_path = self.paths.audit_log_yaml
        try:
            raw = yaml.safe_load(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
            raw = raw or {}
            raw.setdefault("records", []).append(record.model_dump(mode="json"))
            audit_path.write_text(
                yaml.dump(raw, allow_unicode=True, default_flow_style=False),
                encoding="utf-8")
        except Exception as e:
            logger.warning(f"写入 audit_log 失败: {e}")
        return record

    def _mark_idea_abandoned(self, idea_id: str):
        try:
            self.registry.update_idea_status(idea_id, "failed")
        except Exception as e:
            logger.warning(f"标记 abandoned 失败: {e}")

    # ── 工具方法 ─────────────────────────────────────────────

    def _ensure_idea(self, idea_id: str) -> IdeaFSMState:
        if idea_id not in self.snapshot.idea_states:
            self.snapshot.idea_states[idea_id] = IdeaFSMState()
        return self.snapshot.idea_states[idea_id]

    @staticmethod
    def _build_trigger(decision: dict | None) -> str:
        if isinstance(decision, dict) and decision.get("verdict"):
            return f"eval:{decision['verdict']}"
        return "auto:linear"

    @staticmethod
    def _extract_summary(decision: dict | None) -> str:
        if not isinstance(decision, dict) or not decision:
            return ""
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

    def _safe_read(self, path: str) -> str:
        return read_file(path) if os.path.exists(path) else ""
