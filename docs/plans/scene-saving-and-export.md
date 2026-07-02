# Plan — Persistent Scene Saving & Conversation Export

## 1. Introduction

Velora already persists every visible turn event — narration, dialogue, actions, the
player's `user_turn`, `internal_thought` (as a `private_to_user` row), and `state_update` —
to the Postgres `events` table per turn (`services/events_store.persist_story_event`, via the
turn engine's `_Emitter`). What is **missing** for the user's two requests:

1. **The diagnostic trace is never saved.** Graph-write activity and RAG/lore look-ups only
   ever exist as opt-in `TurnTraceFrame`s the `_Tracer` streams and then discards
   (`turn_engine._Tracer` bypasses persistence by design). So a reopened scene can show the
   conversation and thoughts but not *what the graph/RAG did*.
2. **Nothing reloads a scene.** The story player always starts fresh from
   `scene-data.buildScene` (`useScenePlay`); `sessionRef` is captured from the live stream but
   the prior transcript, thoughts, trace, and stats are never fetched back. There is no list /
   history / export endpoint and no save-on-close signal.

The approach: (Phase 1) persist the per-turn diagnostic trace to a new `turn_traces` table and
stamp session recency, so **everything** about a scenario's play-through is durable; (Phase 2)
add read + export endpoints (`sessions` list, full `history`, `close`, `export?format=json|md`);
(Phase 3) resume-on-open + save-on-close in the story player, rehydrating the transcript,
thoughts, trace, and stats by replaying persisted events through the *existing* client reducers;
(Phase 4) an **Export** control in `SceneHeader`, left of `ThemeSwitcher`, offering JSON +
Markdown; (Phase 5) docs, full validation, merge.

Decisions locked with the user: **persist the trace server-side** (not client-only export);
reopening a scenario **resumes its continuous history** and lets play continue forward with
everything intact; export produces **both JSON and Markdown**.

## 2. Gaps & Unanswered Questions

- **Trace storage shape (assumption):** a dedicated `turn_traces` table keyed by
  `(session_id, turn, n)` rather than folding trace into the `events` table. This preserves the
  heavily-tested `(session_id, seq)` monotonic invariant and the deliberate "trace is not a
  story event / not in `story_event_adapter`" separation, while still making it durable and
  reloadable. `turn` = the `user_turn` seq of that turn (`seq0` in `run_turn`); `n` = the
  existing per-turn ordinal.
- **Persist always vs. only when `trace: true` (assumption):** persist the trace **always**
  (best-effort), decoupled from the stream `enabled` flag, so every scene is fully exportable
  after the fact regardless of the request flag. The client already always sends `trace: true`;
  streaming behaviour is unchanged.
- **One continuous session per scenario (assumption):** the user wants to "always go back to
  that scenario and continue forward." Implement as **resume the most recent session** for the
  scenario on open (reload its full history, keep playing on the same `sessionId`); also expose a
  `sessions` list so nothing is hidden. Not building a multi-timeline branch/versioning UI.
- **Export is server-generated (assumption):** because the full record (including past-turn
  graph/RAG trace) lives in Postgres, export is built on the backend from the DB and downloaded,
  so it works identically for a live or a long-closed scene.
- **Save-on-close (assumption):** every turn already persists, so "save on close" is a
  lightweight `close` call (best-effort `navigator.sendBeacon` on unload/unmount) that stamps
  `updated_at` / marks the session closed — no transcript is buffered client-side awaiting flush.
- **Trace `data` payloads are JSON-serialisable** (they already serialise into the NDJSON
  stream), so they round-trip through a `JSONColumn` unchanged.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Persist the diagnostic trace + session recency (backend)

- **Locations:** `web/backend/app/models/turn_trace.py` (new), `web/backend/app/models/__init__.py`,
  `web/backend/app/models/session.py`, `web/backend/app/services/events_store.py` (or a new
  `web/backend/app/services/trace_store.py`), `web/backend/app/services/turn_engine.py`
  (`_Tracer`, `run_turn`), `web/backend/alembic/versions/<new>_scene_saving.py` (chained on head
  `a1b2c3d4e5f6`), tests under `utils/tests/backend/services/` + `utils/tests/backend/data/`.
- **Details:**
  - New `TurnTrace` model: `id` (`tt_` id), `session_id` FK (`play_sessions`, cascade, indexed),
    `scenario_id` FK (cascade, indexed), `turn: int` (the turn's `seq0`), `n: int`, `step: str`,
    `title: str`, `detail: str`, `data: JSONColumn`, `ts: datetime`. Register in `models/__init__`
    (so `Base.metadata.create_all` builds it under the SQLite test profile).
  - `PlaySession`: add `updated_at` (defaults to `created_at`, bumped each turn) and
    `closed_at: datetime | None`.
  - `trace_store.persist_trace(db, *, session_id, scenario_id, turn, frame)` and a
    `touch_session(db, session_id)` helper (bump `updated_at`); best-effort try/except so a trace
    write never breaks a turn.
  - `_Tracer` gains optional `db` / `session_id` / `scenario_id` / `turn`; `emit` **persists the
    frame regardless of `enabled`**, and still yields it only when `enabled`. `run_turn`
    constructs the tracer with those args (`turn=seq0`) and calls `touch_session` at turn end.
- **Rationale:** the trace must be durable and turn-ordered before any endpoint can serve it;
  keeping it in its own table protects the `events` seq invariant.
- **Action:** Run `uv run pytest utils/tests/backend/services utils/tests/backend/data`. Once
  green, commit: `[Scene Saving & Export] (1/5) Complete: persist per-turn diagnostic trace + session recency.`

### Phase 2 — Session history, list, close, and export endpoints (backend)

- **Locations:** `web/backend/app/routes/play.py`, `web/backend/app/schemas/play.py`,
  `web/backend/app/services/events_store.py` / `trace_store.py`,
  `web/backend/app/services/session_export.py` (new — JSON + Markdown rendering), tests under
  `utils/tests/backend/api/test_play_sessions.py`.
- **Details:**
  - `GET /play/{scenarioId}/sessions` → `[{id, createdAt, updatedAt, closedAt, turnCount,
    preview}]` (ordered newest-first; `preview` = first user_turn text).
  - `GET /play/{scenarioId}/sessions/{sessionId}` → `{ session, events, traces }` — **all** rows
    for the session in `seq` / `(turn,n)` order: story events (incl. hidden `internal_thought`
    and `user_turn`) as wire-shaped envelopes, and traces as `TurnTraceFrame`-shaped objects. This
    is the rehydration + export source.
  - `POST /play/{scenarioId}/sessions/{sessionId}/close` → stamp `closed_at` / `updated_at`;
    idempotent; 404 on unknown session.
  - `GET /play/{scenarioId}/sessions/{sessionId}/export?format=json|md` →
    `session_export.render_json` / `render_markdown`, returned with
    `Content-Disposition: attachment` and the right media type. JSON = structured turns (each turn:
    player line → ordered beats with thoughts/actions/dialogue, stat changes, and the turn's trace
    steps incl. graph `commit`/`relationships` + `lore` RAG steps). Markdown = the same, human-readable.
  - Pydantic response schemas in `schemas/play.py`; reuse `crud.get_scenario` for the 404 guard.
- **Rationale:** one read surface (`history`) powers both reload and export; a single
  `session_export` service keeps both formats in sync from the same in-memory turn structure.
- **Action:** Run `uv run pytest utils/tests/backend/api`. Once green, commit:
  `[Scene Saving & Export] (2/5) Complete: session history/list/close/export endpoints.`

### Phase 3 — Resume-on-open + save-on-close (frontend)

- **Locations:** `web/frontend/lib/api.ts`, `web/frontend/lib/events.ts` (+ `lib/types.ts` as
  needed), `web/frontend/features/story-player/turn-stream.ts`,
  `web/frontend/features/story-player/useScenePlay.ts`, co-located tests
  (`turn-stream.test.ts`, `useScenePlay` coverage).
- **Details:**
  - API client: `listPlaySessions`, `getSessionHistory`, `closePlaySession` (via `sendBeacon`
    fallback), and an `exportSessionUrl(scenarioId, sessionId, format)` helper for downloads.
  - `turn-stream.ts`: a `rehydrateFromHistory(events, traces)` reducer that replays persisted
    frames through the **existing** `mergeFrame` / `applyStatUpdate` / `applyStatByChar` /
    `foldTrace`, plus new handling to render a persisted `user_turn` row as a `{kind:"player"}`
    beat (it is not part of the live stream today). Returns `{messages, stats, statsByChar,
    traceTurns}`.
  - `useScenePlay`: on mount, fetch the latest session's history (best-effort); if present,
    seed `messages`/`stats`/`statsByChar`/`traceTurns` from `rehydrateFromHistory` and set
    `sessionRef` so the next turn continues it (fall back to the current seed when none/empty).
    Add a save-on-close effect: `beforeunload` + unmount → `closePlaySession` best-effort.
  - Expose the active `sessionId` from the hook for the Export control (Phase 4).
- **Rationale:** replaying persisted frames through the shipped reducers means reload produces a
  byte-identical transcript/trace to the live one with no second rendering path to maintain.
- **Action:** Run `cd web/frontend && npm test -- turn-stream useScenePlay` + `npm run typecheck`.
  Once green, commit: `[Scene Saving & Export] (3/5) Complete: resume prior scene + save-on-close.`

### Phase 4 — Export control in the scene header (frontend)

- **Locations:** `web/frontend/components/layout/SceneHeader.tsx`,
  `web/frontend/features/story-player/StoryPlayerView.tsx`, a small
  `web/frontend/components/feature/ExportMenu.tsx` (JSON / Markdown), co-located tests
  (`SceneHeader.test.tsx` / `ExportMenu.test.tsx`).
- **Details:**
  - Insert the Export control **immediately before `<ThemeSwitcher/>`** in `SceneHeader`'s
    right-side container (currently line 44). It is a keyboard-operable menu button ("Export")
    offering **Conversation (JSON)** and **Conversation (Markdown)**, matching the existing
    `Inspector` button styling / `CreateMenu` menu pattern.
  - `StoryPlayerView` passes `scenarioId` + the active `sessionId` (from `useScenePlay`) and an
    `onExport(format)` that triggers a download of `exportSessionUrl(...)` (anchor click). Disable
    the control until a `sessionId` exists (no turns yet → nothing to export).
  - a11y: `aria-haspopup`/`aria-expanded`, focusable items, Escape to close, visible focus ring;
    verify contrast + the 320/375/768/1024 header layout (it sits in the existing flex row).
- **Rationale:** places the feature exactly where the user asked and reuses the header's proven
  control styling; server-side export keeps the button a thin trigger.
- **Action:** Run `cd web/frontend && npm test -- SceneHeader ExportMenu` + `npm run typecheck`
  + `npm run lint`, and an accessibility + responsive pass (keyboard, focus, contrast,
  320/375/768/1024). Once green, commit:
  `[Scene Saving & Export] (4/5) Complete: Export control in the scene header.`

### Phase 5 — Docs, full validation, merge

- **Locations:** `docs/api-contract.md`, `docs/data-flow.md`, `docs/architecture.md`,
  `docs/component-map.md`, `docs/structure.md`, `docs/documentation.md`, `docs/checklist.md`.
- **Details:** document the new `turn_traces` table + `PlaySession.updated_at/closed_at`; the
  four new endpoints and their contracts; the trace-is-now-persisted change (update the
  "transport-only" notes to "streamed *and* persisted"); the resume/save-on-close data flow; the
  Export control in the component map; a checklist entry. Update `documentation.md` status.
- **Action:** Run the **full** gate — `uv run pytest` (backend) + `cd web/frontend && npm test`
  + `npm run typecheck` + `npm run lint` + `npm run build`; ruff + mypy on touched backend files.
  Once green, commit: `[Scene Saving & Export] (5/5) Complete: docs + full validation`, then merge
  the feature branch into `main`, resolving any conflicts.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| `TurnTrace` model | Durable per-turn diagnostic trace rows | `web/backend/app/models/turn_trace.py` |
| Session recency cols | `updated_at` / `closed_at` on `PlaySession` | `web/backend/app/models/session.py` |
| Migration | New table + session columns (head `a1b2c3d4e5f6`) | `web/backend/alembic/versions/<new>_scene_saving.py` |
| Trace store | Persist trace + touch session | `web/backend/app/services/trace_store.py` |
| Persisting tracer | `_Tracer` writes each frame, still streams when enabled | `web/backend/app/services/turn_engine.py` |
| Session endpoints | list / history / close | `web/backend/app/routes/play.py`, `web/backend/app/schemas/play.py` |
| Export service | JSON + Markdown record from the DB | `web/backend/app/services/session_export.py` |
| Export endpoint | `GET …/export?format=json\|md` (attachment) | `web/backend/app/routes/play.py` |
| Rehydrate reducer | Replay persisted frames → transcript/trace/stats | `web/frontend/features/story-player/turn-stream.ts` |
| Resume + close | Load latest session on open; save-on-close | `web/frontend/features/story-player/useScenePlay.ts` |
| API client fns | list/history/close/export helpers | `web/frontend/lib/api.ts`, `web/frontend/lib/events.ts` |
| Export control | Menu (JSON/Markdown) left of ThemeSwitcher | `web/frontend/components/feature/ExportMenu.tsx`, `web/frontend/components/layout/SceneHeader.tsx` |
| Backend tests | trace persistence, session/history/close/export | `utils/tests/backend/services/…`, `utils/tests/backend/api/test_play_sessions.py` |
| Frontend tests | rehydration, resume/close, Export control | `web/frontend/features/story-player/turn-stream.test.ts`, `…/SceneHeader.test.tsx`, `…/ExportMenu.test.tsx` |
| Docs | Contract, data-flow, architecture, component-map, structure, checklist | `docs/*.md` |
