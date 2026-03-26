# Remove deep_survey Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `deep_survey` state and all its wiring, rerouting `need_literature` verdict to `refine`.

**Architecture:** Delete `deep_survey` from FSM states, transitions, options, dispatch, and orchestrator. Change `need_literature` verdict mapping from `deep_survey` to `refine`. Remove the `phase_deep_survey()` method.

**Tech Stack:** Python, Pydantic enums, FSM engine

---

### Task 1: Remove `deep_survey` from FSM state enum

**Files:**
- Modify: `shared/models/fsm.py:15`

- [ ] **Step 1: Delete `deep_survey` enum member**

```python
# shared/models/fsm.py — delete line 15:
#     deep_survey = "deep_survey"
# Result: FSMState enum becomes:
class FSMState(StrEnum):
    """所有 FSM 状态"""
    # Topic 级
    elaborate = "elaborate"
    survey = "survey"
    ideation = "ideation"
    # Idea 级
    refine = "refine"
    theory_check = "theory_check"
    code_reference = "code_reference"
    code = "code"
    debug = "debug"
    experiment = "experiment"
    analyze = "analyze"
    conclude = "conclude"
    abandoned = "abandoned"
    completed = "completed"
```

- [ ] **Step 2: Verify import still works**

Run: `cd /Users/zhaodawei/Desktop/Serious/code/sundial_pro/self && python -c "from shared.models.fsm import FSMState; print(list(FSMState))"`

Expected: List without `deep_survey`

---

### Task 2: Remove `deep_survey` from FSM engine transitions, options, and dispatch

**Files:**
- Modify: `agents/fsm_engine.py:41,56,66,70,289,310,353`

- [ ] **Step 1: Remove `deep_survey` from `TOPIC_TRANSITIONS`**

```python
# agents/fsm_engine.py — delete line 41:
#     "deep_survey": "ideation",
# Result:
TOPIC_TRANSITIONS = {
    "elaborate": "survey",
    "survey": "ideation",
    "ideation": "completed",
}
```

- [ ] **Step 2: Remove `("analyze", "deep_survey")` from `USER_CONFIRM_TRANSITIONS`**

```python
# agents/fsm_engine.py — delete line 56:
#     ("analyze", "deep_survey"),
# Result:
USER_CONFIRM_TRANSITIONS = {
    ("analyze", "refine"),
    ("analyze", "abandoned"),
    ("theory_check", "abandoned"),
    ("theory_check", "refine"),
    ("debug", "refine"),
    ("survey", "ideation"),
}
```

- [ ] **Step 3: Remove `"d": "deep_survey"` from both option dicts**

```python
# agents/fsm_engine.py lines 65-72:
TOPIC_OPTIONS = {
    "e": "elaborate", "s": "survey",
    "i": "ideation", "q": "_quit",
}
IDEA_OPTIONS = {
    "e": "experiment", "r": "refine",
    "a": "abandoned", "c": "conclude", "q": "_quit",
}
```

- [ ] **Step 4: Remove `deep_survey` branch from `_execute_topic_state`**

```python
# agents/fsm_engine.py line 289 — change:
#     elif state in ("survey", "deep_survey"):
# to:
    def _execute_topic_state(self, state: str) -> str:
        if state == "elaborate":
            return self.orch.phase_elaborate()
        elif state == "survey":
            round_num = self.snapshot.topic_retry_counts.get("survey", 0) + 1
            return self.orch.phase_survey(round_num=round_num)
        elif state == "ideation":
            return self.orch.phase_ideation()
        else:
            logger.warning(f"未知的 topic 状态: {state}")
            return ""
```

- [ ] **Step 5: Remove `deep_survey` from `_execute_idea_state` dispatch**

```python
# agents/fsm_engine.py line 310 — delete:
#     "deep_survey": lambda: self.orch.phase_survey(),
# Result dispatch dict:
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
            "conclude": lambda: self.orch.phase_conclude(idea_id),
        }
```

- [ ] **Step 6: Reroute `need_literature` verdict to `refine`**

```python
# agents/fsm_engine.py line 353 — change:
#     AnalysisVerdict.need_literature: "deep_survey",
# to:
            AnalysisVerdict.need_literature: "refine",
```

- [ ] **Step 7: Verify FSM engine imports cleanly**

Run: `cd /Users/zhaodawei/Desktop/Serious/code/sundial_pro/self && python -c "from agents.fsm_engine import ResearchFSM; print('OK')"`

Expected: `OK`

---

### Task 3: Remove `phase_deep_survey()` from orchestrator

**Files:**
- Modify: `agents/orchestrator.py:1182-1192`

- [ ] **Step 1: Delete `phase_deep_survey` method**

```python
# agents/orchestrator.py — delete lines 1182-1192:
#     def phase_deep_survey(self, queries: list = None, round_num: int = 2) -> str:
#         """深度文献调研：针对特定方向补充文献
#         ...
#         """
#         self._log_phase_start("deep_survey")
#         result = self.phase_survey(round_num=round_num)
#         self._log_phase_end("deep_survey", summary=result[:200])
#         return result
```

- [ ] **Step 2: Verify orchestrator imports cleanly**

Run: `cd /Users/zhaodawei/Desktop/Serious/code/sundial_pro/self && python -c "from agents.orchestrator import Orchestrator; print('OK')"`

Expected: `OK`

---

### Task 4: Remove `need_literature` from AnalysisVerdict enum

**Files:**
- Modify: `shared/models/fsm.py:37`
- Modify: `agents/evaluators/analysis_evaluator.py:11,35`
- Modify: `agents/fsm_engine.py:353` (already changed in Task 2 Step 6 — remove the line entirely)

Since `need_literature` no longer routes to a distinct state (it now routes to `refine`, same as `enrich`), we have two options:

**Option A — Keep the verdict** as a semantic signal (evaluator can still say "the problem is literature"), but it routes to `refine`. This is what Task 2 Step 6 already does.

**Option B — Delete the verdict entirely** and fold it into `enrich` or `restructure`.

**Recommended: Option A** — keep `need_literature` as a verdict value. It's useful diagnostic info in the evaluator output even though the routing is now the same as `enrich`. No further changes needed beyond Task 2 Step 6.

- [ ] **Step 1: Update evaluator prompt to clarify new behavior**

```python
# agents/evaluators/analysis_evaluator.py line 35 — change:
#     - **need_literature**: 分析中发现理论基础不足，需要补充文献调研
# to:
#     - **need_literature**: 分析中发现理论基础不足，需要补充文献（将回退到 refine，由 refine agent 搜索补充论文）
```

- [ ] **Step 2: Verify evaluator imports cleanly**

Run: `cd /Users/zhaodawei/Desktop/Serious/code/sundial_pro/self && python -c "from agents.evaluators.analysis_evaluator import AnalysisEvaluator; print('OK')"`

Expected: `OK`

---

### Task 5: Commit

- [ ] **Step 1: Stage and commit**

```bash
cd /Users/zhaodawei/Desktop/Serious/code/sundial_pro/self
git add shared/models/fsm.py agents/fsm_engine.py agents/orchestrator.py agents/evaluators/analysis_evaluator.py
git commit -m "refactor: 移除 deep_survey 状态，need_literature 改路由到 refine"
```
