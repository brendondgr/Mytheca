# Live Turn Visibility

**Status:** complete — all ten phases shipped 2026-08-19
**Created:** 2026-08-19
**Owner:** brendondgr

> ## What the measurement changed about this plan
>
> [EXP-2026-08-003](../research/experiments/EXP-2026-08-003-live-turn-visibility/) tested
> the two interventions this plan is built around, and **refuted the framing of both**.
>
> * Capping the reasoning budget did **not** reduce completion tokens (592 ± 108 → 607 ± 25).
>   It cut the *dispersion* four-fold, which is consistent with bounding a tail — but that is
>   a reading, not a result, and the timeout tail was not measured.
> * Streaming did **not** collapse time-to-first-prose. On this model the first *answer*
>   token arrives at 10.59 s against an 11.82 s total — about 90 % of the way through.
>
> What streaming actually buys is the **reasoning channel at 0.55 s**, roughly 20× earlier
> than the first word of prose, in the same call. So **Phase 5 — the live reasoning channel —
> is the load-bearing change**, not Phases 2/4 as written below. Phases 2–4 remain necessary
> (they are what makes Phase 5 possible at all), but they are plumbing, not the payoff.
>
> The plan text below is left as written, because a plan that is quietly edited to match its
> results stops being evidence of anything. The corrections live here and in RESULTS.md.

## 1. Introduction

A player turn today is a black box that can take minutes and sometimes dies at exactly
five minutes. The whole time, the story player shows one static pill reading *"The scene
is unfolding"*. Nothing about the wait is legible: the player cannot tell whether the app
misread their message, which character was chosen, what that character is thinking, or how
much of their scene direction will actually be delivered.

Two independent faults produce that experience, and this plan fixes both.

**Fault 1 — the model is never told to stop thinking.** `services/llm_backend.py` detects
only vLLM (`GET /version`) and llama.cpp (`GET /props`). The configured endpoint is an
OpenAI-protocol *relay* that serves neither probe, so `get_backend()` returns `UNKNOWN` and
`apply_reasoning()` does nothing. Every per-operation `ReasoningEffort` in the codebase —
`INTENT_EFFORT = LOW`, `TURN_EFFORT = MEDIUM`, `NARRATOR_EFFORT = LOW` — is silently
discarded. The model reasons until it exhausts the 8192-token `GEN_MIN_TOKENS` floor or
until `_GEN_TIMEOUT` (hardcoded 300 s) kills the socket. That is the reported timeout, and
it is also why the bot "overthinks".

**Fault 2 — nothing is shown until everything is finished.** `llm.chat_complete_usage()`
never sets `stream: true`, so each call blocks until the completion is whole. A normal turn
is three sequential blocking calls (intent → planner → character) and a scene's first
message is two (intent → narrator). Only then does `_Emitter.emit_streamed()` take the
*already-complete* text and slice it with `chunk_text()` into fake deltas. The typing
animation is a replay of something that finished seconds ago.

The approach: cap the reasoning and make the generation timeout configurable (Phase 1);
add a real streaming transport and an incremental emission parser (Phases 2–3); wire them
into the turn path so a character's private thought lands *before* their dialogue and the
dialogue arrives word by word (Phase 4); surface the model's own in-flight reasoning as an
optional live channel (Phase 5); and turn the remaining silent steps — reading the message,
choosing a speaker, delivering a direction — into things the player can watch happen
(Phases 6–9). Phase 10 closes the validation gate and measures the result.

Phases 1–4 are ordered by dependency and must ship in sequence. Phases 5–9 each depend on
Phase 4 but are independent of one another and may be parallelised across agents.

## 2. Gaps & Unanswered Questions

**Resolved by inspection (assumptions stated, no human input needed):**

1. **What engine is actually configured?** Probed on 2026-08-19: `http://localhost:4000`
   returns `{"detail":"Not Found"}` for both `/v1/version` and `/props`, but `GET /v1/models`
   reports `owned_by: "relay:llama.cpp · local"` and `relay.upstream_model` per entry.
   **Assumption:** detection gains a third path that reads the upstream engine from the
   models listing, and an unknown engine falls back to sending *both* budget keys rather
   than sending none. **Verified against the live relay:** it accepts both keys together
   without error, and `thinking_budget_tokens` measurably shortens the reasoning on the
   llama.cpp upstream (build `b9692`, `gemma-4-26B-it`). Single-sample smoke test only —
   the real before/after belongs to Phase 10's experiment.

1b. **Where does the reasoning actually come out?** **Not** inline in `content` as
   `<think>…</think>`. The upstream returns a dedicated `message.reasoning_content` field
   (and `delta.reasoning_content` when streaming), which the app currently never reads.
   Two consequences, both folded into the phases below: the live reasoning channel needs
   no tag parsing at all (Phase 5 gets simpler and more robust), and the existing
   `"The model hit its token limit before replying"` / `"returned an empty response"`
   errors in `llm.chat_complete_usage()` are the expected result whenever the budget is
   spent entirely on reasoning — `content` is empty while `reasoning_content` is full.
   `strip_reasoning()` stays for models that *do* inline their thinking; it is now the
   fallback rather than the only path.

2. **What happens to the continuity guard once a beat has already streamed?**
   `consistency.review()` currently inspects a whole candidate line and can regenerate it
   *before* anything is emitted. Under streaming the line is already on screen.
   **Assumption:** add an optional `reset: true` field to delta events meaning *discard the
   text accumulated for this id and replace it*. The client already accumulates by event id,
   so this is an additive envelope change. A regenerated beat visibly re-writes itself,
   which is honest and cheaper than withholding every later speaker's stream.

3. **Should the structural calls (intent, planner, direction) stream too?**
   **Assumption:** no. They return small JSON objects that are useless until complete.
   They benefit from Phase 1's budget cap, not from Phase 2's transport. Streaming them
   would add parsing risk for no perceptible gain.

4. **Default visibility for raw chain-of-thought.** **Assumption:** three-position setting
   — `off` / `thought` / `full` — defaulting to `thought` (the polished `internal_thought`
   the character already produces). Raw reasoning is opt-in because it frequently spoils the
   beat it precedes.

**Needs human input:**

5. **Is a visibly self-rewriting beat acceptable?** Gap 2's `reset` approach means a player
   can watch a line get replaced when the continuity guard rejects it. The alternative is to
   stream only the turn's first character beat and buffer every later one, which preserves
   the illusion but returns the second and third speakers to today's blocking behaviour.
   *Human intervention is needed to answer this question.* The plan implements `reset` and
   keeps the buffering path behind a settings flag so the decision can be reversed without
   rework.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Bound the thinking and make the timeout configurable

The turn cannot be made to feel fast while the model is free to reason without limit, and
no amount of streaming saves a call that dies at 300 s. This phase is also the only one
that improves things without any UI work, so it ships first.

#### Step 1.1 — Detect the engine behind an OpenAI-protocol relay
- **Locations:** `web/backend/app/services/llm_backend.py` — extend `detect_backend()`
  with a third probe that reads `GET {base}/models` and matches the `owned_by` /
  `relay.upstream_model` fields against the known engine names; add a
  `InferenceBackend.RELAY` member or resolve straight through to the detected upstream.
  Keep the existing `/version` and `/props` probes first so direct engines are unaffected.
- **Rationale:** this is the single change that re-enables every reasoning budget the
  codebase already sets. Without it Phases 2–9 make an unbounded generation *prettier*
  rather than shorter.

#### Step 1.2 — Never silently drop the budget on an unknown engine
- **Locations:** `web/backend/app/services/llm_backend.py` — `apply_reasoning()` currently
  no-ops for `UNKNOWN`; change it to write both `thinking_token_budget` (vLLM) and
  `thinking_budget_tokens` (llama.cpp). Add a module-level note that an engine ignoring an
  unrecognised body key is the expected, safe outcome.
- **Rationale:** an unrecognised endpoint should degrade to *capped*, not to *uncapped*.
  This also covers Ollama, recorded in `docs/checklist.md` as silently receiving no budget.

#### Step 1.3 — Make the generation timeout an operator setting
- **Locations:** `web/backend/app/core/config.py` (new `llm_gen_timeout_seconds`, default
  300), `web/backend/app/services/llm.py` (`_GEN_TIMEOUT` reads it rather than hardcoding),
  `.env.example`, `docs/deployment.md`.
- **Rationale:** the 300 s wall is currently invisible and unchangeable. A capped model
  should never reach it, but the operator needs the dial when it does.

#### Step 1.4 — Show the detected engine and the applied budget in Options
- **Locations:** `web/backend/app/routes/settings.py` (expose detected backend + effective
  budget on the LLM config read), `web/backend/app/schemas/settings.py`,
  `web/frontend/features/options/tabs/LanguageModelsTab.tsx`.
- **Rationale:** the whole bug was invisible. A readout saying *"Engine: llama.cpp (via
  relay) · thinking budget applied"* — or *"unknown, sending both budget keys"* — makes a
  recurrence self-diagnosing, and directly serves the goal of a handy app at every step.

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api/test_llm_backend.py utils/tests/backend/services/test_llm.py utils/tests/backend/services/test_llm_context_fit.py`, plus `npm test` for `LanguageModelsTab` and `npm run typecheck`. Once green, commit locally: `[Live Turn Visibility] (1/10) Complete: Engine detection now resolves through an OpenAI relay, unknown engines get a capped thinking budget, and the generation timeout is configurable.` Do not push or open a PR.*

---

### Phase 2 — A real streaming transport

#### Step 2.1 — Add a streaming completion primitive
- **Locations:** `web/backend/app/services/llm.py` — new `chat_complete_stream()` alongside
  `chat_complete_usage()`. It sets `stream: true` plus `stream_options.include_usage`, opens
  the response with `httpx.Client.stream`, parses `data:` SSE lines, yields text deltas as
  they arrive, and returns the assembled text plus `prompt_tokens` on completion. Reuse
  `_fit_max_tokens()`, `_learn_context_limit()`, and the `APIError` mapping unchanged.
- **Rationale:** every later phase consumes this. Streaming also changes the timeout
  semantics for free — the read window applies *between chunks* instead of to the whole
  response, so a long generation no longer trips a five-minute wall.

#### Step 2.2 — Separate the reasoning channel from the answer channel
- **Locations:** `web/backend/app/services/llm.py` — the stream parser reads
  `delta.reasoning_content` and `delta.content` as two independent channels and surfaces
  both to the caller; `web/backend/app/agents/_common.py` — a stateful counterpart to
  `strip_reasoning()` for endpoints that instead inline `<think>` blocks or harmony
  channels in `content`, so a growing buffer can be classified without waiting for the end.
- **Rationale:** gap 1b — the configured endpoint already separates the two, so the
  primary path needs no tag parsing. The incremental scrubber is the fallback for models
  that inline their thinking. Phase 5 consumes whichever channel produced the reasoning.

#### Step 2.4 — Stop treating a reasoning-only completion as an error
- **Locations:** `web/backend/app/services/llm.py` — when `content` is empty but
  `reasoning_content` is not, the message should say the budget was spent on reasoning and
  name the setting that fixes it, rather than the current generic empty/limit errors.
- **Rationale:** this is a live failure mode today (gap 1b), and Phase 1's budget cap makes
  it *more* likely to be hit on a tight budget, not less. The diagnosis must be accurate
  when it happens.

#### Step 2.3 — Fall back cleanly when the endpoint cannot stream
- **Locations:** `web/backend/app/services/llm.py` — on a non-200 or a non-SSE content type,
  fall back to the blocking path once and cache the fact per endpoint+model.
- **Rationale:** the relay proxies several upstreams; one refusing `stream: true` must
  degrade to today's behaviour rather than fail the turn.

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services/test_llm.py` plus a new `utils/tests/backend/services/test_llm_streaming.py` driving `httpx.MockTransport` with a scripted SSE body (including a mid-stream `[DONE]`, a usage frame, and a non-SSE fallback). Note the existing engine-probe flake recorded in memory: make new mock handlers path-aware so `GET /models` and `POST /chat/completions` are answered separately. Once green, commit locally: `[Live Turn Visibility] (2/10) Complete: llm.py can stream completions over SSE, with incremental reasoning classification and a blocking fallback.`*

---

### Phase 3 — Incremental emission parsing

#### Step 3.1 — Build a streaming emission accumulator
- **Locations:** `web/backend/app/services/emission.py` — a new `EmissionAccumulator` (or
  `parse_incremental()`) that is fed text deltas and yields segment events: *segment opened*
  (speaker + type known), *segment grew* (new text for the open segment), *segment closed*.
  It must recognise `<speaker:N>`, `<type:X>`, and `<thinking>…</thinking>` as they complete,
  hold back partial tags at the buffer edge, and finish identically to `parse_emission()`
  when fed a whole string at once.
- **Rationale:** this is the enabler for the entire feature. `parse_emission()` runs
  `finditer` over a finished string; nothing can be shown early until the parser can work on
  a prefix. Building it as a pure, side-effect-free unit keeps it exhaustively testable
  before any of it reaches the turn loop.

#### Step 3.2 — Prove equivalence with the batch parser
- **Locations:** `utils/tests/backend/services/test_emission_incremental.py`.
- **Rationale:** the batch parser is load-bearing for every existing turn test. Feeding the
  accumulator the same fixtures one character at a time, in random chunk sizes, and
  asserting the segment list matches `parse_emission()` exactly is the cheapest guarantee
  that Phase 4 changes *when* things appear and not *what* appears.

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services/test_emission_incremental.py utils/tests/backend/services/` and confirm the existing emission suite is untouched. Once green, commit locally: `[Live Turn Visibility] (3/10) Complete: Added an incremental emission parser proven equivalent to the batch parser under arbitrary chunking.`*

---

### Phase 4 — Stream the turn path for real

#### Step 4.1 — Teach the emitter to stream live segments
- **Locations:** `web/backend/app/services/turn_engine.py` — `_Emitter` gains a method that
  opens an event id, yields growing deltas as the accumulator produces them, and persists
  the full row once on close. `emit_streamed()` (the `chunk_text()` replay) stays for the
  non-streaming fallback path only.
- **Rationale:** the persist-once/emit-many contract already exists; only its *timing*
  changes. Keeping the old method intact means the fallback from Step 2.3 needs no
  special-casing downstream.

#### Step 4.2 — Add the `reset` field to delta events
- **Locations:** `web/backend/app/events/envelope.py`, `web/frontend/lib/events.ts` (the
  hand-maintained mirror — same change, same commit), `web/frontend/features/story-player/turn-stream.ts`
  (`mergeFrame` clears accumulated text when `reset` is set), `docs/api-contract.md`.
- **Rationale:** required by the continuity guard (gap 2). Additive and optional, so every
  existing client and test is unaffected.

#### Step 4.3 — Stream the character beat, thought first
- **Locations:** `web/backend/app/services/turn_engine.py` `_generate_speaker()`,
  `web/backend/app/agents/character_turn_agent.py` (a streaming sibling of
  `generate_line_with_usage()` that preserves `_voice_params()` and the prefix-cache logging).
- **Rationale:** this is the change the player actually feels. Because the emission format
  puts `<thinking>` before the spoken line, streaming makes the private thought land and
  finish *while the dialogue is still being written* — several seconds of real signal where
  there is currently a blank pill.

#### Step 4.4 — Stream the narrator, and re-run the guard after the fact
- **Locations:** `web/backend/app/agents/narrator_agent.py`,
  `web/backend/app/services/turn_engine.py` (`_narrator_interstitial()`, and the
  `consistency.review()` block in `_generate_speaker()` which now runs on the completed
  stream and re-emits with `reset: true` when it rejects).
- **Rationale:** a scene's first message is narrator-led, so leaving the narrator blocking
  would mean the very first thing a new player sees is still the old behaviour.

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api/test_play_turn.py utils/tests/backend/api/test_play_turn_direction.py utils/tests/backend/api/test_play_turn_pov.py utils/tests/backend/services/`, plus `npm test` for `turn-stream` and `useScenePlay`, and `npm run typecheck`. Once green, commit locally: `[Live Turn Visibility] (4/10) Complete: Character and narrator beats stream live from the model, thought before speech, with a reset-capable delta contract.`*

---

### Phase 5 — The live reasoning channel

#### Step 5.1 — Emit in-flight reasoning as its own trace step
- **Locations:** `web/backend/app/services/turn_engine.py` (a `reasoning` trace step fed by
  the `reasoning_content` channel from Step 2.2), `web/backend/app/agents/character_turn_agent.py`.
- **Rationale:** the model's deliberation is currently discarded unread. Routing it to the
  existing trace channel costs nothing on the wire when the setting is off and gives the most
  literal possible answer to "what is it thinking right now". Per gap 1b this is a clean
  field on the wire, not a parse.

#### Step 5.2 — Add the three-position visibility setting
- **Locations:** `web/backend/app/schemas/settings.py`,
  `web/backend/app/services/settings_store.py`,
  `web/frontend/features/options/tabs/LanguageModelsTab.tsx`.
- **Rationale:** raw reasoning routinely states what a character will say before they say
  it. Default `thought`; `full` is opt-in. See gap 4.

#### Step 5.3 — Render it as subordinate, collapsible text
- **Locations:** `web/frontend/components/feature/TranscriptBeat.tsx` (a dimmed, small,
  collapsible reasoning line above the existing muted-italic `thinks` line),
  `web/frontend/features/story-player/turn-stream.ts`.
- **Rationale:** raw chain-of-thought is long and rambling. It must never compete visually
  with the prose; `docs/frontend-polish-spec.md` governs the treatment.

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services/ utils/tests/backend/api/test_settings.py`, plus `npm test` for `TranscriptBeat` and `LanguageModelsTab`. Accessibility pass: the collapsible must be keyboard-operable with visible focus, and the reasoning region must not be announced by the live region that carries the prose. Once green, commit locally: `[Live Turn Visibility] (5/10) Complete: The model's in-flight reasoning streams to an opt-in, collapsible channel under the character's beat.`*

---

### Phase 6 — An honest status strip

#### Step 6.1 — Add the missing phases
- **Locations:** `web/frontend/features/story-player/turn-stream.ts` — extend `TurnPhase`
  with `gathering`, `reading`, and `planning`, and map the `assemble` / `lore` / `files`,
  `intent`, and `plan` trace steps onto them in `applyTurnStatus()`.
- **Rationale:** those frames already stream (the client sends `trace: true`); the reducer
  currently ignores them, which is the entire reason the pill sits on its idle default
  through the longest part of the wait.

#### Step 6.2 — Give each phase a real sentence
- **Locations:** `web/frontend/components/feature/TurnStatusStrip.tsx` (`labelFor()`).
- **Rationale:** "Gathering the scene" → "Reading your message" → "Deciding who speaks" →
  "Mei is thinking" converts a blank interval into a sequence with visible progress.

> *Action: Run the validation for this phase — `npm test` for `TurnStatusStrip` and `turn-stream`, `npm run typecheck`, `npm run lint`. Accessibility pass: the strip is an `aria-live="polite"` region — confirm the added transitions do not produce announcement spam at 320/375/768/1024. Once green, commit locally: `[Live Turn Visibility] (6/10) Complete: The status strip names the real step it is on instead of idling on a generic line.`*

---

### Phase 7 — Read-back and who's-up-and-why

#### Step 7.1 — Show how the message was interpreted
- **Locations:** `web/frontend/features/story-player/turn-stream.ts` (surface the `intent`
  trace step's `kind` + `directive` + resolved names), `web/frontend/components/feature/TurnStatusStrip.tsx`
  or a small sibling component under `components/feature/`.
- **Rationale:** the earliest and most opaque part of the wait becomes informative, and a
  misread ("read as: you are narrating") is catchable before the turn commits to it.

#### Step 7.2 — Name the chosen speaker and the reason
- **Locations:** `web/backend/app/services/turn_engine.py` (carry the planner's `register`
  and `stakes` onto the `speaker` trace step's `data`),
  `web/frontend/features/story-player/turn-stream.ts`, `TurnStatusStrip.tsx`.
- **Rationale:** `planner_agent.next_beat` already computes both. Surfacing them answers
  the most common confusion in play — why *this* character responded — for the cost of
  threading two existing values.

> *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api/test_play_turn.py`, plus `npm test` for `TurnStatusStrip` and `turn-stream`. Accessibility + responsive pass at 320/375/768/1024 (the read-back line must wrap, never truncate the directive). Once green, commit locally: `[Live Turn Visibility] (7/10) Complete: The turn reads your message back and names who is up and why.`*

---

### Phase 8 — The live direction checklist

#### Step 8.1 — Render the outstanding requirements
- **Locations:** `web/frontend/features/story-player/turn-stream.ts` (fold the `direction`
  trace steps into a requirement list with delivered/outstanding state), a new
  `web/frontend/components/feature/DirectionChecklist.tsx` rendered in `DirectorRail`.
- **Rationale:** the engine already computes what the turn owes the player and marks each
  item delivered. Today that only exists in the Inspector. Shown live it becomes the clearest
  progress indicator in the app.

#### Step 8.2 — Make an undeliverable requirement visible
- **Locations:** the same components; the `plan` trace step already carries
  `data.undelivered` when the scene's beat cap is reached.
- **Rationale:** `docs/checklist.md` records that a direction exceeding the scene's turn cap
  is silently compressed. The player currently discovers this by noticing something never
  happened.

> *Action: Run the validation for this phase — `npm test` for `DirectionChecklist`, `DirectorRail`, and `turn-stream`; `npm run typecheck` and `npm run lint`. Accessibility pass: the checklist is a list with per-item state announced once on change, not on every re-render. Once green, commit locally: `[Live Turn Visibility] (8/10) Complete: The player watches their scene direction get delivered item by item.`*

---

### Phase 9 — Give the wait a place to live

#### Step 9.1 — Place the pending beat immediately
- **Locations:** `web/frontend/features/story-player/turn-stream.ts` (open a pending beat on
  the `speaker` trace frame rather than on the first story event),
  `web/frontend/components/feature/TranscriptBeat.tsx`,
  `web/frontend/components/feature/TurnStatusStrip.tsx` (demoted to scene-level status).
- **Rationale:** the layout commits early, the reasoning → thought → speech sequence fills
  in one stable place, and the floating pill stops being the only thing on screen. Reserve
  the beat's height per `docs/frontend-polish-spec.md` so this reduces layout shift rather
  than adding it.

> *Action: Run the validation for this phase — `npm test` for `TranscriptBeat`, `TurnStatusStrip`, `turn-stream`, and the story-player route tests; `npm run typecheck`. Accessibility + responsive pass at 320/375/768/1024, including `prefers-reduced-motion` (the repo-wide rule in `styles/themes.css` kills animation under it — confirm the pending beat has a matching static base style). Once green, commit locally: `[Live Turn Visibility] (9/10) Complete: A pending beat holds the character's place in the transcript while it fills in.`*

---

### Phase 10 — Close the gate: docs, full sweep, and a measured result

#### Step 10.1 — Update the documentation that this plan invalidates
- **Locations:** `docs/api-contract.md` (the `reset` field, the `reasoning` trace step, the
  new trace-driven phases, and the correction that visible prose now delta-streams *live*
  rather than being chunked after generation), `docs/data-flow.md` (the turn path),
  `docs/component-map.md` (`DirectionChecklist`), `docs/design-system.md` (the reasoning
  channel's treatment), `docs/deployment.md` + `.env.example` (the timeout variable),
  `docs/architecture.md` (the streaming transport decision), `docs/checklist.md` (close the
  Ollama-no-budget entry; record anything deferred).
- **Rationale:** required by the global rules in the same change that alters behaviour. The
  api-contract in particular currently documents the fake-delta behaviour as the design.

#### Step 10.2 — Full validation sweep
- **Locations:** repository-wide.
- **Rationale:** `uv run pytest` (948 cases today) and `npm test` in `web/frontend` must both
  be green, plus `npm run typecheck`, `npm run lint`, and
  `node utils/scripts/check_frontend_css.mjs`. Run the frontend suite with `--maxWorkers=4`:
  `docs/checklist.md` records two load-flaky modal tests that fail at full concurrency on a
  busy machine.

#### Step 10.3 — Measure it, and record the measurement properly
- **Locations:** `docs/research/experiments/<EXP-ID>/` per `docs/research/AGENT_INSTRUCTIONS.md`,
  scaffolded with `make new-experiment SLUG=live-turn-visibility`.
- **Rationale:** the plan claims a latency improvement, and the research record is mandatory
  for any reported metric. Measure time-to-first-visible-token before and after across a
  fixed set of turns — `config.py` already carries `turn_ttft_slo_ms = 1200` as the stated
  target, so there is a threshold to report against. Record failed and aborted runs; do not
  aggregate over survivors of a partially-failed run.

> *Action: Run the full validation gate — `uv run pytest`, `cd web/frontend && npm test -- --maxWorkers=4 && npm run typecheck && npm run lint`, `node utils/scripts/check_frontend_css.mjs`, and `make validate-research`. Once green, commit locally: `[Live Turn Visibility] (10/10) Complete: Documentation reconciled, full gate green, and the latency change recorded as an experiment.` Then merge the feature branch into `main` locally.*

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Relay engine detection | Resolve the upstream engine from `GET /models` when the probes 404 | `web/backend/app/services/llm_backend.py` |
| Unknown-engine budget | Send both budget keys instead of none | `web/backend/app/services/llm_backend.py` |
| Configurable timeout | `llm_gen_timeout_seconds` replaces the hardcoded 300 s | `web/backend/app/core/config.py`, `services/llm.py`, `.env.example` |
| Engine readout | Detected engine + applied budget shown to the operator | `web/frontend/features/options/tabs/LanguageModelsTab.tsx` |
| Streaming transport | `chat_complete_stream()` over SSE, with blocking fallback | `web/backend/app/services/llm.py` |
| Incremental scrubber | Stateful reasoning/channel classifier for a growing buffer | `web/backend/app/agents/_common.py` |
| Incremental parser | `EmissionAccumulator` yielding segments from a prefix | `web/backend/app/services/emission.py` |
| Live emitter | Persist-once/emit-many driven by the live stream | `web/backend/app/services/turn_engine.py` |
| `reset` delta field | Lets a rejected beat visibly re-write itself | `web/backend/app/events/envelope.py`, `web/frontend/lib/events.ts` |
| Streaming agents | Streaming siblings for the character and narrator calls | `web/backend/app/agents/{character_turn_agent,narrator_agent}.py` |
| Reasoning channel | Opt-in live chain-of-thought as a `reasoning` trace step | `turn_engine.py`, `TranscriptBeat.tsx`, `LanguageModelsTab.tsx` |
| Status phases | `gathering` / `reading` / `planning` + real sentences | `features/story-player/turn-stream.ts`, `components/feature/TurnStatusStrip.tsx` |
| Intent read-back | "Read as: …" surfaced from the existing `intent` trace | `components/feature/TurnStatusStrip.tsx` |
| Speaker rationale | Planner `register` + `stakes` on the `speaker` trace, rendered | `turn_engine.py`, `TurnStatusStrip.tsx` |
| Direction checklist | Live delivered/outstanding requirement list | `web/frontend/components/feature/DirectionChecklist.tsx` |
| Pending beat | The character's place held in the transcript while it fills | `components/feature/TranscriptBeat.tsx`, `turn-stream.ts` |
| Backend tests | Streaming transport, incremental parsing, engine detection, turn path | `utils/tests/backend/{services,api,agents}/` |
| Frontend tests | Co-located beside each touched component | `web/frontend/**/*.test.{ts,tsx}` |
| Docs | Contract, data flow, components, design system, deployment, checklist | `docs/*.md` |
| Experiment | Time-to-first-token before/after against the 1200 ms SLO | `docs/research/experiments/<EXP-ID>/` |
