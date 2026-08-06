# ISSUES — EXP-2026-08-001

## 2026-08-06 — No LLM endpoint reachable; every agent fell back or raised

**Impact:** Fatal to the experiment. 12 of 18 turns raised
`APIError: Configure a model endpoint in Options first.`; the other 6 completed only
because `planner_agent.next_beat` catches the error and emits a heuristic narrator
beat. **0 LLM calls, 0 input tokens, 0 output tokens.** `n` for every metric is
effectively 0, not the 18 the run appears to report.

**Cause:** No model endpoint is configured for this checkout. `LOCAL_LLM_BASE_URL`
defaults to `http://localhost:11434` (Ollama's port) and nothing is listening; no
`ollama`, `vllm` or `llama-server` binary is on PATH. Confirmed by calling
`resolve_llm` directly against a seeded database.

**Resolution:** None available in this session. Recorded as `status: failed` with
empty `metrics.values` per the contract §3.4. **The folder is kept** — a deleted
failed experiment is a dead end that gets walked into twice, and the harness it
carries is the expensive part.

**Paper implication:** None directly — no number leaves this folder. Indirectly: any
future run of this protocol must verify LLM reachability before starting, and the
paper must state the model and version used, which this run cannot.

---

## 2026-08-06 — Survivorship-biased aggregate written on the first run

**Impact:** Would have published `beats = 1.0 ± 0.0 (n=6)` as a two-arm comparison
result. It is one arm's non-LLM fallback measured six times. The director arm
contributed **zero** rows, so the "comparison" had one side. Caught before the
experiment was committed; no number was ever reported outside this folder.

**Cause:** `run_scene.py` computed its aggregate over `[r for r in rows if not
r["error"]]` regardless of how many rows failed. Excluding failures is correct when a
seed crashes at random; it is wrong when the failure mode is systematic and
arm-correlated, because the survivors are then a biased subsample rather than a
smaller one.

**Resolution:** `run_scene.py` now publishes no aggregate at all when any turn fails —
per-run rows and totals only — and records a note naming the ratio. The zero standard
deviation was the tell: six identical values from the same fallback path, which reads
as consistency and is actually degeneracy.

**Paper implication:** State the reduced `n` per cell wherever a run is excluded, and
never report a mean over the surviving rows of a partially-failed run without saying
what failed and why. This is the concrete instance behind `RESULTS.md` §5.

---

## 2026-08-06 — Degradation mismatch between the two arms (incidental finding)

**Impact:** None on this experiment's conclusion, but it is why the two arms produced
different row counts under an identical fault.

**Cause:** `planner_agent.next_beat` catches `APIError` from `resolve_llm` and returns
`_fallback_beat`. `director_agent.who_is_up` does not, and propagates. Both carry
docstrings promising "best-effort; never raises".

**Resolution:** Not fixed here — this experiment does not modify
`web/backend/app/`, and changing the baseline arm's behaviour mid-experiment would
invalidate the comparison it exists to support. Filed in `../../OPEN_QUESTIONS.md`.

**Paper implication:** None. It is an engine defect, not a result.
