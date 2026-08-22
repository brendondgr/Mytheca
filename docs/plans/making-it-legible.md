# Making It Legible — the app explains itself, and stops counting beats

> **SHIPPED — 12/12 phases, 2026-08-22.** Commit series `634559c … HEAD` on branch
> `play-experience`. What follows this block is the plan as written; the record below is
> what actually happened and where it differs.

## 0. Completion record

### What shipped

The scene's memory stopped being a number the player guesses at. `services/context_budget`
resolves the model's real context window once and fits a **block-quantised** transcript depth
to it, with hysteresis so the window only moves in steps the prompt-cache anchoring already
tolerates; the "Number of beats" slider is gone from the config popover and its whole prop
chain. What the window reached is now *reported* three ways — the Inspector's `window` step,
"What the scene remembers" in the config menu, and a visible `MemoryEdge` line in the
transcript where verbatim recall ends. `SceneMemoryPanel` gives the player the same read the
Inspector holds. Every scene control states its effect and, where one exists, its cost.

Around that: a real model-health endpoint behind the header's status light (four states, never
colour alone), keyboard fluency (`/`, `↑`, `Escape`, `?`) with a shortcut sheet, three
dismissible persisted coach marks, client-side transcript search, a recap endpoint that reuses
the compaction agent rather than inventing a second one, and editable scene-image prompts that
re-paint as a new beat.

### What the evidence changed

**Compaction is built, was measured, and stays off.** Phase 4 delivered
`services/history_compaction` + `agents/recap_agent` behind `TURN_CONTEXT_COMPACTION`, and
Phase 12 ran the pre-registered two-arm experiment that was supposed to justify turning it on.
It did the opposite:
[`EXP-2026-08-011`](../research/experiments/EXP-2026-08-011-context-compaction/) recorded the
compacted arm **losing the planted fact the control kept** (3 of 9 content tokens against 6) —
the summary had reduced *"owes the harbourmaster four hundred crowns, brass key sewn into his
collar"* to `* Rensal: owes 400 crowns.` — while rewriting the summary **16 times** against a
predicted 4 and halving the reusable prompt prefix. Claim **C-013 stays `unsupported`**, the
flag stays `false`, and that is the plan's own stated outcome for this result rather than a
retreat from it.

The run also **found a defect in the feature it was measuring**: `maybe_compact` gates on beats
dropped *in total* rather than *since the last summary*, so the gate never closes after the
first block. It is deliberately **not** fixed inside the experiment's change — the recorded
numbers describe the code at `code.commit` — and is carried in `docs/checklist.md` and
`docs/research/OPEN_QUESTIONS.md`.

Two prior runs are on record rather than deleted: run 1 never fired the treatment at all
(`recap_calls: 0` — a 10-turn scene cannot drop a 20-beat block), and the harness now refuses
`--turns < 24` so that dead end cannot be walked into silently twice.

### Where it differs from the plan

- **H1 as pre-registered could not have come out the other way.** The control is a fixed
  100-beat window, so it never dropped the plant; the fair question the design actually answers
  is "does B match A while reading far less?". Recorded in the experiment's `ISSUES.md` §1
  rather than edited into `PROTOCOL.md`, which is the pre-registration.
- **H3 (prose quality) is `not measured`.** A blinded pairwise read was pre-registered and not
  performed, and a preference from a reader who already knows the arms is not evidence.
- The experiment ran on `gemma-4-26B-it`, not the configured `skynet`, which was down all day.

### Validation at the close of the plan

`uv run pytest` — **1552 passed**. `npm test` — **1182 passed**, 129 files.
`make validate-research` — OK, 11 experiments, 0 warnings.

---

**Status:** proposed
**Created:** 2026-08-21
**Owner:** brendondgr
**Answers:** the owner's *"I don't know if people understand what to do"*, and the direct
instruction *"the number of beats is stupid… it should just remember up to the point where
the LLM has the context available, once it starts to run out of context, a lot of the
context should be compacted in some fashion."*

---

## 1. Introduction

Mytheca currently asks the player to operate a machine whose parts are named after their
implementation. The scene-config popover offers *Max turns*, *Suggestions*, *Beat length*
and *Number of beats*; only the last of those tells the player what it costs, and it is the
one control the owner wants deleted outright. Meanwhile the app already computes a rich,
truthful account of every turn — which documents were tagged, whether retrieval fired, how
deep the transcript reached, exactly how many tokens went to the model — and files all of it
under a control labelled **Inspector** with a gear icon, i.e. a developer tool. The green dot
in the scene header says *"Narrator active"* and is a hardcoded `<span>`. There is no
onboarding of any kind (structural gap **G6**): nothing anywhere tells a new player what a
scene is, what "Speaking as" does, or that the cast rail is clickable.

This plan does two things. First, the **engineering** item: retire the per-scene
`context_beats` slider and replace it with a window that fits itself to the model's real
context budget, plus a rolling **compaction** of the history that falls out of that window —
designed so that the block anchoring which currently protects prompt-cache reuse
(`buffer.anchored_turns`, `TURN_TRANSCRIPT_ANCHOR_BLOCK = 20`) survives intact, and so a
scene still plays with no Redis, no Qdrant and no reachable model. Second, the **legibility**
work that hangs off it: controls relabelled by consequence and cost, a player-facing read of
what the scene actually knows, a visible line in the transcript marking where verbatim memory
ends, three anchored coach marks, keyboard fluency with a shortcut sheet, transcript search
and recap, and a status light driven by whether the configured model endpoint is actually
reachable. Everything lands inside the existing architecture: the assembler stays read-only,
the turn transport stays NDJSON-in-the-POST-response, the FE↔BE contract stays hand-mirrored
in `web/frontend/lib/{events,types}.ts`.

---

## 2. Gaps & Unanswered Questions

### Decisions taken by the owner — 2026-08-21 (supersede the gaps below)

These three were asked and answered before implementation began. Where the text further down
states a different default, **this block wins** and that text is superseded.

**D-1 — Stat values become session-scoped, with a per-stat `carry_over` flag.**
(Answers Control H-1 and Depth §2.2 together — they were the same decision asked from two sides.)
`StatDefinition` gains a `carry_over` boolean. Stat *values* move to a session scope: a new
`session_character_stats` row set keyed `(session_id, character_id, key)`. Resolution order when
the engine reads a stat is: the open session's value → else, if `carry_over` is true, the
character-global value → else the authored baseline. Consequences that the phases below must
absorb:
  * **Rewind** no longer needs `StatPatch.fromValue` as its un-apply mechanism. It deletes the
    session's stat rows and **replays the surviving `state_update` events** from the authored
    baseline — deterministic, needs no per-event provenance, and works for legacy rows written
    before this program. Keep `fromValue` only if it earns its place for the Inspector's display;
    it is no longer load-bearing.
  * **Branch** copies the source session's stat rows to the fork at the fork point, so the two
    play-throughs diverge instead of sharing.
  * **Two play-throughs of one scenario no longer disagree** — they are simply separate, which was
    the defect H-1 named.
  * `GET /characters/{id}/stats` keeps returning the character-global values (the authored/carried
    baseline). Play surfaces read the session-scoped values. Say which is which at every call site.
  * This is additive-but-not-trivial: it is a new table plus a change to every stat read and write
    (`services/stats.py`, `services/stat_render.py`, `beat_runner`'s stat application, the cast
    rail, the dossier, and `useScenePlay`'s baseline load). Give it **its own phase** rather than
    smuggling it into the rewind phase.

**D-2 — Context compaction ships OFF by default.**
`TURN_CONTEXT_COMPACTION` defaults to disabled. Long scenes keep today's behaviour (older history
falls out of the window) until the interleaved two-arm experiment reports. The flag flip is a
one-line change and is explicitly *not* to be made on the strength of a read-through. This
supersedes any "ship on" reading of the compaction phases.

**D-3 — The `sr-only` defect is fixed by redefining the utility once.**
`@utility sr-only { position: fixed }` — one change, covering all existing call sites and every
future one. The per-file sweep is **not** done. The change must be pinned by a regression test and
must pass the offline CSS gate (`node utils/scripts/check_frontend_css.mjs`).

---

### Simple gaps — assumption stated, work proceeds

**G-1. What "the model's context window" is when nothing reports one.**
`GET /api/options/llm/context-window` already resolves *detected* (llama.cpp `/props →
n_ctx`, vLLM/relay `/models → max_model_len`) then falls back to the stored
`LlmConfig.maxContextTokens` (default `16384`). **Assumption:** the engine uses the *same*
resolution, extracted into one shared function so the route and the turn loop can never
disagree, with a final hard floor of `8192` when both are absent. A relay that reports
nothing is the common case on this deployment (`skynet`), so the configured value is the
normal path, not the exception.

**G-2. How much of the window the transcript may claim.**
**Assumption:** the transcript never gets the whole window. The budget is
`window − (system + stable prefix + volatile tail + output allowance + margin)`, and is
additionally capped at `TURN_CONTEXT_MAX_FRACTION` (default `0.5`) of the window. The
non-transcript regions are strings the assembler already holds (`stable_prefix`,
`retrieved_lore`, `tagged_notes`, the speaker block) and are measured with the existing
char/4 heuristic (`app/rag/tokens.approx_tokens`, which the frontend's
`lib/contextBudget.CHARS_PER_TOKEN` already matches). The output allowance is
`character_turn_agent.prose_tokens_for(beat_length)` plus the reasoning budget from
`app/schemas/reasoning.THINKING_BUDGET`.

**G-3. Existing scenarios that carry a `context_beats` value.**
**Assumption:** the column stays, and stops being a player-facing control. A new nullable
`context_policy` column (`"auto"` | `"fixed"`; `NULL` reads as `"auto"`) decides whether
`context_beats` is honoured. Every existing row therefore switches to auto on the next turn —
which is the intended outcome, since the owner's position is that the number was never a
useful thing to choose. The value is *not* deleted, because three research harnesses
(`utils/scripts/research/run_conversation_scaling.py`, `run_beat_length.py`,
`run_prose_end_to_end.py`) pin `contextBeats = 100` to make their arms comparable; they set
`contextPolicy: "fixed"` alongside it and keep working unchanged. `context_policy` is nullable
and additive, so **no Alembic migration is required** — the bootstrap reconciler self-heals it.

**G-4. `MomentRequest.beats` defaults to the scenario's `contextBeats`.**
**Assumption:** the scene-image look-back stops depending on a control that no longer exists
and gets its own constant in `services/scene_moment.py` (the existing default/clamp pair),
defaulting to today's effective value. The image prompt should not silently grow because a
scene's transcript window grew.

**G-5. Which agent compacts, and how expensive it is.**
**Assumption:** a new `agents/recap_agent.py` at `ReasoningEffort.LOW` — the same tier
`reflection_agent` uses, for the same reason (structure-light, no prose to perform). It is
*incremental*: previous summary + the beats about to fall out → the new summary, so its input
is bounded by one anchor block (20 beats) regardless of scene length. It fires at most once
per anchor block, i.e. roughly one turn in twenty, and runs inline **before**
`assembler.assemble_context` so the turn it fires on can use the result. `TURN_ASYNC_FINALIZE`
is the existing seam if this ever needs to move off the request thread; it is not used here,
because the summary is needed by the very turn that triggers it.

**G-6. Where the summary lives.**
**Assumption:** three additive nullable columns on `PlaySession` — `summary_text`,
`summary_through_seq`, `summary_updated_at`. Nullable and additive, so again no migration.
Storing it on the session (rather than as an `Event`) keeps the `(session_id, seq)` monotonic
invariant untouched and makes invalidation a single-row write. It is recomputed only when
compaction fires, so a reload costs nothing and a quiet scene never re-summarises.

**G-7. Interaction with rewind / edit / branch.**
**Assumption:** `services/history_compaction.invalidate_after(db, session_id, seq)` is the
published seam. It clears `summary_text` whenever `summary_through_seq >= seq`, so the next
turn rebuilds the summary from the (authoritative) Postgres event log. A rewind that clears the
buffer but leaves a summary describing events that no longer happened is the exact failure this
seam exists to prevent.
**Ownership, corrected for the program order:** Control Over the Record lands *before* this plan,
so it cannot call a seam that does not yet exist. **This plan owns both the seam and the call
site.** Phase 4 adds `invalidate_after` *and* wires it into
`services/session_state.truncate_session` and `copy_history` (Control's Phase 4 primitives), so
rewind, edit and branch invalidate the summary in the same tested place they rebuild the buffer.
A forked session clears both.

**G-8. The status light (structural gap G8 in the review).**
**Assumption:** driven, not deleted. The most useful available signal is endpoint
reachability, since a player whose local LLM died currently discovers it only by sending a
turn and waiting for a timeout. `GET /api/options/llm/health` reuses the existing cached probe
machinery in `services/llm_backend.py` and reports `reachable | unreachable | unconfigured`,
plus whether the *configured model id* appears in the endpoint's `/models` listing (a relay
returns 200 for an endpoint that will still fail generation on a wrong model name). Colour is
never the only channel — the text next to the dot changes with the state.

**G-9. Up-arrow to edit the last message.**
**Assumption:** this plan owns the *keybinding*, not the edit. **Control Over the Record Phase 7
lands before this plan and owns the edit affordance** (`BeatEditor` + `editBeat(eventId, text)` on
`useScenePlay`), so `Composer`'s optional `onRecallLast` callback is wired by `StoryPlayerView`
straight to that action on the last `user_turn` beat — opening its inline editor and focusing it.
The shell-history *recall* behaviour (placing the last sent text into an empty composer) remains
the fallback **only** if that plan has not landed; it is honest, never pretends to have rewritten
history, and is useful on its own. Whichever is wired, the binding fires only in an **empty**
composer.

**G-10. The 320px scene-header clip.** Documented in `docs/checklist.md` as a design decision,
and owned by the mobile plan. This plan must not make it worse: the status indicator it drives
stays inside the existing `hidden … sm:flex` cluster, so the 320px control count is unchanged.

### Complex gaps — human intervention needed

**G-A. Ship compaction on by default before the experiment reports?**
Compaction changes what the model sees, which is a **writing-quality** change, not plumbing.
`docs/checklist.md` records that the last prompt-ordering change *"has not been checked for
writing quality by anything but a read"*, and that *"day-to-day comparison is worthless"* on
this endpoint — anything measured next *"needs both arms alternating inside a single session"*.
Phase 12 builds exactly that experiment. The question Phase 12 cannot answer for itself is
whether `TURN_CONTEXT_COMPACTION` ships defaulting **on** (with the experiment as a follow-up
that could force a revert) or defaulting **off** (with the auto-fit window shipping alone,
degrading to today's "drop the oldest beats" until the evidence exists). The plan is written so
either choice is a one-line default change. **Human intervention is needed to answer this
question.**

**G-B. Is the scene's summary the player's to edit?**
The summary is the cast's memory of everything older than the verbatim window. Showing it
read-only is unambiguous. Letting the player *edit* it is arguably the most powerful authoring
control in the app — and also a way to silently rewrite established history in a way no export
or trace would explain. This plan ships it read-only in Phase 6. Whether it becomes editable
(and if so, whether an edit is recorded as an event) is a product decision.
**Human intervention is needed to answer this question.**

**G-C. Evidence that would settle whether compaction hurts.** Named here so Phase 12 is not
inventing its own success criteria: (a) a **continuity probe** — scripted player lines that
refer back to facts established *before* the compaction boundary, scored on whether the cast's
reply is consistent with them; (b) a **blinded pairwise read** of matched beats from the two
arms; (c) the mechanical figures already collected by the existing harness (prompt tokens,
reusable-prefix share, TTFT). Arms **must be interleaved scene-by-scene inside one run**, per
the checklist's own conclusion. This belongs in `docs/research/experiments/` under
`docs/research/AGENT_INSTRUCTIONS.md`; **no metric from it may appear in chat or a commit
message without also being written to that folder's `manifest.yaml` and `RESULTS.md`**, and if
some arms fail, per-run rows are reported with **no aggregate** (the `EXP-2026-08-001` lesson).

### Cross-plan ownership — read this before writing code

| Item | Owner | This plan's part |
| --- | --- | --- |
| Rewind / edit a beat / edit the player's last message / branch | **Control Over the Record** | Publishes `history_compaction.invalidate_after()` for it to call; provides the Up-arrow keybinding that triggers *its* edit action (G-9) |
| **Re-roll / remove a scene image** (beat-level record mutation) | **Control Over the Record** | **Handed over.** Deleting or replacing a persisted `scene_image` event is the same event-mutation machinery as removing a beat; building a second path here would duplicate it. This plan contributes only the **additive** half — an editable prompt in `SceneImageModal` that re-paints as a *new* beat (Phase 11) — and never removes anything |
| Persisting `guidance` on the `user_turn` row | the direction-persistence plan | Phase 6's panel reads it when present, and shows the live-only value otherwise |
| Disabling the planner | the planner plan | Phase 5 leaves the scene-config menu structured so its toggle is one more consequence-labelled row |
| Rails as mobile drawers, the 320px header | the mobile plan | Phase 8/9 surfaces must not assume `lg` |
| Targeted requirements being dropped | the requirements plan | Phase 6's panel surfaces outstanding requirements; the diagnosis and fix are not this plan's |

---

## 3. Hierarchical Step-by-Step Instructions

Twelve phases. Each is independently committable and leaves the app working. Phases 1–4 are
the engineering spine; 5–11 are the legibility surface that depends on it; 12 is the evidence.

---

### Phase 1 — One place that knows the context budget

- **Locations:**
  - New `web/backend/app/services/context_budget.py` — the module. Functions:
    `resolve_window(db) -> WindowInfo` (dataclass: `max_tokens`, `source` ∈
    `detected|configured|fallback`), lifted from the body of
    `routes/options.llm_context_window` so both callers share one implementation;
    `reserve_for(ctx_parts) -> int` (system + stable prefix + volatile tail + output allowance
    + margin); `transcript_budget(window, reserve, fraction) -> int`;
    `fit_window(beats, budget_tokens, block) -> FitResult` (dataclass: `window_beats`,
    `dropped_beats`, `used_tokens`) which walks a beat list newest→oldest accumulating
    `app.rag.tokens.approx_tokens`, then **quantises the resulting depth down to a multiple of
    `block`** so the window can only change in anchor-block steps.
  - `web/backend/app/routes/options.py` — `llm_context_window` now delegates to
    `context_budget.resolve_window`; response shape unchanged.
  - `web/backend/app/core/config.py` — new settings `turn_context_max_fraction: float = 0.5`,
    `turn_context_reserve_tokens: int = 512`, `turn_context_fallback_window: int = 8192`,
    `turn_context_compaction: bool` (default per **G-A**).
  - `.env.example` + `docs/deployment.md` + `docs/workflow.md` — document all four.
  - Tests: `utils/tests/backend/services/test_context_budget.py`.
- **Rationale:** every later phase reads this. Extracting the window resolution *first* means
  the number the composer's dial is drawn against and the number the engine budgets against are
  provably the same value — today they would be two independent reads of the same endpoint.
  Quantising inside `fit_window` is the load-bearing detail: it is what keeps
  `buffer.anchored_turns`'s block anchoring intact once the depth becomes dynamic. Tests must
  pin: a growing transcript does **not** move the window every beat; the window only shrinks
  when the budget is exceeded by more than one block (hysteresis, so it cannot oscillate); and
  every function returns a sane value with zero beats, a zero budget, and an unknown window.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services utils/tests/backend/api/test_options.py`. Once green, commit locally: `[Making It Legible] (1/12) Complete: One module resolves the model's context window and fits a block-quantised transcript depth to it.` Do not push or open a PR.*

---

### Phase 2 — Confirm the turn-engine split, and pin the 800-line ceiling

> **Ownership.** The `turn_engine.py` split is **owned by `docs/plans/control-over-the-record.md`
> Phase 3**, which lands before this plan and produces `turn_emit.py` (`Emitter` / `LiveSegment` /
> `Tracer`), `beat_runner.py` (the beat helpers and the presence/relationship/stat appliers),
> `turn_setup.py` (`prepare_turn` — the pre-loop region) and, if needed, `turn_finalize.py`.
> `docs/plans/steering-the-scene.md` Phase 2 then lifts the direction helpers into
> `direction_runtime.py`. **This plan does not invent a second layout.** Every later reference in
> this file to the "opening" module means `turn_setup.py`; the beat helpers mean `beat_runner.py`.

- **Locations:**
  - `web/backend/app/services/turn_engine.py` and the modules named above — **verify only**. Run
    `wc -l web/backend/app/services/turn_*.py beat_runner.py direction_runtime.py` and confirm
    every one is under 800 lines and `turn_engine.py` retains `validate_turn_inputs`, the beat
    loop and the finalize tail. If the sibling split has **not** landed, do it here to exactly the
    module boundaries Control Over the Record Phase 3 names — never to a different set of names —
    and say so in the commit body.
  - New `utils/tests/backend/data/test_file_length_budget.py` — asserts no `.py` under
    `web/backend/app/` exceeds 800 lines. This is the durable guard the split alone does not
    provide, and it is what this phase actually contributes.
- **Rationale:** the repo rule is explicit — *"If your work grows a file past that, the plan must
  include the split as its own phase."* Phases 3, 4 and 6 all add to this file, so the ceiling has
  to be real and enforced before they run. Four plans in this program independently proposed a
  split; converging on one layout (and one owner) is what stops the second and third from
  producing an unmergeable rename. Doing this as a **verify-and-guard** phase means the existing
  suite is the proof: `utils/tests/backend/services/test_turn_engine*.py` and
  `utils/tests/backend/api/test_play.py` must pass untouched.
- *Action: Run the validation for this phase — `uv run pytest` (the whole backend suite; nothing here may change a single assertion), plus `wc -l` on every module under `web/backend/app/services/`. Once green, commit locally: `[Making It Legible] (2/12) Complete: Confirmed the turn-engine split against the agreed module layout and pinned the 800-line ceiling with a test.` Do not push or open a PR.*

---

### Phase 3 — Auto-fit the transcript window, and retire "Number of beats"

- **Locations:**
  - `web/backend/app/models/scenario.py` — new nullable `context_policy: Mapped[str | None]`
    (`"auto"` | `"fixed"`; `NULL` == auto). Additive nullable → **no Alembic migration**; the
    bootstrap reconciler self-heals it. `context_beats` is untouched.
  - `web/backend/app/schemas/scenario.py` — `context_policy` on the create/patch/read models
    (`Literal["auto","fixed"] | None`); `context_beats` keeps its `ge=5, le=100` bounds and its
    docstring is rewritten to say it applies **only** under `"fixed"`.
  - `web/backend/app/services/crud.py` (~line 576) — carry the new field.
  - `web/backend/app/services/assembler.py` — `assemble_context` stops clamping 5–100 and
    instead: reads the whole retained buffer once (`buffer.recent_turns(session_id)`, already
    capped at `turn_buffer_size`), calls `context_budget.transcript_budget` +
    `context_budget.fit_window` with `get_settings().turn_transcript_anchor_block`, then calls
    `buffer.anchored_turns(session_id, fitted_depth, block)` exactly as today. Under
    `context_policy == "fixed"` it takes the old path verbatim. `TurnContext` gains
    `window_beats: int`, `window_source: str`, `dropped_beats: int`, `window_budget_tokens: int`
    and keeps `context_beats` for the fixed path. The assembler stays **read-only**.
  - `web/backend/app/agents/character_turn_agent.py` `_transcript` (~line 638) — depth comes from
    `ctx.window_beats` (falling back to `_TRANSCRIPT_MAX_BEATS`), still `+ anchor_block` for the
    documented anchoring headroom. Same change in `agents/narrator_agent._recent` (~line 155).
  - `web/backend/app/services/turn_setup.py` (Control Over the Record Phase 3's module) — the `assemble` trace step's `data` gains
    `windowBeats`, `windowSource`, `droppedBeats`, `budgetTokens`; a new trace step
    `window` ("How far back the scene reached") is emitted with the same payload.
  - `web/backend/app/services/scene_moment.py` — the moment look-back default stops reading
    `scenario.context_beats` (**G-4**) and uses its own module constant.
  - Frontend, same phase (contract mirror rule): `web/frontend/lib/types.ts` adds
    `contextPolicy?: "auto" | "fixed"`; `web/frontend/components/feature/SceneConfigMenu.tsx`
    **deletes** the "Number of beats" range input and its readout;
    `web/frontend/components/feature/Composer.tsx` and
    `web/frontend/features/story-player/StoryPlayerView.tsx` drop the `contextBeats` /
    `onContextBeatsChange` / `beatTexts` props; `web/frontend/features/story-player/useScenePlay.ts`
    drops `contextBeats` state and its `updateScenario` writer (~lines 121, 509–515, 570) and
    computes `estimatedUsedTokens` over the whole transcript instead of `slice(-contextBeats)`.
  - `web/frontend/lib/contextBudget.ts` — `estimateBeatsTokens` / `beatsTokensFromTexts` lose
    their only caller; keep `beatsTokensFromTexts` (Phase 5 reuses it for the "what this scene
    costs" readout) and delete `estimateBeatsTokens` + `AVG_CHARS_PER_BEAT`.
  - Docs, same phase: `docs/api-contract.md` (the Scenarios row — `contextBeats` is now
    fixed-mode-only, `contextPolicy` documented, the `window` trace step added),
    `docs/data-flow.md` (§"Write + Streaming Path" and the transcript-window paragraph at
    ~line 1025), `docs/documentation.md` (Scenario column list), `docs/component-map.md`
    (`SceneConfigMenu` no longer takes `contextBeats`).
  - Tests: `utils/tests/backend/services/test_assembler.py` — replace
    `test_context_beats_is_the_buffer_fetch_depth` /
    `test_context_beats_out_of_range_is_clamped` with auto-path equivalents; new
    `utils/tests/backend/services/test_assembler_auto_window.py` (auto fits to budget; fixed
    honours `context_beats`; no Redis → empty window and the turn still assembles; the window
    does not move on a beat that does not cross a block boundary).
    `utils/tests/backend/api/test_scenarios.py` — `contextPolicy` round-trips, `contextBeats`
    still 422s out of range. Frontend: `SceneConfigMenu.test.tsx`, `Composer.test.tsx`,
    `StoryPlayerView.test.tsx` (its `contextBeats: 40` persistence assertion at ~line 200 is
    deleted, not weakened), `useScenePlay.test.ts`.
- **Rationale:** this is the owner's instruction, executed. The whole reason it is one phase and
  not two is the mirror rule — the moment `contextBeats` stops being a player control, the
  backend, the TS types, the component and the docs must agree in the same commit. The three
  research harnesses keep working untouched because they set the value through the API, and the
  plan adds `contextPolicy: "fixed"` beside it (`utils/scripts/research/run_conversation_scaling.py`,
  `run_beat_length.py`, `run_prose_end_to_end.py` each need one line). Note what this phase does
  **not** yet do: when the fitted window is smaller than the history, the oldest beats are simply
  dropped, exactly as today. Compaction is Phase 4, and keeping them separate means the window
  work can be validated on its own.
- *Action: Run the validation for this phase — `uv run pytest`, plus `npm test`, `npm run typecheck` and `npm run lint` in `web/frontend`; for the composer/config UI change also an accessibility + responsive pass (keyboard reachability of every remaining control, visible focus, AA contrast, 320/375/768/1024). Once green, commit locally: `[Making It Legible] (3/12) Complete: The transcript window fits itself to the model's context budget; the "Number of beats" slider is gone.` Do not push or open a PR.*

---

### Phase 4 — Compaction: the recap agent and the rolling session summary

- **Locations:**
  - New `web/backend/app/agents/recap_agent.py` — `summarize_history(conn, *, previous_summary,
    beats, stable_prefix) -> str | None`. Takes a **pre-resolved `LlmConn`** exactly like
    `reflection_agent` (so it never touches the request `Session`), runs at
    `ReasoningEffort.LOW`, returns tight third-person prose plus a short bullet list of hard
    facts (names, debts, injuries, promises, locations), and is registered in
    `agents/prompt_registry.py` as a new overridable key `recap.summarize` (making it editable
    in Options › Prompts — the same treatment every other writing agent gets). Best-effort:
    any `APIError`, empty reply, or missing endpoint returns `None`.
  - `web/backend/app/models/session.py` — additive nullable `summary_text: str | None`,
    `summary_through_seq: int | None`, `summary_updated_at: datetime | None`. **No migration.**
  - New `web/backend/app/services/history_compaction.py`:
    `maybe_compact(db, session, scenario, ctx_parts) -> CompactionResult` (decides, calls the
    agent, writes the three columns, returns what happened for the trace);
    `invalidate_after(db, session_id, seq)` (the seam in **G-7**);
    `summary_for(session) -> str` (the rendered block).
    Guarded by `settings.turn_context_compaction`; wrapped so **no failure can break a turn**.
  - `web/backend/app/services/session_state.py` (built by **Control Over the Record** Phase 4) —
    call `history_compaction.invalidate_after` from `truncate_session` **and from `edit_beat`**
    (Control's Phase 7 — an edited beat below the boundary makes the summary describe wording that
    no longer exists), and clear the summary columns on the new session in `copy_history`. A
    beat **re-roll** (Control's Phase 8 `beat_rerun`) is the same case and goes through the same
    call. **This plan owns those call sites** (G-7); they are the same tested places the Redis
    buffer is rebuilt, so the two can never diverge. Extend
    `utils/tests/backend/services/test_session_state.py` with a rewind-invalidates-the-summary
    case rather than duplicating the fixture here.
  - `web/backend/app/services/turn_setup.py` (Control Over the Record Phase 3's module) — calls `maybe_compact` **before**
    `assembler.assemble_context`, so the assembler stays read-only and the summary is on the
    session row by the time assembly reads it. Emits a `compaction` trace step ("Older beats
    folded into the scene's memory", with `beatsFolded`, `throughSeq`, `summaryTokens`).
  - `web/backend/app/services/assembler.py` — `TurnContext` gains `history_summary: str` and
    `summary_through_seq: int | None`, read from the session row.
  - `web/backend/app/agents/character_turn_agent.py` `_build_user_prompt` — the summary is
    rendered as the **head of the APPEND-ONLY region**, immediately above `Recent beats:`, as
    `Earlier in this scene (summary): …`. This placement is deliberate and must be preserved:
    the summary only changes when compaction fires, which is also exactly when the anchored
    window re-anchors, so the two invalidate the prompt-cache prefix *together* rather than on
    different turns. Same treatment in `agents/narrator_agent`.
  - `web/backend/app/schemas/play.py` + `web/backend/app/routes/play.py` — `SessionSummary` gains
    `summaryThroughSeq` so a reload knows the boundary without a second request; mirrored in
    `web/frontend/lib/events.ts`.
  - Docs: `docs/data-flow.md` (a new "History compaction" subsection under the turn path and a
    note in §"Scene Persistence, Resume & Export"), `docs/api-contract.md` (the `compaction`
    trace step, `summaryThroughSeq`, the new `recap.summarize` prompt key in the Prompt
    Overrides section), `docs/documentation.md` (PlaySession columns),
    `docs/architecture.md` (the decision: session-column storage, not an event).
  - Tests: `utils/tests/backend/agents/test_recap_agent.py` (a `MockTransport` handler — make it
    **path-aware**, per the known engine-probe flake), `utils/tests/backend/services/test_history_compaction.py`
    (fires only when the window drops beats; is incremental; `invalidate_after` clears a summary
    that covers a rewound seq and leaves an older one alone; a raising LLM leaves the previous
    summary intact and the turn still completes; disabled by the setting → total no-op),
    `utils/tests/backend/services/test_prompt_cache_prefix.py` (extend: adding beats without
    compaction does not move the summary line).
- **Rationale:** this is the second half of the owner's instruction and the only part of the plan
  that changes what the model reads. Three constraints shape it. (i) **Cost** — incremental
  summarisation bounded to one anchor block means one cheap LOW-effort call roughly every twenty
  beats, not a growing re-summarisation every turn. (ii) **Cache** — putting the summary anywhere
  in the volatile tail would place a block that changes occasionally *after* the transcript,
  which is harmless; putting it above the transcript is *better*, because it re-anchors on the
  same turn the window does. (iii) **Best-effort** — Redis absent means no buffer means no
  dropped beats means nothing to compact; an unreachable model means the previous summary stands
  and the oldest beats drop as they do today. Neither is an error path the player sees.
- *Action: Run the validation for this phase — `uv run pytest` (backend), and `npm test` in `web/frontend` for the `events.ts` mirror change. Once green, commit locally: `[Making It Legible] (4/12) Complete: History that falls out of the window is compacted into a rolling per-session summary, invalidatable on rewind.` Do not push or open a PR.*

---

### Phase 5 — Label every scene control by consequence and cost

> **Config-menu contract after this plan.** `SceneConfigMenu` contains exactly four rows: *Max
> turns*, *Suggestions*, *Beat length* (all relabelled here) and the new read-only *What the scene
> remembers*. **"Number of beats" is gone** (Phase 3). `docs/plans/depth-for-players.md` lands
> after this plan and **adds** rows and per-row pins on top of this structure — presets (its Phase
> 5), Turn planning (6), Register (7), Ties (10) — and must **preserve the consequence copy
> written here** rather than authoring a second set for the same three controls. That plan's own
> cross-plan note already leaves `contextBeats` out of every preset.

- **Locations:**
  - `web/frontend/components/feature/SceneConfigMenu.tsx` — each row becomes label + one-line
    consequence + (where it exists) a cost readout, using the *existing* pattern from the
    deleted beats slider (`lib/contextBudget.beatsTokensFromTexts`) generalised:
    - *Max turns* → **"How many beats one message produces"**, help: *"the cap on replies —
      narrator beats count too; the scene can still end sooner"*, cost: *"≈ N s per extra beat"*
      derived from the session's own observed beat durations rather than a hardcoded number
      (fall back to no cost line before any turn has run).
    - *Suggestions* → **"Follow-up ideas offered after each turn"**, help: *"0 turns them off"*.
    - *Beat length* → **"How much a character says at once"**, help: the real paragraph ranges
      already documented (`short` 1–2, `medium` 2–4, `long` 5–6), cost: the per-tier token
      allowance from `lib/types.ts`.
    - A new read-only row: **"What the scene remembers"** — verbatim beats in the window, the
      token budget behind it, and whether anything has been compacted; sourced from Phase 3/4's
      values through `useScenePlay`.
  - `web/frontend/components/ui/SceneControlSelect.tsx` — accepts an optional `help` node
    rendered as a `<p>` wired via `aria-describedby`, so the consequence line is announced with
    the control rather than floating beside it.
  - `web/frontend/components/feature/Composer.tsx` — the direction box placeholder becomes
    *"Tell the scene what should happen — as vague or as exact as you like"*. **Note:**
    `docs/plans/steering-the-scene.md` Phase 4 lands before this plan and moves the direction
    field out of `Composer.tsx` into a new `components/feature/DirectionRow.tsx` (a labelled
    strip in narrator mode, the textarea under POV). Put this copy on `DirectionRow` — do not
    re-inline a direction box in `Composer`. The message box's
    `aria-label` distinguishes the two modes ("Your line as {name}" under POV);
    `web/frontend/components/feature/PovSelect.tsx` gains a one-line description of what
    "Speaking as" does; `ContextUsageDial`'s tooltip says what the number means in words, not
    just `5.2K / 16K`.
  - `web/frontend/components/layout/SceneHeader.tsx` — the Inspector button's title becomes
    consequence-shaped and the Graph switch keeps its existing `title`.
  - Docs: `docs/design-system.md` (a short "control copy" rule under §Domain Vocabulary — every
    control states its effect, and its cost where one exists), `docs/component-map.md`.
  - Tests: `SceneConfigMenu.test.tsx` (each control exposes an accessible description; the
    remembers row renders both states), `SceneControlSelect.test.tsx` (new — `aria-describedby`
    association), `Composer.test.tsx`, `PovSelect.test.tsx`, `ContextUsageDial.test.tsx`.
- **Rationale:** the review's G6 is that nothing tells a new player what any of this is; the
  cheapest 80 % of that is the copy already attached to controls they can see. It comes *after*
  Phase 3 because one of the four rows no longer exists and one new read-only row only has data
  once the auto-window ships. Doing it before would mean writing copy for a deleted control.
- *Action: Run the validation for this phase — `npm test`, `npm run typecheck`, `npm run lint` in `web/frontend`, plus an accessibility + responsive pass (every description reachable by screen reader via `aria-describedby`, keyboard-only operation of the popover, AA contrast on the new help text — run `uv run python utils/scripts/check_contrast.py` if any token changed, and check 320/375/768/1024). Once green, commit locally: `[Making It Legible] (5/12) Complete: Every scene control now states its effect and its cost.` Do not push or open a PR.*

---

### Phase 6 — "What the scene knows", and the line where memory stops

- **Locations:**
  - New `web/backend/app/routes/play.py` endpoint
    `GET /play/{scenario_id}/sessions/{session_id}/context` → `SceneKnowledgeResponse`
    (new model in `web/backend/app/schemas/play.py`): `windowBeats`, `windowSource`,
    `droppedBeats`, `budgetTokens`, `promptTokens`, `taggedNames[]`, `retrieval`
    (`{fired, reason, matched}`), `relationships[]` (which ties were injected, from the
    `relationship` trace steps), `direction` (`{text, items[], outstanding[]}`),
    `summary` (`{text, throughSeq, updatedAt}`). It is assembled **from data already persisted** —
    the latest turn's `TurnTrace` rows (`assemble`, `window`, `lore`, `files`, `relationship`,
    `direction`, `context`, `compaction`) plus the session's summary columns — so no new writing
    happens on the turn path. Implemented in a new
    `web/backend/app/services/scene_knowledge.py` so the route stays thin.
  - `web/frontend/lib/events.ts` — the mirrored `SceneKnowledge` interface;
    `web/frontend/lib/api.ts` — `getSceneKnowledge(scenarioId, sessionId)`.
  - New `web/frontend/components/feature/SceneMemoryPanel.tsx` — modelled on
    `TurnInspectorPanel` (docked right column, `w-full` below `sm`, `sm:w-[340px]`, `CloseButton`,
    `AsyncPanel` for its five states). Sections in plain language: *How far back the cast
    remembers* · *What it has folded into memory* (the summary, read-only — **G-B**) · *Files you
    attached* · *What it looked up* · *Who it knows about whom* · *What you asked for, and what
    landed*. It is the same data as the Inspector, written for a player: the Inspector answers
    "what did the loop do", this answers "what does the scene know".
  - `web/frontend/features/story-player/StoryPlayerView.tsx` — a header control opens it (a
    third state alongside Inspector, mutually exclusive with it so two 340px rails never dock at
    once); `web/frontend/components/layout/SceneHeader.tsx` gains `onToggleMemory`/`memoryOpen`.
  - The **forgetting line**: a new `SceneMessageKind`-adjacent marker rendered positionally in
    `StoryPlayerView` (not injected into `scene.messages`, so no state churn): a centred hairline
    reading *"— everything above here is remembered as a summary —"* placed before
    `messages.length - windowBeats`. New `web/frontend/components/feature/MemoryEdge.tsx`.
    **Known imprecision, stated in the component's docstring and in `docs/checklist.md`:**
    transcript messages and buffer beats are not exactly 1:1 (internal thoughts fold into a
    speaker's beat), so the marker is accurate to within a beat or two; the panel carries the
    exact figures. Hidden entirely when `droppedBeats == 0`.
  - `web/frontend/features/story-player/useScenePlay.ts` — folds `windowBeats`/`droppedBeats`
    from the live `window` trace step (through `turn-stream.ts`, beside the existing
    `latestContextTokens`) and seeds them from history on resume.
  - Docs: `docs/api-contract.md` (the new endpoint + shape), `docs/data-flow.md`
    (§"Scene Persistence, Resume & Export"), `docs/routes.md` is unchanged (no new route),
    `docs/component-map.md` + `docs/design-system.md` (the panel and the memory edge).
  - Tests: `utils/tests/backend/api/test_play_context.py` (assembles from traces; 404 on an
    unknown session; sane empty response for a session with no turns),
    `utils/tests/backend/services/test_scene_knowledge.py`,
    `web/frontend/components/feature/SceneMemoryPanel.test.tsx`,
    `web/frontend/components/feature/MemoryEdge.test.tsx`,
    `web/frontend/features/story-player/StoryPlayerView.test.tsx` (the panel opens and closes the
    Inspector; the edge appears only when beats have been dropped).
- **Rationale:** the app already knows all of this and shows none of it to the player. Reading it
  back out of the persisted traces (rather than emitting a new frame) means the panel works on a
  *resumed* scene too, and adds nothing to the turn's hot path. The forgetting line is the single
  most important piece of it — the owner's complaint that the cast *"forgets what happens so
  often"* is partly a real defect (the requirements plan owns that) and partly the absence of any
  signal that forgetting is happening at all.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api utils/tests/backend/services`, plus `npm test`, `npm run typecheck`, `npm run lint` in `web/frontend`, and an accessibility + responsive pass on the new rail (focus order, Escape closes it, `aria-label`, no horizontal page overflow at 320/375/768/1024, AA contrast on the memory edge hairline text). Once green, commit locally: `[Making It Legible] (6/12) Complete: A player-facing read of what the scene knows, and a visible line where verbatim memory ends.` Do not push or open a PR.*

---

### Phase 7 — Make the status light mean something

- **Locations:**
  - `web/backend/app/routes/options.py` — `GET /options/llm/health` →
    `LlmHealthResponse` (new in `web/backend/app/schemas/settings.py`):
    `state` ∈ `reachable | model_missing | unreachable | unconfigured`, `backend`, `model`,
    `checkedAt`, `detail`. Implemented in `web/backend/app/services/llm_backend.py` as
    `health(base_url, api_key, model)` reusing the existing `_CACHE`/`_ttl_seconds()` probe
    machinery and its `clear_cache` test seam — a `GET /models` listing, matched against the
    configured model id (**G-8**). Never raises; a transport failure is `unreachable`.
  - `web/frontend/lib/api.ts` — `getLlmHealth()`; `web/frontend/lib/types.ts` — the mirror.
  - New `web/frontend/hooks/use-model-health.ts` — fetch on mount, re-poll on a 60 s interval,
    pause while `document.visibilityState === "hidden"`, and re-check immediately after a stream
    error (the moment the player most needs to know).
  - `web/frontend/components/layout/SceneHeader.tsx` — the hardcoded dot + "Narrator active"
    is replaced by a real four-state indicator: dot **plus** changing text (*Model ready* /
    *Model not found* / *Model unreachable* / *No model set*), `role="status"`, a `title`
    naming the endpoint's backend, and an `aria-label` that never depends on colour. It stays
    inside the existing `hidden … sm:flex` cluster so the 320px control count is unchanged
    (**G-10**).
  - Docs: `docs/api-contract.md` (§Options/Settings — the new endpoint),
    `docs/data-flow.md` (§"Reasoning-Budget Flow" neighbours it — add the health probe),
    `docs/design-system.md` (the four states and their tokens),
    `docs/component-map.md` (`SceneHeader` no longer renders a fake status).
  - Tests: `utils/tests/backend/api/test_options_llm_health.py` (each of the four states, with a
    **path-aware** `MockTransport` handler), `web/frontend/hooks/use-model-health.test.ts`,
    `web/frontend/components/layout/SceneHeader.test.tsx`.
- **Rationale:** the review's G8, answered by driving rather than deleting. A player on a local
  model currently learns their endpoint died by sending a turn and waiting out
  `LLM_GEN_TIMEOUT_SECONDS` (300 s). The probe already exists and is already cached and polled;
  this only surfaces it. Colour is never the sole channel, per the repo's ADA rules.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api`, plus `npm test` and `npm run typecheck` in `web/frontend`, and an accessibility pass on the indicator (announced as a live `role="status"`, meaning conveyed in text as well as colour, AA contrast in all three themes — `uv run python utils/scripts/check_contrast.py` if any token is added). Once green, commit locally: `[Making It Legible] (7/12) Complete: The scene header's status light reports whether the configured model endpoint is actually reachable.` Do not push or open a PR.*

---

### Phase 8 — Keyboard fluency and the shortcut sheet

- **Locations:**
  - New `web/frontend/hooks/use-scene-shortcuts.ts` — a single document-level `keydown` listener
    that **ignores every event originating in an editable target** except the two that belong
    there. Bindings: `/` focuses the composer (when focus is not already in a field);
    `ArrowUp` in an **empty** composer recalls or edits the last player message (**G-9**);
    `Escape` closes, in order, the open mention menu → the config popover → the dossier or the
    open rail → nothing; `?` (Shift+/) opens the shortcut sheet; `Escape` closes it.
  - New `web/frontend/components/feature/ShortcutSheet.tsx` — a `Modal`-based list of the
    bindings, grouped, with a footer line naming the composer's existing Enter/Shift+Enter and
    `@` behaviours (which are real shortcuts nobody documents today).
  - `web/frontend/components/feature/Composer.tsx` — new optional `onRecallLast?: () => void`
    and a `lastSent` value; the Enter/Shift+Enter and `@`-menu key handling in
    `onFieldKeyDown` is left exactly as it is (the menu must keep owning
    Arrow/Enter/Tab/Escape while open — the hook checks that first and stands down).
  - `web/frontend/features/story-player/StoryPlayerView.tsx` — mounts the hook, owns the sheet's
    open state, and passes the close callbacks for dossier/rails/inspector/memory panel.
  - `web/frontend/features/story-player/useScenePlay.ts` — remembers `lastSentText` so recall has
    something to give back.
  - Docs: `docs/design-system.md` (a keyboard-shortcut section), `docs/component-map.md`,
    `docs/routes.md` unchanged.
  - Tests: `web/frontend/hooks/use-scene-shortcuts.test.ts` (each binding; **and** that typing
    `/` or `?` inside a textarea does nothing, which is the bug this class of feature always
    ships with), `web/frontend/components/feature/ShortcutSheet.test.tsx`,
    `web/frontend/components/feature/Composer.test.tsx` (recall on empty, no-op on non-empty).
- **Rationale:** the second third of G6. A shortcut sheet behind `?` is also the cheapest place
  to *document* the composer behaviours that already exist and are invisible (Enter sends,
  Shift+Enter newlines, `@` tags a file). The hook must be written defensively around the
  existing mention menu, which already owns Arrow/Enter/Tab/Escape in the composer — that
  interaction is the one real hazard in this phase.
- *Action: Run the validation for this phase — `npm test`, `npm run typecheck`, `npm run lint` in `web/frontend`, and an accessibility pass (the sheet traps focus and restores it on close; every shortcut has a pointer equivalent; nothing steals keys from a text field; 320/375/768/1024). Once green, commit locally: `[Making It Legible] (8/12) Complete: Keyboard fluency — slash to focus, up to recall, Escape to close, and a shortcut sheet behind "?".` Do not push or open a PR.*

---

### Phase 9 — Three coach marks on the first scene

- **Locations:**
  - New `web/frontend/lib/coachMarks.ts` — the `localStorage` key and read/write helpers,
    following the exact shape of `lib/theme.ts` / `lib/font-size.ts` (including the
    SSR-safe guard); dismissal is stored as a set of mark ids so a later fourth mark can ship
    without re-showing the first three.
  - New `web/frontend/hooks/use-coach-marks.ts` — returns the next undismissed mark and a
    `dismiss(id)`; renders nothing until after hydration (reuse `hooks/use-hydrated.ts`) so the
    server and client markup agree.
  - New `web/frontend/components/feature/CoachMark.tsx` — one small anchored callout (Framer
    Motion, honouring the repo's global reduced-motion rule — a matching base style, no separate
    media query needed), positioned relative to a passed anchor ref, dismissible by button,
    Escape, or acting on the thing it points at. **Not a modal tour** — no overlay, no backdrop,
    no forced sequence; the scene stays fully usable behind it.
  - `web/frontend/features/story-player/StoryPlayerView.tsx` — three anchors: the composer
    textarea (*"Type what you say or do. Enter sends."*), the `PovSelect` control (*"Speak as one
    of the cast instead of narrating."*), and the `CastRail` (*"Click anyone here to see who they
    are and how they feel about you."*). The cast-rail mark is suppressed below `lg`, where the
    rail is hidden — it must not point at nothing (the mobile plan owns the drawer that would
    let it).
  - Docs: `docs/design-system.md` (the coach-mark pattern and its dismissal contract),
    `docs/component-map.md`.
  - Tests: `web/frontend/components/feature/CoachMark.test.tsx`,
    `web/frontend/hooks/use-coach-marks.test.ts` (dismissal persists; a dismissed mark never
    returns; nothing renders before hydration), `StoryPlayerView.test.tsx` (only one mark at a
    time; none below `lg` for the rail).
- **Rationale:** the final third of G6, and the review explicitly ruled out a modal tour. Three
  marks, anchored to the three things a first-time player provably does not discover: that the
  composer takes actions as well as speech, that they can play *as* a character, and that the
  cast rail is interactive. Persisted dismissal means it is a one-time cost.
- *Action: Run the validation for this phase — `npm test`, `npm run typecheck`, `npm run lint` in `web/frontend`, and an accessibility + responsive pass (the mark is announced, keyboard-dismissible, never traps focus, respects `prefers-reduced-motion`, and fits at 320/375/768/1024 without overlapping the control it describes). Once green, commit locally: `[Making It Legible] (9/12) Complete: Three dismissible, persisted coach marks anchored to the composer, the POV select and the cast rail.` Do not push or open a PR.*

---

### Phase 10 — Search the transcript, and recap it

- **Locations:**
  - New `web/frontend/features/story-player/transcript-search.ts` — pure helpers
    (`matchBeats(messages, query)` returning indices + match ranges, case- and
    diacritic-insensitive, searching `text`/`action`/`thought`), unit-testable without a DOM.
  - New `web/frontend/components/feature/TranscriptSearch.tsx` — a compact find bar (open from
    the scene header or `Ctrl/Cmd+F` **only when the composer is not focused** — otherwise let the
    browser have it), with match count, next/previous, `Escape` to close, and scroll-into-view
    driven through the existing `use-sticky-bottom` ref. Matches are highlighted with `<mark>`,
    never colour alone.
  - `POST /play/{scenario_id}/sessions/{session_id}/recap` in `web/backend/app/routes/play.py` →
    `{ text }`, implemented in `web/backend/app/services/history_compaction.py` as
    `recap(db, session, through_seq)`, which calls the **same** `agents/recap_agent.summarize_history`
    Phase 4 introduced over the events above a given seq. **No second summarisation path** — this
    is the whole reason Phase 4 built the agent as a standalone, connection-taking function. It
    reuses the stored summary as its `previous_summary` when the requested range starts above the
    boundary, so a recap of a long scene is also incremental.
  - `web/frontend/lib/api.ts` — `postSessionRecap`; `web/frontend/lib/events.ts` — the mirror.
  - `web/frontend/components/feature/SceneMemoryPanel.tsx` — a **Recap everything above** action
    that renders the returned prose inline, with a loading and an error state through
    `AsyncPanel`.
  - Docs: `docs/api-contract.md` (the recap endpoint), `docs/data-flow.md`,
    `docs/component-map.md`.
  - Tests: `web/frontend/features/story-player/transcript-search.test.ts`,
    `web/frontend/components/feature/TranscriptSearch.test.tsx`,
    `utils/tests/backend/api/test_play_recap.py` (returns prose; an unreachable model returns a
    clean error envelope rather than a 500; an empty session returns an empty recap).
- **Rationale:** "find a line" and "tell me what happened" are the two things a player asks of a
  long scene, and both are currently impossible without scrolling. Search is client-side because
  the whole transcript is already in memory after rehydration — a server round-trip would be
  slower and would not survive an offline substrate. Recap is server-side because it is a model
  call, and it must be the *same* model call as compaction or the two will drift apart in tone
  and in what they consider a fact worth keeping.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api`, plus `npm test`, `npm run typecheck`, `npm run lint` in `web/frontend`, and an accessibility + responsive pass (find bar reachable and dismissible by keyboard, match count announced via a live region, `<mark>` contrast in all three themes, 320/375/768/1024). Once green, commit locally: `[Making It Legible] (10/12) Complete: Transcript search, and a recap that reuses the compaction agent rather than inventing a second one.` Do not push or open a PR.*

---

### Phase 11 — Scene images: edit the prompt, paint it again

> Scope note, restated because it is easy to get wrong: **Control Over the Record owns removing
> or replacing a persisted `scene_image` event.** This phase adds only the additive half — an
> editable prompt that produces a **new** beat. Nothing here deletes anything.

- **Locations:**
  - `web/backend/app/schemas/play.py` — `MomentRequest` gains optional `prompt: str | None` and
    `negative: str | None`. When `prompt` is supplied, `services/scene_moment.generate_moment`
    **skips the `moment_agent` call** and goes straight to the `render` stage with the player's
    text (still passed through `moment_agent.strip_names`, so the existing no-names guarantee —
    the subject of `EXP-2026-08-002` — is not quietly bypassed by hand-written input).
  - `web/backend/app/services/scene_moment.py` — the branch above; the `moment_stage` frame
    sequence is unchanged, so the client's existing staged progress keeps working.
  - `web/frontend/lib/events.ts` — `MomentRequestBody` mirror; `web/frontend/lib/api.ts` —
    `postSceneMoment` passes the new fields.
  - `web/frontend/components/feature/SceneImageModal.tsx` — the existing "Show the prompt"
    disclosure (already implemented, read-only) becomes an editable `TextArea` plus a
    **Paint again with this prompt** button, wired to a new `onRepaint(prompt, negative)` prop.
    Disabled while a moment stream is in flight, with the same staged progress copy
    `CreateImageBar` uses.
  - `web/frontend/features/story-player/useScenePlay.ts` — `createImage` gains optional
    prompt/negative arguments; the existing independent `momentStream` is reused unchanged.
  - Docs: `docs/api-contract.md` (§Scene images / the moment endpoint),
    `docs/comfyui-image-generation.md`, `docs/data-flow.md` (§"In-Narrative Scene Image Flow"),
    `docs/checklist.md` — **Control Over the Record Phase 8 lands first in this program and closes
    the "Scene images cannot be regenerated or deleted from the transcript" entry outright** (it
    ships re-roll, take pager and delete). Expect the bullet to be **gone**; do not re-add it in
    order to narrow it. If it is somehow still present, narrow it and note the discrepancy.
  - Tests: `utils/tests/backend/api/test_play_moment_prompt_override.py` (an explicit prompt skips
    the agent; names are still stripped; an empty override falls back to the agent),
    `web/frontend/components/feature/SceneImageModal.test.tsx`.
- **Rationale:** the prompt is already persisted on the event and already displayed; making it
  editable is a small, purely additive change that turns "here is why the picture looks like
  that" into "here is how to get the picture you wanted". Keeping the destructive half out avoids
  building a second event-mutation path beside the one Control Over the Record is building.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api utils/tests/backend/services`, plus `npm test`, `npm run typecheck`, `npm run lint` in `web/frontend`, and an accessibility + responsive pass on the modal (the textarea is labelled, the button state is announced, the modal still fits at 320/375). Once green, commit locally: `[Making It Legible] (11/12) Complete: A scene image's prompt is editable and can be re-painted as a new beat.` Do not push or open a PR.*

---

### Phase 12 — Does compaction hurt the writing? Measure it, then reconcile the docs

- **Locations:**
  - `make new-experiment SLUG=context-compaction` → `docs/research/experiments/EXP-2026-08-011-context-compaction/`
    with `PROTOCOL.md` written **before** the run (the contract's §3.2), `manifest.yaml`,
    `RESULTS.md` after, and `figures/` generated by a script that hardcodes no number.
  - New `utils/scripts/research/run_context_compaction.py`, modelled on
    `utils/scripts/research/run_conversation_scaling.py` (which already builds a world, drives
    scripted player lines, and records per-turn usage). **Two arms, interleaved scene-by-scene
    inside one process run** — arm **A** `contextPolicy: "fixed", contextBeats: 100` (today's
    behaviour), arm **B** auto + `TURN_CONTEXT_COMPACTION=true` — because `docs/checklist.md`
    states plainly that day-to-day comparison on this endpoint is worthless and that arms must
    alternate inside a single session.
  - Metrics, per **G-C**: a **continuity probe** (scripted late-scene player lines that refer to
    facts established before the compaction boundary, scored for consistency), a **blinded
    pairwise read** of matched beats, and the mechanical figures the harness already collects
    (prompt tokens, reusable-prefix share, TTFT, planner share).
  - `docs/research/CLAIMS.md` — a new claim row for "compaction preserves continuity beyond the
    verbatim window" with its status set by the result, `unsupported` until then.
  - `docs/checklist.md` — remove the now-closed items (the beats-vs-buffer `TURN_BUFFER_SIZE`
    mismatch note, which the auto-window supersedes; the scene-image regenerate/delete entry is
    **not** this plan's — Control Over the Record Phase 8 already closed it, per Phase 11's note)
    and **add** the new deferrals this plan creates: the memory-edge
    marker's ±1-beat imprecision, `context_beats` surviving as an API-only fixed-mode override,
    **G-A** and **G-B** if still unanswered, and any validation skipped.
  - `docs/documentation.md` + `docs/architecture.md` — the status paragraph and the decision
    record for auto-fitted context + compaction.
- **Rationale:** compaction is the one change in this plan that alters what the model reads, and
  the repository's own record says an unmeasured prompt change is how the last one went wrong.
  Running it as a pre-registered, interleaved, two-arm experiment is the only form of evidence
  the checklist considers valid here. **If some arms fail, report per-run rows and no aggregate**
  — survivors of a partially-failed run are not a random subsample (`EXP-2026-08-001` is the
  worked example). If the continuity probe shows arm B losing facts arm A keeps, the honest
  outcome is to default `TURN_CONTEXT_COMPACTION` off and say so, not to ship it quietly.
- *Action: Run the validation for this phase — `make validate-research` **and** `uv run pytest` **and** `npm test`; record every number in `manifest.yaml` + `RESULTS.md` before it appears anywhere else. Once green, commit locally: `[Making It Legible] (12/12) Complete: Interleaved two-arm compaction experiment recorded, claims and checklist reconciled.` Do not push or open a PR.*

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Context-budget module | Window resolution (detected → configured → fallback), reserve model, block-quantised `fit_window` | `web/backend/app/services/context_budget.py` |
| Shared window resolution | `/options/llm/context-window` and the turn loop read one implementation | `web/backend/app/routes/options.py` |
| File-length ceiling verified | The turn-engine split is **owned by Control Over the Record Phase 3**; this plan verifies it and adds the durable guard | `web/backend/app/services/turn_engine.py` (verify), `utils/tests/backend/data/test_file_length_budget.py` |
| File-size guard | No `.py` under `web/backend/app/` exceeds 800 lines | `utils/tests/backend/data/test_file_length_budget.py` |
| Auto-fitted window | `context_policy` column; assembler fits the depth to the budget; anchoring preserved | `web/backend/app/models/scenario.py`, `web/backend/app/services/assembler.py` |
| Beats slider removed | "Number of beats" deleted from the config popover and its whole prop chain | `web/frontend/components/feature/SceneConfigMenu.tsx`, `Composer.tsx`, `features/story-player/{StoryPlayerView,useScenePlay}.ts(x)` |
| Recap agent | Incremental LOW-effort summariser, overridable as `recap.summarize` | `web/backend/app/agents/recap_agent.py`, `web/backend/app/agents/prompt_registry.py` |
| Compaction service | Trigger, storage, rendering, and the `invalidate_after` rewind seam | `web/backend/app/services/history_compaction.py` |
| Session summary columns | `summary_text` / `summary_through_seq` / `summary_updated_at` (additive nullable) | `web/backend/app/models/session.py` |
| Summary in the prompt | Rendered at the head of the append-only region, above `Recent beats:` | `web/backend/app/agents/character_turn_agent.py`, `narrator_agent.py` |
| Consequence-labelled controls | Every scene control states its effect and, where it exists, its cost | `web/frontend/components/feature/SceneConfigMenu.tsx`, `components/ui/SceneControlSelect.tsx`, `Composer.tsx`, `PovSelect.tsx`, `ContextUsageDial.tsx` |
| Scene-knowledge endpoint | Player-facing read assembled from persisted traces + the session summary | `web/backend/app/routes/play.py`, `web/backend/app/services/scene_knowledge.py`, `web/backend/app/schemas/play.py` |
| Scene memory panel | The same data the Inspector holds, written for a player | `web/frontend/components/feature/SceneMemoryPanel.tsx` |
| Memory edge marker | The transcript line where verbatim history ends | `web/frontend/components/feature/MemoryEdge.tsx` |
| Model-health endpoint + indicator | `GET /options/llm/health` and a four-state, non-colour-only status | `web/backend/app/routes/options.py`, `web/backend/app/services/llm_backend.py`, `web/frontend/hooks/use-model-health.ts`, `web/frontend/components/layout/SceneHeader.tsx` |
| Keyboard shortcuts + sheet | `/`, `ArrowUp`, `Escape`, `?` — and the sheet that documents them | `web/frontend/hooks/use-scene-shortcuts.ts`, `web/frontend/components/feature/ShortcutSheet.tsx` |
| Coach marks | Three anchored, dismissible, persisted marks — not a modal tour | `web/frontend/lib/coachMarks.ts`, `web/frontend/hooks/use-coach-marks.ts`, `web/frontend/components/feature/CoachMark.tsx` |
| Transcript search | Client-side find with match count and highlighting | `web/frontend/features/story-player/transcript-search.ts`, `web/frontend/components/feature/TranscriptSearch.tsx` |
| Recap endpoint | `POST …/sessions/{id}/recap`, reusing the compaction agent | `web/backend/app/routes/play.py`, `web/backend/app/services/history_compaction.py` |
| Scene-image prompt editing | Editable prompt + re-paint as a new beat (additive only) | `web/backend/app/services/scene_moment.py`, `web/backend/app/schemas/play.py`, `web/frontend/components/feature/SceneImageModal.tsx` |
| FE↔BE contract mirror | `contextPolicy`, `SceneKnowledge`, `LlmHealth`, `summaryThroughSeq`, moment prompt override | `web/frontend/lib/events.ts`, `web/frontend/lib/types.ts`, `web/frontend/lib/api.ts` |
| **Backend tests** | Context budget | `utils/tests/backend/services/test_context_budget.py` |
| **Backend tests** | Auto-fitted window (auto, fixed, no-Redis, no-oscillation) | `utils/tests/backend/services/test_assembler_auto_window.py`, `utils/tests/backend/services/test_assembler.py` |
| **Backend tests** | Recap agent (path-aware `MockTransport`) | `utils/tests/backend/agents/test_recap_agent.py` |
| **Backend tests** | Compaction trigger, incrementality, invalidation, best-effort failure | `utils/tests/backend/services/test_history_compaction.py` |
| **Backend tests** | Prompt-cache prefix still stable with the summary block | `utils/tests/backend/services/test_prompt_cache_prefix.py` |
| **Backend tests** | Scene-knowledge endpoint + service | `utils/tests/backend/api/test_play_context.py`, `utils/tests/backend/services/test_scene_knowledge.py` |
| **Backend tests** | Model health, four states | `utils/tests/backend/api/test_options_llm_health.py` |
| **Backend tests** | Recap endpoint | `utils/tests/backend/api/test_play_recap.py` |
| **Backend tests** | Moment prompt override (agent skipped, names still stripped) | `utils/tests/backend/api/test_play_moment_prompt_override.py` |
| **Backend tests** | `contextPolicy` round-trip; `contextBeats` bounds unchanged | `utils/tests/backend/api/test_scenarios.py` |
| **Frontend tests** | Config menu without the slider, with descriptions and the remembers row | `web/frontend/components/feature/SceneConfigMenu.test.tsx` |
| **Frontend tests** | Control description association | `web/frontend/components/ui/SceneControlSelect.test.tsx` |
| **Frontend tests** | Composer: prop chain, recall, unchanged mention-menu keys | `web/frontend/components/feature/Composer.test.tsx` |
| **Frontend tests** | Memory panel + memory edge | `web/frontend/components/feature/SceneMemoryPanel.test.tsx`, `MemoryEdge.test.tsx` |
| **Frontend tests** | Status indicator + health hook | `web/frontend/components/layout/SceneHeader.test.tsx`, `web/frontend/hooks/use-model-health.test.ts` |
| **Frontend tests** | Shortcuts (incl. "does nothing inside a text field") + sheet | `web/frontend/hooks/use-scene-shortcuts.test.ts`, `web/frontend/components/feature/ShortcutSheet.test.tsx` |
| **Frontend tests** | Coach marks: one at a time, persisted dismissal, none pre-hydration | `web/frontend/components/feature/CoachMark.test.tsx`, `web/frontend/hooks/use-coach-marks.test.ts` |
| **Frontend tests** | Search helpers + find bar | `web/frontend/features/story-player/transcript-search.test.ts`, `web/frontend/components/feature/TranscriptSearch.test.tsx` |
| **Frontend tests** | Player integration: panel/inspector exclusivity, edge visibility, no `contextBeats` write | `web/frontend/features/story-player/StoryPlayerView.test.tsx`, `useScenePlay.test.ts` |
| **Experiment** | Pre-registered, interleaved two-arm compaction study | `docs/research/experiments/EXP-2026-08-011-context-compaction/`, `utils/scripts/research/run_context_compaction.py` |
| **Docs** | Contract, flow, components, design, deployment, status, claims, checklist | `docs/{api-contract,data-flow,component-map,design-system,deployment,workflow,documentation,architecture,checklist}.md`, `docs/research/CLAIMS.md`, `.env.example` |
