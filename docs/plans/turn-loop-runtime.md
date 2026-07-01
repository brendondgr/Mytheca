# Velora — Turn-Loop Runtime: Implementation Plan

> Companion to the design doc `Documents/Plans/Velora/2.velora-turn-loop-plan.md` (v0.3,
> §16 "Phased commits" P1–P11). This plan translates that design into Velora's
> phase-by-phase, commit-per-phase engineering format and records the locked decisions
> for the build.

## 1. Introduction

This plan builds Velora's **runtime turn loop** — the path from a human player's message to
the bot's streamed, validated story output — replacing the story player's scripted seed
(`useScenePlay`) with a real, agent-driven, NDJSON-streamed engine. It implements the
four bands of the design: **Assemble** (read-only context), **Produce** (the per-character
POV think→speak loop, streamed), **Commit** (cold-path turn-writer), and **Reflect**
(read-time interlude). The work lands across the FastAPI brain
(`web/backend/app/{routes,services,agents,events,memory,schemas}`) and the Next.js story
player (`web/frontend/features/story-player`, `hooks`, `lib`), grounded in the existing
event envelope, stat system, graph reader/writer, RAG retriever, and LLM provider.

The engine is **one POV loop**: each active character *thinks* then *speaks* in turn order;
**Narrator Mode = the same loop + optional narrator interstitials**, **POV Mode = the loop
with interstitials off**. Control fields (speaker, event type) are constrained; prose is
free. The hot path is **read-only**; all mutation defers to the cold-path turn-writer.

## 2. Decisions & Gaps (locked with the user)

- **D-A — Stream transport: POST streams NDJSON directly.** `POST /api/play/{scenarioId}/turn`
  runs the turn and returns the event stream in its response body, reusing the proven
  `postNdjson` / `_lines()` + `StreamingResponse` pattern already used by build/triage.
  Redis holds the recent-turn buffer, per-character interior state, and (cache of) the seq
  cursor — **not** the stream transport. A separate `GET /stream/{sessionId}` + Redis
  pub/sub (reconnect / multi-watcher fan-out) is a **documented seam**, deferred.
- **D-B — No dice (D11).** The turn loop never emits checks. `check` is removed from the
  runtime `branch_choices` option (`BranchChoiceOption`); branch choices carry `label` +
  `outcome` only. The frontend `CheckCard` path is retired from turn-loop rendering.
- **D-C — Parallel processing enabled.** vLLM is available, so off-hot-path and
  independent work (reflection for all N, Director-concurrent-with-assembly, cascade
  refresh) may run concurrently via a bounded worker pool, gated by a config knob
  `TURN_MAX_CONCURRENCY` (default 4). **Sequential speech stays sequential** (a later
  speaker reacts to an earlier one). Tests mock the LLM, so concurrency never affects
  determinism.
- **D-D — Simulated delta streaming first.** `chat_complete` returns a full string; the
  backend chunks completed prose into `message_start → message_delta* → message_end`
  frames for the live-typing feel (offline-testable, deterministic). True token streaming
  from vLLM is a later enhancement (P11 / seam).
- **D-E — seq is DB-authoritative.** Next `seq` per session = `max(existing seq)+1`,
  enforced by a `UniqueConstraint(session_id, seq)`; Redis caches the cursor best-effort.
  Works with no Redis (offline/test path).
- **D-F — Constrained control fields via thin tags + optional guided decoding.** The model
  emits a thin header (`<speaker:N>`, `<type:...>`) + free prose; the backend owns the
  envelope and resolves `N → characterId` against the numbered roster. On vLLM, the
  provider may additionally pin `speaker`/`type` with guided decoding; otherwise the thin
  tags + a parse-and-drop fallback hold the contract. An out-of-roster speaker is dropped.
- **Scope of this session: P1–P8.** Build, validate, and commit P1 through P8, then **stop
  for review** before the reflection (P9), multi-party (P10), and vLLM-hardening (P11)
  phases. P9–P11 are specified here for continuity.

Best-effort throughout (mirrors Neo4j/Qdrant): Redis down → no buffer/interior, turn still
runs and persists to Postgres; Neo4j down → empty subgraph; a slow/failed reflect never
blocks the stream. All LLM calls are offline-mocked in tests (`httpx.MockTransport`).

## 3. Phases

### P1 — Transport + envelope (full-event mode)

- **Locations:** `web/backend/app/events/envelope.py` (add `internal_thought`; drop `check`
  from `BranchChoiceOption`), `web/backend/app/schemas/base.py` (`EventType` += `internal_thought`),
  `web/backend/app/events/stream.py` (new — envelope/line builders: `make_event`,
  `to_ndjson_line`), `web/backend/app/models/event.py` (+`UniqueConstraint(session_id, seq)`),
  `web/backend/alembic/versions/*` (new migration), `web/backend/app/services/turn_engine.py`
  (new — minimal echo turn: persist `user_turn`, build+validate+persist a hand-built event
  set, yield NDJSON), `web/backend/app/services/events_store.py` (new — `next_seq`,
  `persist_event`), `web/backend/app/memory/buffer.py` (new — Redis recent-turn buffer,
  best-effort), `web/backend/app/schemas/play.py` (new — `TurnRequest{sessionId?, text, directedAt?}`),
  `web/backend/app/routes/play.py` (new — `POST /play/{scenarioId}/turn`, pre-flight validate,
  `StreamingResponse`), `web/backend/app/main.py` (register router), `web/backend/app/core/config.py`
  (turn-loop settings).
- **Rationale:** Stand up the streaming spine and the durable event/seq contract before any
  generation. Everything downstream emits through this path.
- **Tests:** `utils/tests/backend/api/test_play_turn.py` (echo turn streams a valid,
  seq-monotonic event set end to end; `user_turn` persisted; every line validates against
  `story_event_adapter`; unknown scenario → 404; no-Redis path works),
  `utils/tests/backend/data/test_event_seq.py` (`next_seq`, unique-constraint guard).
- **Action:** Run `uv run pytest utils/tests/backend/{api,data}` + ruff/mypy on touched
  files. Commit: `[Turn Loop Runtime] (1/8) Complete: streaming turn transport + event/seq contract (echo turn end to end).`

### P2 — Band-1 assembly (read-only context)

- **Locations:** `web/backend/app/services/assembler.py` (new — `assemble_context(db, scenario, session, directed_at)` →
  a `TurnContext` dataclass: resolved cast (ordered), setting, active stat schema + clamped
  per-character values, loaded stat guidance, recent buffer, scenario subgraph (best-effort),
  in-voice anchors from the buffer), `web/backend/app/agents/_common.py` (reuse
  `world_context`; add a `stable_prefix` builder for World Primer + contract + stat guidance),
  `web/backend/app/services/graph_reader.py` (reuse `scenario_graph`), `web/backend/app/services/stats.py`
  + `stat_guidance.py` (reuse). Concurrency helper `web/backend/app/services/concurrency.py`
  (new — bounded `gather` over threads, capped by `TURN_MAX_CONCURRENCY`).
- **Rationale:** The generator needs a single, materialized, best-effort context object;
  isolating assembly keeps Produce a pure function of `TurnContext`.
- **Tests:** `utils/tests/backend/services/test_assembler.py` (assembles cast/stats/guidance/buffer/subgraph;
  graph-down → empty subgraph, no raise; missing cast/setting id skipped gracefully;
  stable prefix contains primer + stat guidance).
- **Action:** Run `uv run pytest utils/tests/backend/services` + ruff/mypy. Commit:
  `[Turn Loop Runtime] (2/8) Complete: Band-1 context assembler (buffer + subgraph + stats/guidance + stable prefix).`

### P3 — POV loop, single-pass + delta streaming (no thinking yet)

- **Locations:** `web/backend/app/agents/character_turn_agent.py` (new — `generate_line(ctx, speaker)`:
  build the bookended prompt, call `chat_complete`, parse the thin `<speaker:N>/<type:...>`
  header + prose, resolve `N → characterId`), `web/backend/app/services/emission.py` (new —
  thin-tag parser → typed events; out-of-roster drop), `web/backend/app/events/envelope.py`
  (add delta frames `MessageStart/MessageDelta/MessageEnd` + a `StreamFrame` union for the
  wire), `web/backend/app/events/stream.py` (chunk a visible event into delta frames),
  `web/backend/app/services/turn_engine.py` (replace echo with the single-speaker POV loop:
  assemble → generate → build events → validate → stream deltas), `web/backend/app/core/llm`
  provider hook for optional vLLM guided decoding (`web/backend/app/services/llm.py` —
  pass-through `extra_body` for `guided_choice`/`guided_json`, off by default).
  Frontend: `web/frontend/lib/events.ts` (new — `PlayEvent` / `StreamFrame` TS types),
  `web/frontend/hooks/use-event-stream.ts` (new — consume `postNdjson`, accumulate deltas,
  route by type, expose connection state), `web/frontend/features/story-player/useScenePlay.ts`
  (wire real turn submit + event routing, optimistic player bubble, in-flight guard),
  `web/frontend/lib/api.ts` (`postTurn` stream helper), `web/frontend/lib/types.ts` (fix
  `EventTag`: add `character_dialogue`, `internal_thought`).
- **Rationale:** First real generation; proves a two-speaker turn streams in order with
  distinct speakers and valid envelopes, and the UI renders deltas live.
- **Tests:** backend `test_character_turn_agent.py` (mocked LLM: thin-tag parse, name→id,
  out-of-roster drop), `test_turn_engine_pov.py` (two-speaker turn streams in order, valid
  envelopes, deltas chunk + finalize); frontend `use-event-stream.test.ts` (delta accumulate
  → finalize on message_end; routes state_update to panels; in-flight guard), `useScenePlay`
  test updates.
- **Action:** Run backend `uv run pytest` (affected) + frontend `npm test`/`typecheck`/`lint`;
  **a11y + responsive pass** (transcript live-region, keyboard, 320/375/768/1024). Commit:
  `[Turn Loop Runtime] (3/8) Complete: per-character POV loop + delta streaming wired end to end (FE+BE).`

### P4 — Think → speak + voice anchoring

- **Locations:** `web/backend/app/agents/character_turn_agent.py` (emit a hidden
  `<thinking>` block before the line; in-voice, short, character-led prompt guardrails;
  fold in `speech` descriptor + in-voice anchors from the buffer; sampler params —
  repetition/frequency penalties, lower top_p), `web/backend/app/services/emission.py`
  (thinking → `internal_thought` event, `visibility: hidden`), `web/backend/app/services/turn_engine.py`
  (persist internal_thought hidden; **withhold from the stream**).
- **Rationale:** The primary voice lever — same-context think→speak conditioning at one call.
- **Tests:** `test_character_turn_agent.py` (thinking parsed + hidden; `internal_thought`
  persisted, not streamed; anchors + speech reach the prompt; voice-bleed check across two
  characters via captured request bodies).
- **Action:** `uv run pytest` (affected) + ruff/mypy. Commit:
  `[Turn Loop Runtime] (4/8) Complete: think→speak (hidden internal_thought) + in-voice anchors + sampler tuning.`

### P5 — Speaker selection + Narrator interstitials (one engine)

- **Locations:** `web/backend/app/agents/director_agent.py` (new — `who_is_up(ctx)` →
  structure-only `{speakers:[ids], needsBranch, beat}`, constrained to the roster; trivial
  fast-path for a single addressee, reasoned escalation for charged/crowded beats; launched
  concurrent with assembly), `web/backend/app/agents/narrator_agent.py` (new — optional
  interstitial `narration` between speakers, Narrator Mode only), `web/backend/app/services/turn_engine.py`
  (drive the speaker queue; POV vs Narrator mode = interstitials off/on), `web/backend/app/schemas/play.py`
  (turn/scenario mode field; default POV).
- **Rationale:** Promote "who's up" to a real step; prove the same engine renders both modes.
- **Tests:** `test_director_agent.py` (single addressee fast-path; multi-speaker order;
  roster-constrained, drops invented speakers), `test_turn_engine_modes.py` (same turn,
  POV = no narration interstitial, Narrator = interstitial present).
- **Action:** `uv run pytest` (affected) + ruff/mypy. Commit:
  `[Turn Loop Runtime] (5/8) Complete: reasoned Director (who's-up) + Narrator interstitials (one engine, two modes).`

### P6 — Retrieval gate + hybrid RAG

- **Locations:** `web/backend/app/services/retrieval_gate.py` (new — cheap model-free gate:
  off-roster entity/place/event named? world-history question? else skip),
  `web/backend/app/services/assembler.py` (call the gate; on fetch, hybrid retrieve via
  `app/rag/retriever.retrieve` + inject under a fenced `RETRIEVED LORE` header),
  `web/backend/app/memory/prefetch.py` (new — best-effort warm prefetch of cast/setting
  between turns; top-up on the hot path).
- **Rationale:** Most turns skip retrieval; a fired retrieval grounds the line in durable
  lore without diluting the prompt.
- **Tests:** `test_retrieval_gate.py` (skip vs fetch triggers), `test_assembler_rag.py`
  (skip-turn issues no retrieve; fetch-turn injects fenced lore; gate decisions logged;
  RAG-off path is a clean skip).
- **Action:** `uv run pytest` (affected) + ruff/mypy. Commit:
  `[Turn Loop Runtime] (6/8) Complete: retrieval gate + gated hybrid-RAG injection (fenced lore).`

### P7 — Cold-path turn-writer

- **Locations:** `web/backend/app/services/turn_writer.py` (new — async/after-stream:
  route each consequence by the "…toward whom?" rule (relational target → edge, else stat),
  reify a `:Consequence` node via `graph_writer.attach_consequence`, append an `:Event`
  node; never blocks the player; best-effort when Neo4j down), `web/backend/app/services/turn_engine.py`
  (enqueue the cold-path job after the stream completes — background task / thread),
  `web/backend/app/services/stats.py` (hot-path stat apply already clamped during validation).
- **Rationale:** Durable consequences off the hot path; Postgres canonical, Neo4j projection.
- **Tests:** `test_turn_writer.py` (a consequence turn writes the expected stat/edge/Event;
  Neo4j-down → no-op, stream unaffected; no relational target → stat only).
- **Action:** `uv run pytest` (affected) + ruff/mypy. Commit:
  `[Turn Loop Runtime] (7/8) Complete: cold-path turn-writer (Consequence + edges/stats + Event append, non-blocking).`

### P8 — Branch choices + stat panel wiring

- **Locations:** `web/backend/app/services/turn_engine.py` (after a line-to-line consistency
  pass seam, emit `branch_choices` when the Director flagged `needsBranch`; stats inform
  which options surface, never gate mechanically), `web/backend/app/services/validator.py`
  (new — parse → validate → **clamp** stat changes to `[min,max]`, keep `reason`; unknown
  stat dropped; repair-loop fallback seam). Frontend: `web/frontend/features/story-player/useScenePlay.ts`
  (branch selection feeds the next turn's `directedAt`/text; stat `state_update` drives the
  Stats panel + tension), `web/frontend/components/feature/TranscriptBeat.tsx` (retire the
  `CheckCard` path; `BranchChoices` carries label+outcome only), `web/frontend/features/story-player/StoryPlayerView.tsx`
  (DirectorRail live stat deltas + clamp/reason display).
- **Rationale:** Closes the interactive loop — choices feed the next turn, stat changes drive
  panels, clamp + reason are visible.
- **Tests:** backend `test_validator_clamp.py` (clamp + reason retained; unknown stat dropped),
  `test_turn_engine_branch.py` (branch emitted on needsBranch); frontend `useScenePlay`
  branch+stat tests, `TranscriptBeat`/panel tests (no check, branch renders, stat updates).
- **Action:** backend `uv run pytest` + frontend `npm test`/`typecheck`/`lint`; **a11y +
  responsive pass** (branch keyboard operability, live stat announcements, viewports). Commit:
  `[Turn Loop Runtime] (8/8 core) Complete: branch choices + stat-panel wiring + validator clamp (no dice).`

> **Stop for review here.** P9–P11 follow after the user reviews P1–P8.

### P9 — Read-time reflection interlude (post-review)

- **Locations:** `web/backend/app/agents/reflection_agent.py` (new — retrospective +
  overridable disposition; branch-keyed when offered), `web/backend/app/services/reflection.py`
  (new — read-time per-character job, write `interior:{session}:{character}` to Redis),
  `web/backend/app/memory/interior.py` (new — get/set interior records),
  `web/backend/app/services/assembler.py` (read interior state into Band-1),
  `web/backend/app/agents/character_turn_agent.py` (consume interior; shorten Step-5 thinking).
- **Action:** `uv run pytest` (affected). Commit `(9/11)`.

### P10 — Multi-party: live queue + cascade + consistency validator (post-review)

- **Locations:** `web/backend/app/services/turn_engine.py` (universal reflection for N>2;
  live speaker queue: score impact → re-rank → cascade disposition refresh, width/strength
  scaled to impact), `web/backend/app/agents/director_agent.py` (mid-turn re-consult),
  `web/backend/app/services/consistency.py` (new — post-sequence line-to-line check;
  in-place regenerate of an offending line, sequence order preserved),
  `web/backend/app/agents/character_turn_agent.py` (bookended prompt under scale).
- **Action:** `uv run pytest` (affected). Commit `(10/11)`.

### P11 — vLLM concurrency hardening (post-review)

- **Locations:** `web/backend/app/services/llm.py` + provider hooks (prefix-cache-aware
  ordering, optional token streaming), `web/backend/app/services/turn_engine.py` (async
  non-blocking per-session; Director concurrent with assembly; off-hot-path batched),
  config (`TURN_MAX_CONCURRENCY`, TTFT SLO knobs), logging (prefix-cache hit-rate).
- **Action:** `uv run pytest` + concurrency smoke. Commit `(11/11)`.

## 4. Deliverables (P1–P8 this session)

| Deliverable | Description | Location |
| --- | --- | --- |
| Event envelope + frames | `internal_thought`; delta frames; `check` dropped | `web/backend/app/events/envelope.py`, `web/backend/app/events/stream.py` |
| Event/seq store | DB-authoritative seq, unique constraint, persist | `web/backend/app/services/events_store.py`, `web/backend/app/models/event.py`, alembic |
| Turn request schema | `TurnRequest` | `web/backend/app/schemas/play.py` |
| Turn engine | POV loop: assemble → generate → validate → stream; cold-path enqueue | `web/backend/app/services/turn_engine.py` |
| Band-1 assembler | buffer + subgraph + stats/guidance + stable prefix + gated RAG | `web/backend/app/services/assembler.py`, `web/backend/app/services/retrieval_gate.py` |
| Character turn agent | think→speak, thin tags, in-voice anchors | `web/backend/app/agents/character_turn_agent.py` |
| Director + Narrator | who's-up (structure-only); interstitials | `web/backend/app/agents/{director_agent,narrator_agent}.py` |
| Validator + turn-writer | clamp/validate; cold-path consequences | `web/backend/app/services/{validator,turn_writer}.py` |
| Redis memory | recent-turn buffer (+ prefetch) | `web/backend/app/memory/{buffer,prefetch}.py` |
| Play route | `POST /play/{scenarioId}/turn` (NDJSON) | `web/backend/app/routes/play.py` |
| Event stream hook | NDJSON consume + delta accumulate + connection state | `web/frontend/hooks/use-event-stream.ts`, `web/frontend/lib/events.ts` |
| Story player wiring | real turn submit, render deltas, branches feed next turn, stat panels | `web/frontend/features/story-player/*`, `web/frontend/components/feature/TranscriptBeat.tsx` |
| Tests | turn/seq/assembler/agents/validator/turn-writer; hook/component | `utils/tests/backend/{api,data,services,agents}/…`, `web/frontend/**/*.test.{ts,tsx}` |
| Docs | api-contract (turn + stream + internal_thought + no-check), data-flow (turn + bands), architecture (one-engine + bands), structure, checklist | `docs/*.md` |
