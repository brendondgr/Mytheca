# Binding Upfront Plan + Two Execution Arms

## 1. Introduction

The turn loop plans **per beat**. `planner_agent.plan_beats` is called, one beat runs, and
the planner is called again — a ReAct loop. Three defects follow from that single fact, and
this plan removes the cause rather than treating each symptom.

**The plan is not binding.** `turn_engine.py:362` reads `elif not planned:` — when a plan's
queue empties, the engine plans *again*. A plan the player approved is therefore a head start
on an open-ended loop, not a contract. Measured in `EXP-2026-08-016`: turns of 18, 22 and 24
beats, the last being the runaway backstop rather than a decision.

**Thinking is allocated backwards.** The planning stage runs at `ReasoningEffort.QUICK`
(128 tokens); the prose stage runs at `HIGH` (1024). Measured against the live endpoint, the
prose call spends **91 % of its output on hidden reasoning** — 2646 reasoning characters for
247 characters of prose. Execution deliberates eight times harder than planning, while
planning is what has to stay consistent from beat to beat.

**Per-beat planning destroys the prefix cache.** `_build_user_prompt` is already ordered
STABLE (setting + full roster) → APPEND-ONLY (transcript) → VOLATILE (this speaker), which is
exactly right. But the server holds one KV cache, so interleaving `[planner][Lily][planner]
[Zoe]` overwrites the character prefix on every planner call and each beat re-processes the
whole stable region. One upfront plan makes the sequence `[planner][Lily][Zoe][Aldous]`, and
the cache reuse the ordering was designed for finally happens.

The approach: **plan once, with the full thinking budget; treat the resulting beat list as a
contract; execute it without re-planning.** Then measure the two execution strategies over
that same fixed plan — one continuous generation versus a stop-at-each-beat pass.

## 2. Gaps & Unanswered Questions

- **Prose reasoning: `NONE` or `QUICK`?** Assumption: **`NONE`**. `HIGH` was set because a run
  with reasoning off *and* no `<thinking>` block leaked a scratchpad into the passage and
  degenerated at 29,660 characters. That was before `prose_guards.looks_like_scratchpad` and
  the degeneration guard existed. Phase 3 measures it; if scratchpad text reaches the
  transcript, fall back to `QUICK` (128) rather than to `HIGH`.
- **Does a binding plan need a ceiling at all?** Assumption: keep
  `max(turn_max_beats, 2*cast + 6)` as a **crash guard on plan *creation*** only — the planner
  may not emit a plan longer than it — and never as a runtime stop. A 15-beat plan runs 15
  beats.
- **Who approves the plan in a test?** Assumption: the harness auto-approves, standing in for
  the player. The property under test is that the executed beat list equals the approved one,
  which does not depend on a human pressing the button.
- **Complex gap — none blocking.** Whether `plan` mode or `auto` should become the default is
  a product decision and is explicitly **out of scope**; this plan changes what a plan *means*,
  not which mode ships on.

## 3. Step-by-Step Instructions

### Phase 1 — A plan is a contract

- **Locations:** `web/backend/app/services/turn_plan.py` (`preflight` returns whether the
  turn is running a **bound** plan), `web/backend/app/services/turn_engine.py` (the
  `elif not planned:` branch at ~362; the `while … beats < max_beats` loop at 311).
- **Rationale:** This is the single branch that makes every other symptom possible. A bound
  turn whose queue empties must **end**, not re-plan. Nothing else in this plan is safe to
  build on top of a loop that can still extend itself.
- **Tests:** `utils/tests/backend/services/test_bound_plan.py` — a 3-beat plan runs exactly 3;
  an 8-beat plan runs exactly 8; **exactly one** planner call occurs per turn; a beat whose
  actor left mid-turn is dropped without triggering a re-plan.
- *Action: `uv run pytest utils/tests/backend/services utils/tests/backend/api`. Commit:
  `Binding Plan (1/7) Complete: an approved or upfront plan is executed exactly and never re-planned.`*

### Phase 2 — Plan once, thinking hard

- **Locations:** `web/backend/app/agents/planner_agent.py` (`PLANNER_EFFORT`, a whole-turn
  `plan_turn` wrapper over `plan_beats`), `web/backend/app/core/config.py`
  (`turn_planner_lookahead` semantics: `0` = plan the whole turn).
- **Rationale:** Consistency across beats is the planner's job, so the thinking budget belongs
  here. Raising planner effort **only** pays off once it is called once per turn — raising it
  while it still runs per beat would cost more, not less, so Phases 1 and 2 must land together.
- **Tests:** `utils/tests/backend/agents/test_planner_whole_turn.py` — one call yields the full
  beat list terminated by `end`; the plan never exceeds the creation ceiling; `_pressure()` is
  not consulted on a bound turn.
- *Action: `uv run pytest utils/tests/backend/agents utils/tests/backend/services`. Commit:
  `Binding Plan (2/7) Complete: the whole turn is planned in one call at full thinking budget.`*

### Phase 3 — Execution executes

- **Locations:** `web/backend/app/agents/character_turn_agent.py` (`TURN_EFFORT`; carry the
  beat's `reason` into the VOLATILE tail of `_build_user_prompt`),
  `web/backend/app/services/beat_runner.py` (pass `reason` through).
- **Rationale:** The writer already receives `register` and `stakes` but **not** the plan's
  `reason` — the one field stating what the beat is *for*. Giving it the intent is what makes
  dropping its private deliberation safe: it executes a decision instead of re-deriving one.
- **Tests:** `utils/tests/backend/agents/test_prose_executes_the_plan.py` — `reason` reaches the
  prompt; no hidden-reasoning budget is requested; `looks_like_scratchpad` still gates output.
  Then `uv run python -m utils.scripts.scene_smoke --turns 1` for real prose.
- *Action: `uv run pytest utils/tests/backend/agents`. Commit:
  `Binding Plan (3/7) Complete: prose executes the planned beat instead of re-deliberating it.`*

### Phase 4 — Stop tokens and constrained decoding

- **Locations:** `web/backend/app/services/llm.py` (`stop` + `response_format` support — neither
  exists today), `web/backend/app/services/llm_backend.py` (engine capability),
  `web/backend/app/agents/planner_agent.py` (JSON-schema-constrained reply).
- **Rationale:** The planner's reply is parsed free-form today, so a malformed answer degrades
  silently. Constrained decoding was **verified working** on this endpoint: a schema permitting
  only `{"action":"end"}` returned exactly that when the model was asked to continue.
  **Recorded hazard:** a `stop` sequence also matches inside the reasoning channel — with
  `stop: ["<END_SCENARIO>"]` the model died mid-thought and returned empty content. Stop
  sequences are therefore only safe where reasoning is off, and `<END_SCENARIO>`-style tags are
  parsed server-side (as `<speaker:N>` already is) rather than passed as `stop`.
- **Tests:** `utils/tests/backend/services/test_llm_stop_and_schema.py` — both params reach the
  body; schema only sent to engines that support it; a reasoning-on call never receives `stop`.
- *Action: `uv run pytest utils/tests/backend/services`. Commit:
  `Binding Plan (4/7) Complete: stop sequences and constrained decoding, with the reasoning-channel hazard guarded.`*

### Phase 5 — Make the cache visible

- **Locations:** `web/backend/app/services/llm.py` (capture
  `usage.prompt_tokens_details.cached_tokens`), `web/backend/app/services/turn_emit.py`
  (`Tracer` carries it), `web/backend/app/schemas/play.py` if the trace frame needs the field.
- **Rationale:** The KV claim in §1 must be measured, not asserted. The endpoint already
  reports cached tokens; nothing reads them. Without this, Phase 6 cannot tell a real cache
  win from a story.
- **Tests:** `utils/tests/backend/services/test_cached_tokens_trace.py` — a payload reporting
  cached tokens surfaces them; a payload omitting the field does not crash the turn.
- *Action: `uv run pytest utils/tests/backend/services`. Commit:
  `Binding Plan (5/7) Complete: prefix-cache hits are captured from usage and traced.`*

### Phase 6 — EXP-2026-08-017, two arms over one plan

- **Locations:** `docs/research/experiments/EXP-2026-08-017-bound-plan-execution/`
  (`PROTOCOL.md` written **before** the run), `utils/scripts/research/run_bound_plan.py`.
- **Rationale:** The two strategies must differ **only** in execution, so both arms consume the
  *same* bound plan. `n = 2` player turns per arm, interleaved — the owner capped run length,
  and `EXP-2026-08-016` showed a 3-hour run answers a bounding question no better than a short
  one.
- **Metrics:** `plan_adherence` (beats run == beats planned — the primary, and a hard pass/fail),
  `planner_calls_per_turn` (must be 1), `cached_token_rate`, `seconds_per_beat`,
  `reasoning_share`, plus `cross_speaker_rate` / `misattribution_rate` / `voice_distinctness`
  carried from EXP-016 so prose quality cannot regress unnoticed.
- **Failure handling:** a partly-failed run is `status: failed` with per-turn rows and **no
  aggregate** — survivors are not a random subsample (`EXP-2026-08-001`).
- *Action: run it, write `RESULTS.md` + generated figures, `make validate-research && make research-index`. Commit:
  `Binding Plan (6/7) Complete: EXP-2026-08-017 measures both execution arms over one bound plan.`*

### Phase 7 — Docs, checklist, merge

- **Locations:** `CLAUDE.md` (the "facts that override stale assumptions" list — plan binding,
  reasoning allocation), `docs/data-flow.md` (turn path), `docs/api-contract.md`,
  `docs/checklist.md` (close the planner-`end` item; carry anything unmeasured),
  `docs/plans/binding-plan-and-execution-arms.md` (status table).
- **Rationale:** Project rules require docs to change in the **same** change as behaviour.
  `CLAUDE.md` currently tells a reader the planner decides when a turn ends; after Phase 1 that
  is false and would mislead the next session.
- *Action: full gate — `uv run pytest`, `cd web/frontend && npm test && npm run typecheck && npm run lint`. Commit:
  `Binding Plan (7/7) Complete: docs and checklist match the bound-plan turn loop.` Then merge to `main`.*

## 4. Deliverables

| Deliverable | Description | Location |
| --- | --- | --- |
| Bound-plan execution | A plan's beat list is executed exactly, never extended | `web/backend/app/services/turn_engine.py`, `services/turn_plan.py` |
| Whole-turn planner | One call, full thinking budget, whole turn | `web/backend/app/agents/planner_agent.py` |
| Intent-carrying prose | `reason` reaches the writer; no hidden deliberation | `web/backend/app/agents/character_turn_agent.py`, `services/beat_runner.py` |
| Stop + schema support | `stop` and `response_format` on the LLM layer | `web/backend/app/services/llm.py`, `services/llm_backend.py` |
| Cache observability | `cached_tokens` captured and traced | `web/backend/app/services/llm.py`, `services/turn_emit.py` |
| Experiment | Two arms over one bound plan, pre-registered | `docs/research/experiments/EXP-2026-08-017-bound-plan-execution/` |
| Runner | Harness for the experiment | `utils/scripts/research/run_bound_plan.py` |
| Backend tests | Binding, planner, prose, LLM params, cache trace | `utils/tests/backend/{services,agents}/` |

## 5. Status

| Phase | State |
| --- | --- |
| 1 — A plan is a contract | **done** |
| 2 — Plan once, thinking hard | **done** |
| 3 — Execution executes | **done** |
| 4 — Stop tokens + constrained decoding | not started |
| 5 — Make the cache visible | not started |
| 6 — EXP-2026-08-017 | not started |
| 7 — Docs, checklist, merge | not started |
