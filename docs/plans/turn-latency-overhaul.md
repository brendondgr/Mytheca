# Turn Latency Overhaul — fewer calls, bounded waits, and a prompt cache that grows

**Status:** phases 1–5 complete; phase 6 (measurement) running
**Created:** 2026-08-20
**Owner:** brendondgr
**Baseline:** [EXP-2026-08-005](../research/experiments/EXP-2026-08-005-conversation-scaling/RESULTS.md)

## 1. Introduction

[EXP-2026-08-005](../research/experiments/EXP-2026-08-005-conversation-scaling/RESULTS.md)
measured where a turn's time actually goes and produced a ranked list of fixes. This plan
implements the five the owner selected, plus the prompt-cache work that the measurement
only partly explored.

The measured cost of a turn breaks down as: beat planner **41 %** (3–6 sequential calls),
first character dialogue 15 %, reflection 13 %, continuity guard 11 %, intent 7 %. The
wait before any prose appears is ~10 s, and the "takes five minutes" complaint is a
*decision* call stalling inside a timeout window sized for prose generation.

Six workstreams, in dependency order:

| # | Change | What it buys |
| --- | --- | --- |
| 1 | Per-operation timeouts | A stalled decision becomes a 25 s hiccup, not a 5 min hang |
| 2 | Retire the continuity guard | −11 % of turn time; **every** beat streams live |
| 3 | Plan several beats per call | Attacks the single largest cost (41 %) |
| 4 | Cache-shaped prompt | Up to ~40 % of the wait once a scene is long |
| 5 | Live thinking on by default | First visible signal at ~0.4 s instead of ~10 s |
| 6 | Re-measure against the baseline | The claim is only real if it reproduces |

**Reflection is deliberately untouched.** It costs ~13 % and there is an existing
`TURN_ASYNC_FINALIZE` switch to move it off the request path, but the owner's decision was
to keep it as-is. Recorded here so a later reader does not mistake the omission for an
oversight.

### Why the cache is stuck at 800 tokens

A prefix cache matches from the first token and stops at the first byte that differs.
`character_turn_agent._build_user_prompt` orders the prompt:

1. output contract + world primer + stat guidance — *never changes* (**this is the 800**)
2. speaker identity, register-selected voice samples, **current stat values**, recent lines
   — *changes every beat*
3. setting, roster, retrieved lore, tagged files, relationship note, scene direction
4. **the transcript** — the only block that is purely append-only
5. act-now instructions

The match dies at the top of (2) on turn 2, so the transcript below it — the largest block
in a long scene, and one that would be reusable almost in its entirety — is re-read from
scratch on every call. This is not a cap; it is where the first volatile token sits.

Two facts sharpen the target beyond what EXP-2026-08-005 reported:

- **The measured 40 % saving is a floor.** That probe compared a 100-turn prompt against a
  50-turn one, so at most ~half could match by construction. Real play appends one or two
  beats per turn, so a correctly ordered prompt should match a far larger share of the
  previous call — and it applies to every beat, not once per turn.
- **A sliding window would silently undo the reorder.** `buffer.recent_turns(limit=N)` and
  `_transcript` both take the *last* N beats. Past `context_beats` the window drops its
  oldest beat every turn, changing the transcript's first token and invalidating everything
  after it. Reordering alone stops paying at exactly the scene length it is meant to help.

## 2. Gaps & Unanswered Questions

**Assumptions taken (simple gaps):**

1. **Lookahead depth = 3 beats, configurable.** Planning the whole turn in one call maximises
   the saving but makes the later beats' `register` a guess about a moment that has not
   happened. Three is the compromise: it removes most planner calls while re-reading the
   room at least once mid-turn. Exposed as a setting so it can be tuned against measurement.
2. **Decision timeout = 25 s.** Measured means are 3.6 s (intent) and 4.9 s (planner); 25 s
   is ~5× the slowest observed and still an order of magnitude below the 300 s prose window.
3. **Transcript anchor block = 20 beats.** With `context_beats = 100` the window start moves
   once every 20 turns instead of every turn, so 19 of 20 turns keep a warm prefix.
4. **The continuity guard is removed, not disabled.** The owner's instruction was "forget
   about the continuity check". Dead code behind a flag is the thing `CLAUDE.md` already
   calls out (`director_agent.who_is_up`), so it goes rather than lingering.
5. **Speaker identity moves to the prompt tail, not into a shared prefix.** Placing every
   cast member's authored voice in one shared block would cache more, but the design's
   per-character isolation ("no shared multi-POV prompt, so voices stay distinct") exists to
   stop voice bleed. Keeping only the *speaker's* identity, and putting it after the
   transcript, captures nearly all of the cache win — the transcript dwarfs the identity
   block in a long scene — without that risk.

**Flagged, not blocking:** Steps 3.x and 4.2 change what the model attends to and in what
order. They are latency changes with writing-quality consequences, so Phase 6 reads output
side by side, not only stopwatches it.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Bound the decision calls

#### Step 1.1 — A per-call timeout override on the transport
- **Locations:** `web/backend/app/services/llm.py` — `_gen_timeout()` takes an optional
  seconds override; `chat_complete`, `chat_complete_usage`, `chat_complete_stream` accept
  `timeout_s: float | None`. `web/backend/app/core/config.py` — new
  `llm_decision_timeout_seconds: int = 25`, documented in `.env.example`.
- **Rationale:** every call currently shares one 300 s window sized for prose. The transport
  is the only place that knows about `httpx.Timeout`, so the override belongs there rather
  than being re-implemented per agent.

#### Step 1.2 — Apply it to the structural agents
- **Locations:** `web/backend/app/agents/intent_agent.py`, `planner_agent.py`,
  `direction_agent.py`, `triage_agent.py`.
- **Rationale:** these emit no prose and return JSON. A stalled one should surface as a fast
  best-effort fallback (each already has one) rather than a five-minute silence.

> *Action: `uv run pytest utils/tests/backend/services/test_llm.py utils/tests/backend/services/test_llm_streaming.py utils/tests/backend/agents/`. Commit: `[Turn Latency] (1/6) Complete: Structural decision calls get a 25s ceiling instead of the 300s prose window.`*

### Phase 2 — Retire the continuity guard

#### Step 2.1 — Remove the guard and its call site
- **Locations:** delete `web/backend/app/services/consistency.py`; in
  `web/backend/app/services/turn_engine.py` drop `guard_conn`, the `guarded` split, the
  `consistency` trace step and the correction re-generation; drop the now-unused
  `correction` parameter from `character_turn_agent.generate_line*` / `stream_line` and its
  TAIL branch. Remove `utils/tests/backend/services/test_consistency*.py` and guard-specific
  assertions elsewhere.
- **Rationale:** it costs ~10 s whenever a second character speaks and is the *only* reason
  later beats cannot stream. Removing it makes every beat live, which is a UX win on top of
  the latency one.

#### Step 2.2 — Follow the contract through the docs and the Inspector
- **Locations:** `docs/api-contract.md` (trace-step list), `docs/data-flow.md`,
  `docs/architecture.md`, `docs/component-map.md`; `web/frontend/features/story-player/turn-stream.ts`
  (`PHASE_BY_STEP`), `components/feature/TurnStatusStrip.tsx`, `TurnInspectorPanel.tsx`.
- **Rationale:** a trace step that no longer exists must not be left in the frontend's phase
  map or the published contract.

> *Action: `uv run pytest`; `cd web/frontend && npm test && npm run typecheck && npm run lint`. Commit: `[Turn Latency] (2/6) Complete: The continuity guard is gone and every beat now streams live.`*

### Phase 3 — Plan several beats per call

#### Step 3.1 — `planner_agent.plan_beats()`
- **Locations:** `web/backend/app/agents/planner_agent.py` — new `plan_beats()` returning an
  ordered `list[BeatDecision]` (each carrying its own `register`/`stakes`), bounded by the
  lookahead and the remaining scene budget; `next_beat()` becomes the single-beat wrapper so
  existing callers and tests keep working. Prompt text in `prompt_registry` gains the
  multi-beat contract.
- **Rationale:** the planner is 41 % of turn time purely because it runs once per beat. One
  call that returns three beats replaces three calls that return one.

#### Step 3.2 — Consume the plan in the turn loop, re-planning on divergence
- **Locations:** `web/backend/app/services/turn_engine.py` (the beat loop);
  `web/backend/app/core/config.py` — `turn_planner_lookahead: int = 3`, `.env.example`.
- **Rationale:** a plan is a prediction, so the loop must discard planned beats whose actor
  is no longer present, whose requirement was already delivered, or that would exceed the
  cap, and re-plan when the plan runs out without an `end`. This keeps the ReAct loop's
  correctness while paying for it once per few beats instead of once per beat.

#### Step 3.3 — Keep the status strip honest
- **Locations:** `web/frontend/features/story-player/turn-stream.ts`,
  `components/feature/TurnStatusStrip.tsx`.
- **Rationale:** "Deciding who speaks next" now happens once for several beats. The strip
  should say what is true rather than implying a decision before every line.

> *Action: `uv run pytest utils/tests/backend/agents/ utils/tests/backend/services/`; frontend tests for the touched components. Commit: `[Turn Latency] (3/6) Complete: The planner decides several beats in one call instead of one per beat.`*

### Phase 4 — Shape the prompt so the cache grows with the scene

#### Step 4.1 — Block-anchored transcript window
- **Locations:** `web/backend/app/services/assembler.py` (`assemble_context`, `_transcript`),
  `web/backend/app/memory/buffer.py` (`recent_turns` gains an anchored variant),
  `web/backend/app/core/config.py` — `turn_transcript_anchor_block: int = 20`.
- **Rationale:** this must land **before** the reorder. A window that slides one beat per
  turn changes the transcript's first token every turn and would waste the entire reorder
  past `context_beats`. Advancing the start in blocks means one cold turn in twenty.

#### Step 4.2 — Reorder the character prompt to be monotonic in volatility
- **Locations:** `web/backend/app/agents/character_turn_agent.py` (`_build_user_prompt`).
- **Rationale:** the new order is **stable** (setting, roster — identical for every speaker)
  → **append-only** (transcript) → **volatile tail** (speaker identity, voice samples, live
  stats, recent lines, relationship note, retrieved lore, tagged notes, scene direction,
  register directive, disposition, act-now, requirements). Everything that changes per beat
  ends up after everything that does not, so the reusable prefix ends where the transcript
  ends and grows with the scene. Identity moving from primacy to recency is a deliberate
  trade — recency is the stronger position on this model class — and is what Phase 6 checks
  for quality.

#### Step 4.3 — Make prefix reuse observable without depending on the endpoint
- **Locations:** `web/backend/app/services/llm.py` (a small per-session last-prompt cache +
  shared-prefix length), `web/backend/app/services/turn_engine.py` (`context` trace gains
  `reusablePrefixChars`), `web/frontend/lib/events.ts`, `docs/api-contract.md`.
- **Rationale:** `skynet` reports `prompt_tokens_details: null` when the hit is zero, so the
  server's counter cannot prove a regression. The shared prefix between consecutive calls is
  computed locally, always available, and is the thing actually under our control.

#### Step 4.4 — Same discipline for the other transcript-carrying prompts
- **Locations:** `web/backend/app/agents/reflection_agent.py`.
- **Rationale:** every present character reflects on the *same* transcript at the end of a
  turn, so leading with it makes one shared prefix that all of those calls hit.
- **Narrator and director deliberately excluded.** Both condition on a six-beat window that
  slides every beat, so there is no stable prefix to protect; reordering them would be
  prompt churn with a quality risk and no measurable gain. Recorded in `docs/checklist.md`
  rather than done silently.

> *Action: `uv run pytest utils/tests/backend/services/ utils/tests/backend/agents/`; frontend tests + typecheck. Commit: `[Turn Latency] (4/6) Complete: The prompt is ordered stable → transcript → volatile, behind an anchored window.`*

### Phase 5 — Live thinking on by default

#### Step 5.1 — Flip the default and say what it costs
- **Locations:** `web/backend/app/schemas/settings.py` (`reasoning_visibility` default
  `"summary"` → `"full"`), `web/frontend/features/options/tabs/LanguageModelsTab.tsx` (copy),
  `docs/deployment.md`, `docs/design-system.md` if the disclosure state is documented there.
- **Rationale:** the first reasoning token arrives ~0.4 s in against ~10 s for prose, so this
  is the largest perceived-latency win available for one line of change. The trade-off —
  reading a character's deliberation can spoil the line — belongs in the Options copy, not
  in a commit message.

> *Action: `uv run pytest utils/tests/backend/api/`; frontend tests + accessibility/responsive pass on the Options tab and the transcript disclosure. Commit: `[Turn Latency] (5/6) Complete: Live thinking is on by default.`*

### Phase 6 — Measure it against the baseline

#### Step 6.1 — Re-run EXP-2026-08-005's protocol on the new code
- **Locations:** `docs/research/experiments/EXP-2026-08-006-turn-latency-overhaul/`;
  `utils/scripts/research/run_conversation_scaling.py` reused unchanged where possible.
- **Rationale:** same endpoint (`skynet`), same configuration (`maxTurns = 5`,
  `suggestionsCount = 0`, `contextBeats = 100`, 10 turns) — otherwise the comparison is not a
  comparison. Report the same per-turn and step-share tables so the two experiments read
  side by side, and record the writing-quality read of the reordered prompt alongside the
  timings.

#### Step 6.2 — Reconcile the record
- **Locations:** `docs/research/CLAIMS.md`, `docs/checklist.md`, `docs/plans/conversation-scaling-latency.md`
  (its recommendation list is now acted on), this file's status.
- **Rationale:** the research contract requires findings to be recorded, and the earlier
  plan's open recommendation should point at what was done about it.

> *Action: full gate — `uv run pytest`; `npm test`, `npm run typecheck`, `npm run lint`; `uv run python utils/scripts/check_contrast.py`; `node utils/scripts/check_frontend_css.mjs`; `make validate-research`. Commit: `[Turn Latency] (6/6) Complete: Measured against EXP-2026-08-005 and recorded.`*

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Per-call timeout | `timeout_s` override on all three transports | `web/backend/app/services/llm.py` |
| Decision ceiling | `llm_decision_timeout_seconds` (25 s) applied to structural agents | `web/backend/app/core/config.py`, `agents/{intent,planner,direction,triage}_agent.py` |
| Guard removal | `consistency.py` deleted; every beat streams live | `web/backend/app/services/turn_engine.py` |
| Multi-beat planning | `plan_beats()` + lookahead-bounded consumption | `web/backend/app/agents/planner_agent.py`, `services/turn_engine.py` |
| Anchored window | Transcript start advances in blocks, not per beat | `web/backend/app/services/assembler.py`, `memory/buffer.py` |
| Cache-shaped prompt | stable → transcript → volatile ordering | `web/backend/app/agents/character_turn_agent.py` |
| Prefix observability | `reusablePrefixChars` on the `context` trace | `web/backend/app/services/llm.py`, `services/turn_engine.py`, `web/frontend/lib/events.ts` |
| Live thinking default | `reasoning_visibility` defaults to `full` | `web/backend/app/schemas/settings.py`, `features/options/tabs/LanguageModelsTab.tsx` |
| Backend tests | Timeouts, planner plans, anchoring, prompt order, prefix reuse | `utils/tests/backend/{services,agents}/` |
| Frontend tests | Phase map without `consistency`, status-strip copy, Options default | co-located `*.test.tsx` |
| Experiment | Before/after against the same protocol and endpoint | `docs/research/experiments/EXP-2026-08-006-turn-latency-overhaul/` |
