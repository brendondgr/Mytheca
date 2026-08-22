# Control Over the Record

> **STATUS: COMPLETE — 12/12 phases, 2026-08-22.** Implemented in commit series
> `09cc82e … 5290c41` on branch `play-experience`. The record below is what actually
> shipped and where it differs from the plan; the phases that follow are kept as the
> specification they were built from.

## What shipped, and why

The scenario stopped having exactly one silently-resumed play-through, and the transcript
stopped being append-only. Concretely, a player can now:

| Do | How it works |
| --- | --- |
| Keep several stories per scene | `PlaythroughTray` over `GET/POST/PATCH/DELETE …/sessions`. The client no longer reads `sessions[0]`. |
| Fork at any beat | `POST …/branch` — copies history through the **end of the containing turn** with fresh ids and the **same seqs**; the source is untouched. |
| Cut back and carry on | `POST …/rewind` — cuts at a **turn boundary**, keeps the pre-cut history as its own play-through (undo is a tray row, not soft-deletion), and hands the player's own line back **with its direction and attachments**. |
| Rewrite any beat, theirs included | `PATCH …/beats/{id}` — and the Redis buffer is rebuilt, so the cast reads what the player reads. |
| Ask for a different line | `POST …/beats/{id}/reroll` — streams into the **same event id and seq**, keeps the previous wording as a take behind a pager. |
| Let the scene run | `continuation: true` with no text — no buffer push, no `turn_beats` seed, **no intent call**. |
| Have their line drafted | `POST …/ghostwrite/stream` — persists **nothing** until they send. |

Two decisions shaped everything else. **Takes live inside the beat's own row**, never as extra
events: a second row needs a `seq`, which would break `UNIQUE (session_id, seq)` or poison the
ordering. And **history mutation goes through one module** (`session_state`), because rewind,
branch, edit and re-roll are the same three operations — cut rows, re-derive, rebuild caches —
and four implementations would drift silently.

## How the engine had to change

`turn_engine.py` was 1,986 lines with a ~800-line `run_turn`. It now defines exactly two things
and calls out to seven modules — `turn_setup` · `beat_runner` · `beat_stream` · `turn_effects` ·
`turn_emit` · `direction_runtime` · `turn_finalize` — acyclic, one-directional, none over 800
lines. That split is what made a single-beat re-run possible at all: `LiveSegment` gained a
**replace mode** (stream into an existing id/seq, update the row instead of inserting), and
`replace` threads down as a per-type mapping.

## Where this deviated from the plan

- **Alembic migrations were required.** The plan said additive-nullable columns needed none
  because the bootstrap reconciler self-heals. `test_alembic.py` enforces Alembic ≡ `create_all`,
  and Alembic is authoritative. Two migrations written.
- **A 12th phase was inserted**: session-scoped stat values (owner decision D-1), ahead of
  `session_state`, because it changes what "roll the stats back" means. With session scope, rewind
  replays surviving `state_update` rows onto the authored baseline — no per-event provenance, and
  correct for rows written before any of this. The `StatPatch.fromValue` scheme the plan was built
  around was not needed.
- **Phases 9 and 10 were swapped** (Continue before re-roll): smaller, and it owns the
  `validate_turn_inputs` relaxation the Steering plan consumes.
- **Scene-image re-roll/delete was NOT built.** Phase 9's title claimed it; only the prose seam
  landed. Recorded in `docs/checklist.md` and handed to `making-it-legible.md` Phase 11.
- **`useScenePlay` was split** into `useSessionRecord` when it passed 800 lines, re-exporting its
  surface unchanged so no other plan needs a rebase.

## Defects found by building it

Each was caught by a test or a live run, not by reading:

1. A blanket underscore-strip made `runaway_chars = runaway_chars(...)` self-referential — 82 tests.
2. `delete_session` relied on an FK cascade SQLite does not enforce, so dev accumulated orphan rows.
3. `rehydrateFromHistory` dropped the event id on player beats, so the player's own line could not
   be targeted — the exact thing the owner asked for.
4. `record_take` read `data.text` *after* the stream, which had already overwritten it — the
   original take was silently lost.
5. A re-roll **re-applied** the beat's consequences: a fresh `state_update` row each time and the
   character's stats drifting further on every re-roll.
6. A re-roll **appended** the accompanying `internal_thought`, stacking a stale thought beside the
   new line it no longer explained.
7. The first stat design gated the *starting* value on `carry_over`, discarding the authored
   starting stats world population writes.

## Validation

1381 backend and 940 frontend tests (from 1253 / 850), typecheck clean, lint 0 errors, frontend
CSS gate passing. Every phase was also exercised against the running app — real Postgres, real
Redis, real generations on the local `skynet` relay — including a two-turn play-through branched
and rewound, an edit whose new wording was confirmed *in the live Redis buffer*, a beat re-rolled
three times with the transcript shape byte-identical, and a ghostwritten line drafted from a
plain-English note.

---


## 1. Introduction

Today a Mytheca scenario has exactly one play-through — `useScenePlay.ts:249` calls
`listPlaySessions()` and silently loads `sessions[0]` — and once a beat has landed nothing can
be done to it. The transcript is an append-only log: no re-roll, no edit, no rewind, no branch,
no way to keep two versions of a scene, and (per `docs/checklist.md`) not even a way to delete
an unwanted scene image. Every affordance the player has points *forward*, at the next turn.
This plan gives the player control over the **story record itself**, and it is the foundation
the other four plans build on: it establishes the session primitives (name / fork / delete),
the history-mutation primitives (truncate, rebuild, reconcile), and the engine seam that can
re-emit **one beat** instead of replaying a whole turn.

The approach works with Mytheca's existing grain rather than against it. Postgres `events` rows
are already canonical and already replay through the *same* reducers the live NDJSON stream uses
(`turn-stream.rehydrateFromHistory`), so every mutation is expressed as "change the rows, then let
the client re-replay". Redis, Neo4j and Qdrant stay best-effort: the buffer is *rebuilt* from the
rows rather than patched, the graph's per-turn `:Event` nodes are pruned by their deterministic
id, and none of it may ever fail an operation. The `(session_id, seq)` unique constraint is left
untouched — alternate takes live **inside one row's `data`**, not in a second row and not in a
variant seq namespace, so one beat stays one position in the transcript no matter how many times
it is re-rolled. Because `web/backend/app/services/turn_engine.py` is 1986 lines with a ~800-line
`run_turn`, the re-run seam cannot simply be bolted on: an early phase splits the engine into
`turn_emit` / `beat_runner` / `turn_setup` so both the turn loop and the single-beat re-run can
call the same code.

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

### Simple gaps — assumption stated, proceeding

**G-1 — Where alternate takes are stored.** *Decision: a `takes` array plus `activeTake` on the
event's own `data`, with `data.text` mirroring the active take.* A second event row would need a
seq (breaking `UNIQUE (session_id, seq)` or the transcript's ordering); a variant seq namespace
would poison `next_seq`, `session_events`, `presence.current_presence` and the export. Keeping
takes inside the row means one beat keeps one position, `data.text` stays the single source of
truth for every existing consumer (buffer, export, rehydrate, moment prompts), and the pager is a
pure client concern. `data` is a `JSONColumn`, so this needs no migration — but pydantic's default
`extra="ignore"` means unknown keys are **silently dropped** by `build_event`, so the fields must
be declared on the envelope payload models and mirrored in `lib/events.ts` in the same phase.

**G-2 — Rewind granularity.** *Decision: rewind cuts at a **turn boundary**, not an arbitrary
beat.* "Rewind to here" on any beat resolves to the `user_turn` row that opened the turn
containing it, and truncates from that row inclusive. This is exactly the owner's description
("moves the conversation up to that point and forgets about what was after that", then the player
says what they want instead), and it keeps `turn_traces` (keyed by the turn's opening seq),
presence, and the stat replay all aligned — a mid-turn cut would leave half a trace describing
beats that no longer exist. Beat-level surgery is still available: re-roll replaces one beat and
edit rewrites one beat.

**G-3 — Undo of a rewind.** *Decision: reuse branching rather than soft-deletion.* Before
truncating, the server forks the pre-cut history into a new `PlaySession` named
`Before rewind · <timestamp>` (`parentSessionId` + `forkSeq` set), then hard-truncates the live
session. Undo is "open that play-through in the tray". This adds no new storage concept, no
`deleted_at` column that every query must then filter, and it makes the undo *discoverable*
instead of a hidden ten-second window. Controlled by a `keepSnapshot` flag defaulting to `true`.

**G-4 — Concurrency (a rewind while a turn is streaming).** *Decision: optimistic
concurrency, not a lock.* Every mutating endpoint takes an `expectedSeq` precondition (the client's
view of the session's highest seq) and returns **409** on mismatch; the UI additionally disables
all beat controls while `scene.sending` is true. A `busy` column would have to be cleared in a
`finally` that a client abort can skip, leaving sessions permanently wedged; a stale-precondition
409 fails safe and needs no state.

**G-5 — What happens to each best-effort substrate on a history mutation.**
- **Redis recent-turn buffer** — `buffer.clear(session_id)` then re-push the surviving prose rows
  in seq order (`user_turn` → `player`/`character` under POV, `narration` → `narrator`,
  `character_prose`/`character_dialogue`/`character_action` → `character`; `internal_thought` is
  never buffered, matching `turn_engine`). No Redis → the rebuild is a no-op and the turn still
  runs, exactly as today.
- **Qdrant / RAG** — *nothing to do.* Verified: nothing on the play path writes to the vector
  store. `rag/indexer` is called only from `services/crud.py` (context documents) and
  `services/storyline_apply.py`. Transcript text is never indexed, so an edited beat has no stale
  embedding to invalidate. This corrects the brief's assumption.
- **Neo4j** — `turn_writer._append_event` writes one `:Event` node per consequence-bearing turn at
  the deterministic id `evt_{session_id}_{turn_seq}`; truncation deletes those nodes for cut turns
  via `graph_writer.remove_node`. Relationship **edges** and `:Consequence` nodes written by cut
  turns are **not** rolled back — the graph is a best-effort accumulator with no per-turn
  provenance index, and inventing one is out of scope. Recorded as a new deferral in
  `docs/checklist.md`.
- **`CharacterStat` rows** — see G-6.

**G-6 — Un-applying stats committed by truncated turns.** `CharacterStat` is *character*-scoped,
not session-scoped, so there is no baseline to fall back to. *Decision: carry the pre-change value
on the event.* `StatPatch` gains `fromValue`, written by `beat_runner.apply_stat_change` from
`stats.get_character_stats` before `set_character_stats`. Re-deriving after any mutation is then:
for each `(characterId, key)` touched by the session, take the last **surviving** `state_update`'s
`value`; if none survives, take the **earliest removed** one's `fromValue`. Legacy rows written
before this phase have no `fromValue` — those keys are left at their current value and the fallback
is recorded as a deferral. Presence needs no equivalent: `presence.current_presence` already
derives from the surviving `character_status_change` rows, so truncation re-derives it for free.

**G-7 — Which beats get controls.** *Decision: every beat in the transcript gets the same control
cluster, with per-kind availability* — narrator/character beats get Re-roll · Edit · Rewind here;
the player's own beats get Edit · Rewind here; scene images get Re-roll (repaint) · Edit caption ·
Delete. `DELETE …/beats/{eventId}` is restricted to `scene_image` rows: deleting a prose beat would
leave a hole in a causal chain that rewind already handles correctly, whereas an image is inert
(nothing in the turn loop reads it back).

**G-8 — Where the Ghostwriter call lives.** *Decision: a new narrow agent,
`agents/ghostwriter_agent.py`, not a reuse of `character_turn_agent.stream_line`.* The character
agent's output contract produces a **tagged emission** (`emission.parse_emission` splits it into
thought/action/dialogue segments) with register-driven samplers and a beat-length allowance — all
of which the ghostwriter must not inherit, because its output goes into a `<textarea>` as one plain
line the player then edits. It reuses `ctx.stable_prefix`, the cast/voice blocks and
`character_turn_agent._transcript`, and adds a ninth `prompt_registry` key (`ghostwriter.line`).
Nothing is persisted until the player presses Send through the ordinary turn path.

**G-9 — Ghostwritten lines and POV.** *Assumption: a ghostwritten line is indistinguishable from a
typed one.* It lands in the composer, the player edits it, and it is sent as ordinary `text` with
whatever `povCharacterId` is active. No flag on the `user_turn` row.

**G-10 — Auto-resume behaviour after the tray exists.** *Assumption: keep resuming the
most-recently-updated play-through by default*, but route it through the same explicit
`openSession(id)` path the tray uses, and show in the tray which one is live. The silent
`sessions[0]` index access is replaced by a named `mostRecent(sessions)` helper so the choice is
visible in the code.

### Complex gaps — human intervention needed

**H-1 — Stat lifecycle across forked play-throughs.** `CharacterStat` is global to a character,
but branching creates two play-throughs of the same scenario that will disagree about that
character's health. This plan reconciles stats to *the session you have open* (`session_state.
reconcile_stats` runs on open, rewind and branch), which is the least surprising behaviour
available without a schema change — but it means opening play-through B silently rewrites values
that play-through A also reads, and any non-play surface reading `GET /characters/{id}/stats`
sees whichever session was opened last. The real fix is session-scoped stat values (a
`session_id` column on `CharacterStat`, or a per-session overlay table), which collides with the
already-open "Stat lifecycle across scenarios" decision in `docs/checklist.md`.
**This is the same question as `docs/plans/depth-for-players.md` §2 complex gap 2** ("What should
stats do between scenarios?", options A–D, that plan recommending **C** = per-stat carry-over with
session-scoped values). Answer them together: option C is exactly the session-scoped model this
gap needs, and Depth's Phase 11 ships its prerequisite (a recoverable `CharacterStat.baseline`).
Until it is answered, this plan reconciles to the open session and Depth records the baseline.
**Human intervention is needed to answer this question.**

**H-2 — Retention of rewind snapshots.** Every rewind forks a snapshot play-through (G-3). A
player who rewinds ten times in a session gets ten extra rows in the tray. Options: keep all and
let the player prune by hand; keep the last N and auto-delete the rest; hide them behind a
"History" disclosure in the tray; or make the snapshot opt-in per rewind. This plan implements
"keep all, marked with a `snapshot` badge and grouped last", which is the safest default but is
probably not the one the owner wants.
**Human intervention is needed to answer this question.**

**H-3 — How many alternate takes to keep, and whether they survive export.** The plan caps takes
at 5 per beat (oldest dropped) and includes only the **active** take in
`GET …/export?format=md`, with all takes in `format=json`. Whether a reader of the Markdown
export should see the roads not taken — and whether takes should count toward the context window
the model reads — is a product call.
**Human intervention is needed to answer this question.**

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — The session record: name, lineage, and the turn's own inputs

- **Locations:**
  - `web/backend/app/models/session.py` — add three **nullable** columns to `PlaySession`:
    `name: str | None`, `parent_session_id: str | None` (self-FK, `ondelete="SET NULL"`),
    `fork_seq: int | None`. All additive-nullable, so the `core/bootstrap._reconcile_additive_columns`
    reconciler self-heals a drifted dev DB and **no Alembic migration is required** (note it in the
    module docstring the way `updated_at` already is).
  - `web/backend/app/services/events_store.py` — `create_session(db, scenario_id, *, name=None,
    parent_session_id=None, fork_seq=None)`; new `rename_session`, `delete_session`;
    `user_turn_stats` changed to take the first **non-empty** player line as `preview` (a
    continuation turn in Phase 9 writes an empty one); `record_user_turn` gains `guidance: str |
    None` and `tagged_doc_ids: list[str]` written onto `data`.
  - `web/backend/app/services/turn_engine.py` — pass `req.guidance` / `req.tagged_doc_ids` through
    to `record_user_turn` (one call site, around line 438).
  - `web/backend/app/schemas/play.py` — `SessionSummary` gains `name: str | None`,
    `parent_session_id: str | None`, `fork_seq: int | None`; new `SessionCreateRequest {name?}` and
    `SessionRenameRequest {name}`.
  - `web/backend/app/routes/play_record.py` — **new module** for every session/beat mutation
    endpoint this plan adds (`play.py` is already 256 lines and would blow past 500). This phase
    adds `POST /play/{scenarioId}/sessions` (start fresh — creates an *empty* session and returns
    its `SessionSummary`; it must not touch the existing one),
    `PATCH /play/{scenarioId}/sessions/{sessionId}` (rename),
    `DELETE /play/{scenarioId}/sessions/{sessionId}` (cascade-deletes `events` + `turn_traces` via
    the existing FK `ondelete=CASCADE`, then `buffer.clear` best-effort).
  - `web/backend/app/main.py` — import `play_record` and add it to the `include_router` tuple.
  - `web/frontend/lib/events.ts` — mirror `name` / `parentSessionId` / `forkSeq` onto
    `SessionSummary`.
  - `web/frontend/lib/api.ts` — `createPlaySession`, `renamePlaySession`, `deletePlaySession`.
  - `docs/api-contract.md` (Sessions rows in *Endpoint Groups*), `docs/data-flow.md`
    (*Scene Persistence, Resume & Export*).
  - Tests: `utils/tests/backend/api/test_play_sessions_crud.py`,
    `utils/tests/backend/services/test_events_store_sessions.py`.
- **Rationale:** Every later phase needs somewhere to put a play-through's identity and lineage,
  and needs "start fresh" to stop meaning "silently continue whatever `sessions[0]` was".
  Persisting `guidance` and `taggedDocIds` on the `user_turn` row is required here and not later,
  because rewind (Phase 6) restores the player's line **with its direction and attachments** into
  the composer, and the turn-scope re-roll (Phase 8) replays the same request. It also closes two
  standing `docs/checklist.md` items ("The scene direction is not persisted", "The persisted player
  beat shows no attachment").
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api
  utils/tests/backend/services` plus `npm run typecheck` in `web/frontend`. Once green, commit
  locally: `[Control Over the Record] (1/12) Complete: PlaySession gained name/lineage columns, session create/rename/delete endpoints, and the turn's guidance + tagged files are persisted.` Do not push or open a PR.*

---

### Phase 2 — The play-through tray in the scene header

- **Locations:**
  - `web/frontend/components/feature/PlaythroughTray.tsx` — **new**. A menu-button popover built on
    the `ExportMenu.tsx` idiom (`aria-haspopup="menu"`, `role="menu"`, close on outside-mousedown
    and Escape, `mytheca-menu` surface). Each row: the play-through's name (or its `preview`, or
    "Untitled play-through"), `turnCount` turns, relative `updatedAt`, a live/current marker, and
    row actions Resume · Rename · Delete. A `+ New play-through` action sits at the foot. Rename is
    an inline `TextField` on the row; Delete asks for confirmation inside the row rather than
    opening a modal, so the tray stays a single focus context.
  - `web/frontend/components/feature/PlaythroughTray.test.tsx` — co-located test.
  - `web/frontend/components/layout/SceneHeader.tsx` — accept `tray?: ReactNode` and render it left
    of `ExportMenu`. **Also delete the hardcoded green dot + "Narrator active"** block (lines
    114–117): it reflects nothing and the header needs the width. This is the cheapest way to buy
    back the ~7px that makes the Inspector button unreachable at 320px (`docs/checklist.md`).
    **This plan owns that delete** — `docs/plans/making-it-legible.md` Phase 7 replaces the slot
    with a real four-state model-health indicator and `docs/plans/reach.md` Phase 4 assumes the
    fake dot is already gone. The 7px is therefore a *relief*, not a fix: the durable fix is
    Reach's header overflow menu, so this phase does not close the checklist bullet (see Phase 11).
  - `web/frontend/features/story-player/useScenePlay.ts` — replace the `sessions[0]` access
    (line ~251) with an explicit `mostRecent(sessions)` helper; extract the resume body into
    `loadSession(sessionId)` (fetch history → `rehydrateFromHistory` → `rememberSession` →
    `setPov` / `setLiveContextTokens` / message + stat + trace state), and reuse it for resume,
    tray switching, branch (Phase 5) and rewind (Phase 6). Expose `sessions`, `refreshSessions`,
    `openSession`, `startNewPlaythrough`, `renamePlaythrough`, `deletePlaythrough`. Starting fresh
    calls `closePlaySession` on the outgoing session first, then `createPlaySession`, then resets
    the transcript to `buildScene(scenario)`'s seed.
  - **The file-length rule applies here too.** `useScenePlay.ts` is **604 lines today** and every
    plan in this program adds to it (this plan alone adds `branchFrom`, `rewindTo`, `editBeat`,
    `rerollBeat`, `continueTurn`, `ghostwrite` and the session-list state). **This plan owns the
    split**, established at this phase and re-checked at the end of every later one: when the file
    would pass 800 lines, extract the play-through/record concerns into a sibling
    `web/frontend/features/story-player/useSessionRecord.ts` that `useScenePlay` composes and
    re-exports, keeping the hook's *public surface* unchanged so the other four plans (and
    `docs/plans/reach.md` Phase 3, which explicitly relies on that stability) need no rebase.
    Run `wc -l web/frontend/features/story-player/useScenePlay.ts` as part of every Action below.
  - `web/frontend/features/story-player/StoryPlayerView.tsx` — pass `<PlaythroughTray …/>` into
    `SceneHeader`.
  - `web/frontend/features/story-player/useScenePlay.test.ts` — extend: a scenario with three
    sessions resumes the most-recent one; `startNewPlaythrough` does not clobber it.
  - `docs/component-map.md` (new component), `docs/routes.md` (the story player's header controls).
- **Rationale:** G1 — one play-through per scenario, chosen for you — closes here, and the tray is
  the surface every later phase reports into (a branch shows up in it; a rewind snapshot shows up
  in it). Doing it immediately after Phase 1 means the app is usefully better after two commits
  rather than after eleven.
- *Action: Run the validation for this phase — `npm test` in `web/frontend` for the touched
  components plus `npm run typecheck && npm run lint`, and an accessibility + responsive pass
  (keyboard-only open/rename/delete, visible focus on every row action, AA contrast on the tray
  surface, 320/375/768/1024 — confirm the header no longer clips the Inspector button). Once green,
  commit locally: `[Control Over the Record] (2/12) Complete: A play-through tray in the scene header lists, resumes, renames, deletes and starts play-throughs.` Do not push or open a PR.*

---

### Phase 3 — Split the turn engine so a single beat can be re-run

- **Locations:** all under `web/backend/app/services/`.
  - `turn_emit.py` — **new**. Move `_Emitter`, `_LiveSegment`, `_Tracer` (lines 118–388) out
    verbatim and rename them `Emitter`, `LiveSegment`, `Tracer`.
  - `beat_runner.py` — **new**. Move `_stream_emission`, `_emit_segment_delta`, `_beat_or_skip`,
    `_generate_speaker`, `_narrator_interstitial`, `_relationship_note`, `_apply_declared_presence`,
    `_apply_presence_change`, `_apply_relationship_change`, `_apply_stat_change`, plus
    `_DEGENERATE_AFTER_CHARS` / `_CHARS_PER_TOKEN` / `_runaway_chars`, renamed without the leading
    underscore where they are now cross-module.
  - `turn_setup.py` — **new**. A `TurnSetup` dataclass (`session`, `ctx`, `pov`, `seq0`, `emitter`,
    `tracer`, `turn_beats`, `intent`, `direction`, `show_reasoning`) and `prepare_turn(db, scenario,
    req)` holding everything `run_turn` does before the beat loop: resolve session, assemble
    context, resolve POV, record the user turn, push the buffer, emit the `turn`/`assemble`/`lore`/
    `files` traces, run `intent_agent.interpret`, resolve the `SceneDirection`. It is a generator
    (it yields trace frames) returning `TurnSetup`.
  - `turn_engine.py` — keeps `validate_turn_inputs`, `run_turn` (now: call `prepare_turn`, the
    opening-narration branch, the beat loop, the finalize tail), `_turn_summary`, `_delivered`,
    `_name_of`, `_direction_lead`, `_plan_still_valid`. Target: **under 800 lines**; if the beat
    loop alone still exceeds it, move the finalize tail (suggestions → cold-path writer →
    reflection → `touch_session`, lines ~1098–1200) into `turn_finalize.py` in this same phase.
  - `utils/tests/backend/services/test_degenerate_beat.py:100` — the one test that imports private
    engine symbols; update its import to `beat_runner`.
  - `docs/architecture.md` + `CLAUDE.md`'s backend table — add the new modules under `services/`.
- **Rationale:** This is a **pure move with no behaviour change**, and the 1110-case suite is its
  gate. It has to happen before Phase 8, because the re-run seam needs `Emitter`, `LiveSegment`,
  `beat_runner.generate_speaker` and `turn_setup.prepare_turn` from outside `run_turn` — importing
  them from a 1986-line module that also owns the loop would either mean a circular import or
  pushing `turn_engine.py` toward 2500 lines, well past the repo's 800-line ceiling.
- *Action: Run the validation for this phase — the **full** `uv run pytest` (this is a refactor;
  a subset proves nothing), plus `wc -l` on each new and touched module to confirm every one is
  under 800 lines. Once green, commit locally: `[Control Over the Record] (3/12) Complete: The turn engine is split into turn_setup, beat_runner and turn_emit, with no behaviour change.` Do not push or open a PR.*

---

### Phase 4 — Session-scoped stat values (owner decision D-1)

- **Locations:**
  - `web/backend/app/models/stat.py` — `StatDefinition` gains `carry_over: bool | None`
    (nullable → the additive reconciler self-heals; read as `False`). **New**
    `SessionCharacterStat(session_id, character_id, key, value)` with
    `UniqueConstraint(session_id, character_id, key)` and `ondelete="CASCADE"` on both FKs.
  - `web/backend/alembic/versions/` — a migration for both (the parity test in
    `utils/tests/backend/data/test_alembic.py` enforces Alembic ≡ `create_all`; Phase 1 learned
    this the hard way).
  - `web/backend/app/services/session_stats.py` — **new**, kept separate from `stats.py` so the
    authoring surface and the play surface do not blur: `resolve(db, session_id, character_id)`
    (session row → carried character value → authored default), `apply(db, session_id,
    character_id, values)`, `baseline(db, character_id)`, `copy(db, source, target)` for branch,
    `clear(db, session_id)` for the rewind replay.
  - **Play-path call sites move to the session scope** — `services/validator.py` (reads the
    current value to apply a delta), `services/turn_effects.py` (applies the change),
    `services/assembler.py` (renders stats into the prompt). Each needs the `session_id`
    threaded to it.
  - **Authoring call sites stay character-global** — `routes/stats.py` and
    `services/world_populate.py` continue to read and write the authored baseline. Say which is
    which at every call site; this is the distinction the whole phase exists to draw.
  - `web/frontend/lib/api.ts` + `features/story-player/useScenePlay.ts` — the play surface reads
    the session's values, not `getCharacterStats`.
  - `docs/checklist.md` — closes **"Stat lifecycle across scenarios"** in *Undesigned decisions*.
  - Tests: `utils/tests/backend/services/test_session_stats.py`.
- **Rationale:** Owner decision **D-1**. `CharacterStat` is global to a character, so two
  play-throughs of one scenario silently share a health value and a rewind can only reconcile to
  whichever session happens to be open. This must land **before** `session_state` (Phase 5),
  because it changes what "roll the stats back" means: with session scope, rewind deletes the
  session's rows and **replays the surviving `state_update` events** from the authored baseline —
  deterministic, no per-event provenance, and correct for rows written before this program. That
  is strictly better than the `StatPatch.fromValue` scheme Phase 5 was originally written around,
  which is why this phase comes first rather than after it.
- *Action: Run the validation for this phase — `uv run pytest` in full (this changes a read path
  every turn uses), plus `npm run typecheck` in `web/frontend`. Once green, commit locally:
  `[Control Over the Record] (4/12) Complete: Stat values are session-scoped, with a per-stat carry_over flag.` Do not push or open a PR.*

---

### Phase 5 — History-mutation primitives (`session_state`)

- **Locations:**
  - `web/backend/app/events/envelope.py` — add `from_value: int | None = None` to `StatPatch`.
  - `web/backend/app/services/beat_runner.py` — `apply_stat_change` reads the character's current
    value via `stats.get_character_stats` **before** `set_character_stats` and carries it as
    `fromValue` on the emitted patch.
  - `web/frontend/lib/events.ts` — mirror `fromValue` on `StatPatch` (same phase — the mirror is
    hand-maintained).
  - `web/backend/app/services/session_state.py` — **new**, the single place any history mutation
    goes through:
    - `rebuild_buffer(db, session_id)` — `buffer.clear`, then re-push surviving rows in seq order
      with the role mapping in G-5. Best-effort; a missing Redis is a silent no-op.
    - `reconcile_stats(db, session_id, cast_ids)` — the G-6 replay: last surviving `state_update`
      per `(characterId, key)`, else the earliest removed one's `fromValue`, else leave alone.
    - `truncate_session(db, session_id, *, after_seq)` — delete `Event` rows with `seq > after_seq`
      **returning the removed rows**, delete `TurnTrace` rows with `turn > after_seq`, then call
      `prune_graph_events`, `reconcile_stats` and `rebuild_buffer`. Returns a
      `TruncationResult(cut_seq, removed_events, removed_traces, removed_stat_keys)`.
    - `prune_graph_events(session_id, removed_turn_seqs)` — `graph_writer.remove_node` for each
      `evt_{session_id}_{turn_seq}`; wrapped so a disabled/unreachable Neo4j is a no-op.
    - `copy_history(db, source_session, target_session, *, through_seq)` — new `Event` rows
      (fresh ids from `new_id("ev")`, **same `seq` values** so ordering and the unique constraint
      both hold within the new session) plus the matching `TurnTrace` rows.
    - `turn_boundary(db, session_id, event_id)` — resolve any event to the `seq` of the `user_turn`
      that opened its turn (G-2), and to the persisted request fields on that row.
    - `latest_seq(db, session_id)` / `require_expected_seq(db, session_id, expected)` — the
      optimistic-concurrency precondition from G-4, raising `APIError(409, "conflict", …)`.
  - `docs/data-flow.md` — a new *History Mutation* subsection under *Scene Persistence*, stating
    what happens to Postgres / Redis / Neo4j / stats and that Qdrant is **not** involved.
  - Tests: `utils/tests/backend/services/test_session_state.py` — truncate removes the right rows
    and no others; presence re-derives from the survivors; stats roll back via `fromValue`; a
    legacy `state_update` with no `fromValue` leaves the value alone; the buffer rebuild is a clean
    no-op without Redis; `copy_history` produces an independent session with identical seqs;
    `require_expected_seq` 409s on a stale value.
- **Rationale:** Rewind, branch, edit and re-roll are four faces of the same three operations. If
  each endpoint re-implements them, they will drift, and the drift will be silent (a stale Redis
  buffer feeds the model a beat the player deleted). Building and testing them once, against a
  suite that runs with none of the optional substrates, also proves the "never let a missing
  service break the operation" requirement directly.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services
  utils/tests/backend/api` and `npm run typecheck` in `web/frontend` for the mirrored `StatPatch`.
  Once green, commit locally: `[Control Over the Record] (5/12) Complete: session_state gives truncation, buffer rebuild, stat replay and history copy one tested home.` Do not push or open a PR.*

---

### Phase 6 — Branch from here

- **Locations:**
  - `web/backend/app/routes/play_record.py` — `POST /play/{scenarioId}/sessions/{sessionId}/branch`.
    Body `BranchRequest { atEventId: str, name?: str, expectedSeq?: int }`. Resolves the fork point
    with `session_state.turn_boundary` (the fork is *after* the chosen beat's turn completes),
    creates a `PlaySession` with `parent_session_id` + `fork_seq`, calls `copy_history`, runs
    `reconcile_stats` + `rebuild_buffer` on the **new** session, and returns its `SessionSummary`.
    The source session is not touched.
  - `web/backend/app/schemas/play.py` — `BranchRequest`.
  - `web/frontend/lib/api.ts` + `lib/events.ts` — `branchPlaySession` and its request type.
  - `web/frontend/components/feature/BeatControls.tsx` — **new**. The per-beat control cluster:
    a row of small icon buttons that is `opacity-0` until the beat is hovered **or contains
    focus** (`group-hover:` + `group-focus-within:`), never `display:none`, so it is always in the
    tab order and always reachable by keyboard. This phase wires only *Branch from here*; later
    phases add Rewind, Edit, Re-roll and Delete to the same component behind capability props.
  - `web/frontend/components/feature/BeatControls.test.tsx` — co-located.
  - `web/frontend/components/feature/TranscriptBeat.tsx` — accept `controls?: ReactNode` and render
    it in the beat's header row (character beats), above the card (narrator), or under the bubble
    (player); `StoryPlayerView.tsx` supplies it per message.
  - `web/frontend/features/story-player/useScenePlay.ts` — `branchFrom(eventId)`: call the endpoint,
    `refreshSessions()`, then `openSession(newId)` so the player lands *in* the branch, and toast
    "Branched — the original is in the tray".
  - `docs/api-contract.md`, `docs/data-flow.md`, `docs/component-map.md`.
  - Tests: `utils/tests/backend/api/test_play_branch.py` (fork copies rows through the cut and no
    further; the parent is byte-identical afterwards; lineage columns are set; a stale
    `expectedSeq` 409s), `web/frontend/components/feature/BeatControls.test.tsx`.
- **Rationale:** Branch is the *non-destructive* half of the same machinery rewind needs, so it is
  built and proved first — and Phase 6 then implements rewind's undo (G-3) by calling straight into
  it, rather than inventing soft-deletion.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api
  utils/tests/backend/services`, `npm test` in `web/frontend` for the touched components, and an
  accessibility + responsive pass (the beat controls must be tab-reachable with visible focus and
  must not overlap prose at 320/375/768/1024). Once green, commit locally:
  `[Control Over the Record] (6/12) Complete: Branch from here forks a play-through at a beat, leaving the original intact.` Do not push or open a PR.*

---

### Phase 7 — Rewind to here

- **Locations:**
  - `web/backend/app/routes/play_record.py` — `POST /play/{scenarioId}/sessions/{sessionId}/rewind`.
    Body `RewindRequest { atEventId: str, keepSnapshot: bool = true, expectedSeq?: int }`. Order of
    operations: `require_expected_seq` → resolve `turn_boundary` → when `keepSnapshot`, branch the
    pre-cut history into `Before rewind · <ts>` (Phase 5's `copy_history`) → `truncate_session(after_seq
    = cut_seq - 1)` so the opening `user_turn` row goes too → return
    `RewindResponse { session, cutSeq, removedEvents, removedTraces, snapshotSessionId,
    restoredTurn }`, where `restoredTurn` is the deleted player line with its `pov`, `guidance` and
    `taggedDocIds` (persisted in Phase 1).
  - `web/backend/app/schemas/play.py` — `RewindRequest`, `RewindResponse`, `RestoredTurn`.
  - `web/frontend/lib/api.ts` + `lib/events.ts` — `rewindPlaySession` and the mirrored types.
  - `web/frontend/features/story-player/useScenePlay.ts` — `rewindTo(eventId)`: guard on
    `sending`; call the endpoint; truncate `messages` locally to the returned `cutSeq` (or simply
    re-run `loadSession` — prefer the re-load, since it is the one path already proven to produce a
    faithful transcript); write `restoredTurn.text` into `composer`, `restoredTurn.guidance` into
    `guidance`, restore `pov`; focus the composer. **This is the "natural prompt" the owner asked
    for**: the player's own words come back, editable, and the scene continues from there.
  - `web/frontend/components/feature/RewindNotice.tsx` — **new**. A quiet centred rule at the foot
    of the truncated transcript ("Rewound to here — say what happens instead", plus an *Undo* link
    that opens the snapshot play-through), rendered as a `role="status"` live region so the change
    is announced rather than silently swallowing half the page.
  - `web/frontend/components/feature/BeatControls.tsx` — add *Rewind to here*, with a confirm step
    inside the control (it removes content) naming how many beats will go.
  - `docs/api-contract.md`, `docs/data-flow.md`, `docs/component-map.md`, `docs/checklist.md`.
  - Tests: `utils/tests/backend/api/test_play_rewind.py` — the cut removes the whole containing
    turn and everything after; the snapshot session holds the removed history; presence re-derives;
    stats roll back; traces for cut turns are gone; a rewind with no snapshot leaves no extra
    session; `expectedSeq` mismatch 409s; a rewind on a scenario with no Redis/Neo4j/Qdrant
    succeeds. Frontend: `web/frontend/features/story-player/useScenePlay.test.ts` — a rewind
    restores the player's line and its direction into the composer.
- **Rationale:** The single most important item in the plan, and it is deliberately last among the
  destructive operations because it consumes every primitive built so far — truncate, stat replay,
  buffer rebuild, graph prune, branch-as-undo, and the persisted turn inputs that make the restored
  prompt possible. The turn-boundary rule (G-2) is what makes it correct rather than merely
  plausible.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api
  utils/tests/backend/services`, `npm test` in `web/frontend`, and an accessibility + responsive
  pass (confirm the rewind confirmation is keyboard-operable, the notice is announced by a screen
  reader, and focus lands in the composer afterwards; 320/375/768/1024). Once green, commit
  locally: `[Control Over the Record] (7/12) Complete: Rewind to here truncates the session at a turn boundary, snapshots the old history, and hands the player's line back to the composer.` Do not push or open a PR.*

---

### Phase 8 — Edit a beat in place

- **Locations:**
  - `web/backend/app/routes/play_record.py` — `PATCH /play/{scenarioId}/sessions/{sessionId}/beats/{eventId}`.
    Body `BeatEditRequest { text: str, caption?: str, expectedSeq?: int }`. Allowed on `narration`,
    `character_prose`, `character_dialogue`, `character_action`, `user_turn`, and (for `caption`
    only) `scene_image`. Writes `data.text` (and the active entry of `data.takes` when Phase 8's
    field exists), then `session_state.rebuild_buffer`. Returns the row as a `PersistedEvent`.
    Editing a `user_turn` is explicitly permitted for **any** player line, not just the last: the
    row is rewritten and the conversation continues from wherever the player then sends, which is
    what "continuing from the edited point" means once rewind exists as the separate tool for
    discarding what followed.
  - `web/backend/app/services/session_state.py` — `edit_beat(db, session_id, event_id, text)`
    (validation of the type whitelist + the write + the rebuild in one tested place).
  - `web/frontend/components/feature/BeatEditor.tsx` — **new**. An inline editor that replaces the
    beat's prose with an auto-growing `<textarea>` (the `Composer` resize idiom), Save / Cancel,
    Escape cancels, ⌘/Ctrl+Enter saves. It is a `<form>` with a labelled field, not a
    `contenteditable`.
  - `web/frontend/components/feature/BeatEditor.test.tsx` — co-located.
  - `web/frontend/components/feature/BeatControls.tsx` — add *Edit*.
  - `web/frontend/features/story-player/useScenePlay.ts` — `editBeat(eventId, text)`: optimistic
    text swap in `messages`, PATCH, revert + toast on failure.
  - `web/frontend/features/story-player/turn-stream.ts` — a `replaceBeatText(messages, eventId,
    text)` reducer beside the existing `mergeFrame`, so live, rehydrated and edited transcripts all
    move through the same module.
  - `docs/api-contract.md`, `docs/data-flow.md`, `docs/component-map.md`.
  - Tests: `utils/tests/backend/api/test_play_beat_edit.py` (an edited row's text is what
    `session_events` and the export return; a disallowed type 422s; the buffer is rebuilt),
    `web/frontend/features/story-player/turn-stream.test.ts` (the new reducer).
- **Rationale:** Edit is the cheapest of the four beat operations and the one that most needs the
  buffer rebuild to exist — without it the model keeps reading the *old* wording out of Redis while
  the player reads the new one, which is exactly the class of silent divergence Phase 4 was built
  to prevent.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api
  utils/tests/backend/services`, `npm test` in `web/frontend`, plus an accessibility + responsive
  pass (the editor is a labelled form field, Escape/Save are keyboard-reachable, focus returns to
  the beat's control cluster on close; 320/375/768/1024). Once green, commit locally:
  `[Control Over the Record] (8/12) Complete: Any beat — including the player's own lines — can be edited in place, and the buffer follows.` Do not push or open a PR.*

---

### Phase 9 — Re-roll a beat, keep both takes, and give scene images the same controls

- **Locations:**
  - `web/backend/app/events/envelope.py` — `BeatTake { id, text, ts }`, `ImageTake { id, url,
    prompt, negative, caption, ts }`, and a `TakesData` mixin carrying `takes: list[BeatTake] = []`
    + `active_take: int = 0`, inherited by `NarrationData`, `CharacterProseData`,
    `CharacterDialogueData`; `SceneImageData` gets `takes: list[ImageTake]` + `active_take`.
    Defaults are empty, so every existing row, delta frame and test is unchanged (G-1).
  - `web/frontend/lib/events.ts` — mirror all of the above **in this phase** (the contract mirror
    is hand-maintained; `web/shared/contracts/` stays empty).
  - `web/backend/app/events/stream.py` — `BeatRerollFrame { type: "beat_reroll", eventId, take }`,
    a transport frame (not a persisted story event) telling the client to **clear** that message's
    text before the deltas that follow. The deltas themselves are ordinary story-event frames
    re-emitting the same `id` + `seq`, so `turn-stream.mergeDelta` accumulates them with no change.
  - `web/backend/app/services/beat_rerun.py` — **new**, the engine seam. `rerun_beat(db, scenario,
    session, event_row)`:
    1. `turn_setup.prepare_turn` is **not** re-run (it would record a second `user_turn`); instead a
       new `turn_setup.context_for_replay(db, scenario, session, through_seq=row.seq - 1)` rebuilds
       the `TurnContext` and the `turn_beats` list from the persisted rows of the containing turn,
       stopping *before* the target beat — so the re-run sees exactly the context the original saw.
    2. A `turn_emit.LiveSegment` is opened in **replace mode**: it is constructed with the target
       row's existing `id` and `seq` rather than claiming new ones, so the re-take streams into the
       same transcript position and `close()` updates the existing row instead of inserting.
    3. For a character beat it calls `beat_runner.generate_speaker` with the beat's original
       speaker, register and stakes (read back from the turn's persisted `speaker` trace step); for
       a narrator beat, `beat_runner.narrator_interstitial`.
    4. On completion it appends the new text to `data.takes` (capped at 5, oldest dropped), sets
       `active_take` to the new index, mirrors it into `data.text`, and calls
       `session_state.rebuild_buffer`.
    - `rerun_turn(db, scenario, session, event_row)` is the turn-scope variant the owner asked for:
      `turn_boundary` → `truncate_session` → replay the persisted request through
      `turn_engine.run_turn`. It is the composition of Phase 6 and the existing loop, not new
      machinery.
  - `web/backend/app/services/scene_moment.py` — `regenerate_moment(db, ctx, event_row)`: the same
    prompt+render pipeline, but appending an `ImageTake` to the existing `scene_image` row instead
    of persisting a new event.
  - `web/backend/app/routes/play_record.py` —
    `POST …/sessions/{sessionId}/beats/{eventId}/reroll` (NDJSON; body `{ scope: "beat" | "turn",
    expectedSeq? }`; `scene_image` rows route to `regenerate_moment` and reuse the existing
    `moment_stage` frames), `PATCH …/beats/{eventId}/take` (body `{ take: int }` — flip the pager;
    sets `activeTake` + `data.text`, rebuilds the buffer, returns the `PersistedEvent`), and
    `DELETE …/beats/{eventId}` (**`scene_image` only**, per G-7; removes the row and best-effort
    unlinks the WebP through `services/media_cleanup`).
  - `web/frontend/features/story-player/scene-data.ts` — `SceneMessage` gains
    `takes?: { count: number; active: number }`.
  - `web/frontend/features/story-player/turn-stream.ts` — read `takes`/`activeTake` off event data
    in `mergeFrame`; handle `beat_reroll` by clearing the target message's `text`/`thought`/
    `action`.
  - `web/frontend/components/feature/BeatTakePager.tsx` — **new**. The "1 / 2" pager: previous /
    next buttons with `aria-label`s naming the take, an `aria-live="polite"` count, and the flip
    calling `PATCH …/take`.
  - `web/frontend/components/feature/BeatTakePager.test.tsx`, and additions to
    `BeatControls.test.tsx` for Re-roll and Delete.
  - `web/frontend/components/feature/BeatControls.tsx` — add *Re-roll* (with the scope choice at a
    turn boundary) and *Delete* (images only).
  - `docs/api-contract.md` (three endpoints + the `takes`/`activeTake` fields on four event types +
    the `beat_reroll` transport frame), `docs/data-flow.md`, `docs/component-map.md`,
    `docs/checklist.md` (closes "Scene images cannot be regenerated or deleted from the
    transcript").
  - Tests: `utils/tests/backend/api/test_play_beat_reroll.py` (a re-roll keeps the row's id and
    seq, appends a take, leaves the transcript length unchanged; the take cap drops the oldest;
    `scope: "turn"` truncates and replays; a `scene_image` re-roll appends an `ImageTake`),
    `utils/tests/backend/services/test_beat_rerun.py` (replay context stops before the target beat),
    `utils/tests/backend/api/test_play_beat_delete.py` (only `scene_image` deletable).
- **Rationale:** This is the phase the brief calls "the real cost", and it is fourth-from-last on
  purpose: it needs the engine split (Phase 3) to reach `LiveSegment` and `generate_speaker`, the
  buffer rebuild (Phase 4) so a re-take does not leave the old wording in Redis, and rewind
  (Phase 6) so the turn-scope variant is a two-line composition rather than a second truncation
  implementation. Storing takes inside the row is what keeps `UNIQUE (session_id, seq)` and the
  whole reload-is-replay property intact.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api
  utils/tests/backend/services`, `npm test` in `web/frontend`, `npm run typecheck && npm run lint`,
  and an accessibility + responsive pass (the pager announces its position, Re-roll's scope choice
  is keyboard-operable, the image controls do not overlap the picture at 320/375/768/1024). Once
  green, commit locally: `[Control Over the Record] (9/12) Complete: A beat can be re-rolled in place, both takes are kept behind a pager, and scene images gained re-roll and delete.` Do not push or open a PR.*

---

### Phase 10 — Continue (and the shared no-text-turn relaxation)

- **Locations:**
  - `web/backend/app/schemas/play.py` — `TurnRequest` gains `continuation: bool = False` and its
    docstring gains the new rule.
  - `web/backend/app/services/turn_engine.py` — `validate_turn_inputs` (line 390) stops requiring
    `text` outright: the turn is valid when **any** of `text`, `guidance`, `outcome` or
    `continuation` is present, and 400s with "Say something, direct the scene, or press Continue."
    otherwise. **This plan owns this change and states the whole rule once.** `outcome` is
    included here even though this plan never sends it, because
    `docs/plans/steering-the-scene.md` Phase 3 needs `guidance` and Phase 11 needs `outcome`;
    landing both conditions in one edit means Steering *consumes* the relaxation and never
    re-opens this function. Test all four accept-paths and the wholly-empty 400 here.
  - `web/backend/app/services/turn_setup.py` — with empty `text`: seed `turn_beats` as `[]`
    (no player line to carry), **skip the `buffer.push_turn` call** (pushing `""` into the
    recent-turn buffer would poison the transcript window with a blank player beat), **skip the
    `intent_agent.interpret` call entirely** and construct a neutral freeform intent (this is also
    a saved LLM call), and still write the `user_turn` row — with `data.continuation = true` — so
    the turn keeps its trace grouping and its place in the export. **This plan owns the empty-text
    handling in `turn_setup`**; `docs/plans/steering-the-scene.md` Phase 3 extends the same branch
    to a `guidance`-only turn (falling the `turn` trace's `detail` back to the direction text) and
    must not reimplement it.
  - `web/backend/app/services/events_store.py` — `user_turn_stats` already ignores empty previews
    after Phase 1; assert it here with a test rather than assuming.
  - `web/frontend/components/feature/TranscriptFootBar.tsx` — **new**. Composes the existing
    `CreateImageBar` and a *Continue* button in one row at the foot of the transcript, so the two
    between-turn actions read as one cluster; `CreateImageBar` itself is untouched (its tests stay
    valid). `StoryPlayerView.tsx` swaps its `CreateImageBar` block for this.
  - `web/frontend/features/story-player/useScenePlay.ts` — `continueTurn()`: the same `stream.run`
    path as `submit` with `text: ""`, `continuation: true`, and no optimistic bubble.
  - `web/frontend/lib/events.ts` — `continuation?: boolean` on `TurnRequestBody`.
  - `docs/api-contract.md` (the Play row's body shape + the new 400 rule), `docs/data-flow.md`,
    `docs/checklist.md` (closes "A guidance-only turn cannot be sent" on the backend side).
  - Tests: `utils/tests/backend/api/test_play_turn_continuation.py` (a text-less continuation turn
    runs and emits beats; a wholly empty request still 400s; the intent agent is not called;
    `turnCount`/`preview` behave), `web/frontend/components/feature/TranscriptFootBar.test.tsx`.
- **Rationale:** "Continue" is one button, but the backend relaxation underneath it is shared with
  the Steering plan's direction-only turn — so it is stated here, once, with the ownership written
  down. Doing it after the beat operations means the new turn path inherits an engine that is
  already split and already tested.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api
  utils/tests/backend/services`, `npm test` in `web/frontend`, and an accessibility + responsive
  pass on the transcript foot bar (keyboard order Continue → Create image, visible focus, AA
  contrast, 320/375/768/1024). Once green, commit locally:
  `[Control Over the Record] (10/12) Complete: A turn can run with no player line, and Continue sits at the foot of the transcript.` Do not push or open a PR.*

---

### Phase 11 — Ghostwriter

- **Locations:**
  - `web/backend/app/agents/ghostwriter_agent.py` — **new**. `stream_line(db, ctx, *, intent, pov,
    mode)` where `mode ∈ {"character", "narrator"}`. Builds a system message from
    `ctx.stable_prefix` plus a new output contract ("write the line itself, nothing else: no
    labels, no tags, no stage directions unless the player asked for them"), and a user message
    from the POV character's identity/voice block, `character_turn_agent._transcript(ctx, [])`, and
    the player's stated intent. Streams `llm.StreamDelta`s and returns the finished text. Best-
    effort: an unconfigured endpoint raises `APIError` before the stream opens.
  - `web/backend/app/agents/prompt_registry.py` — register `ghostwriter.line` as a ninth
    overridable key (Options → Prompts picks it up automatically).
  - `web/backend/app/events/stream.py` — `GhostwriteFrame { type: "ghostwrite", text, done }`,
    incremental like every other delta in this codebase.
  - `web/backend/app/routes/play_record.py` — `POST /play/{scenarioId}/ghostwrite/stream`
    (NDJSON; body `{ sessionId, intent, povCharacterId?, mode }`). **Nothing is persisted** — no
    event row, no trace, no buffer push. Pre-flight 404/400 as everywhere else.
  - `web/backend/app/schemas/play.py` — `GhostwriteRequest`.
  - `web/frontend/lib/api.ts` + `lib/events.ts` — `postGhostwrite` + `GhostwriteFrame`.
  - `web/frontend/components/feature/GhostwriteButton.tsx` — **new**. Sits in the composer's
    controls row left of `PovSelect`: disabled until the message box has text (the *intent* is the
    input), shows a `TypingDots` state while streaming, and offers *Undo* to restore the pre-draft
    text. The drafted line lands in the same `<textarea>` the player types into, so review and edit
    are the ordinary editing affordances and require nothing new.
  - `web/frontend/components/feature/GhostwriteButton.test.tsx` — co-located.
  - `web/frontend/components/feature/Composer.tsx` — accept `onGhostwrite`, `ghostwriting`,
    `canGhostwrite`; render the button when the handler is supplied (so every existing render is
    unchanged).
  - `web/frontend/features/story-player/useScenePlay.ts` — `ghostwrite()`: keep the pre-draft text
    in a ref, run its **own** `useEventStream` (independent of the turn stream, like
    `momentStream`), append deltas into `composer`, expose `undoGhostwrite()`.
  - `docs/api-contract.md`, `docs/data-flow.md`, `docs/component-map.md`, and the prompt-key count
    in `CLAUDE.md` + `docs/architecture.md` (8 → 9).
  - Tests: `utils/tests/backend/agents/test_ghostwriter_agent.py` (the prompt carries the POV
    character's voice and the player's intent; the output contract forbids tags; an unconfigured
    LLM raises rather than returning junk), `utils/tests/backend/api/test_play_ghostwrite.py`
    (streams deltas; writes **no** rows to `events` or `turn_traces`).
- **Rationale:** The owner's own addition, and deliberately last among the features: it is the only
  one that touches neither the record nor the engine, so it can be added without risk once
  everything else is stable. Keeping it entirely out of the turn record until Send is what makes it
  safe — a ghostwritten line the player rejects leaves no trace anywhere.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/agents
  utils/tests/backend/api`, `npm test` in `web/frontend`, and an accessibility + responsive pass
  (the button has an accessible name, its streaming state is announced, the textarea keeps focus
  and the caret is not stolen mid-draft; 320/375/768/1024). Once green, commit locally:
  `[Control Over the Record] (11/12) Complete: The Ghostwriter drafts a POV or narrator line from the player's intent, straight into the composer.` Do not push or open a PR.*

---

### Phase 12 — One consistent set of beat affordances, the mobile floor, and the docs sweep

- **Locations:**
  - `web/frontend/components/feature/BeatControls.tsx` — final pass: every transcript beat kind
    (narrator, character, player, player-as-character, scene image, choices) either declares its
    supported actions or explicitly declares none, so there is no beat in the transcript whose
    affordances are an accident. Controls collapse into a single ⋯ menu below `sm`, where a row of
    five icon buttons cannot meet the 44px touch floor.
  - `web/frontend/components/feature/TranscriptBeat.tsx` — render the tagged-file chips on a
    persisted player beat from the `taggedDocIds` stored in Phase 1, closing the last half of the
    `@`-tagging follow-up in `docs/checklist.md`.
  - `web/frontend/components/feature/PlaythroughTray.tsx` — snapshot play-throughs (G-3) get a
    `snapshot` badge and sort last; the tray becomes a full-height sheet below `sm`.
  - `web/frontend/components/feature/responsive-floor.test.ts` — extend the existing floor test to
    cover the new controls at 320px.
  - `web/frontend/components/feature/TranscriptAnnouncer.tsx` — confirm a mutation (rewind, edit,
    take flip, delete) is announced once and does not re-announce the whole transcript.
  - Docs, reconciled in this phase because this is where the feature set stops moving:
    `docs/api-contract.md` (every endpoint and event-shape change above, in the *Endpoint Groups*
    table and the *NDJSON Event Stream* section), `docs/data-flow.md` (the *History Mutation*
    subsection + the rewind/branch/re-roll/ghostwrite flows), `docs/component-map.md` (six new
    components), `docs/routes.md` (the story player's new header and beat controls),
    `docs/architecture.md` + `CLAUDE.md` (the new `services/` modules, the ninth prompt key),
    `docs/design-system.md` (the beat-control reveal pattern and the take pager).
  - `docs/checklist.md` — **remove** the now-closed items: "The scene direction is not persisted",
    "A guidance-only turn cannot be sent" (backend half; note Steering owns the composer restore),
    "Scene images cannot be regenerated or deleted from the transcript", "The persisted player beat
    shows no attachment". **Do not remove the 320px scene-header clipping line**: Phase 2 frees
    ~7px by deleting the dead "Narrator active" block, but `docs/plans/making-it-legible.md`
    Phase 7 spends it again on a real four-state model-health indicator and this plan's own
    `PlaythroughTray` adds a control. Narrow the bullet to record what Phase 2 reclaimed and name
    `docs/plans/reach.md` Phase 4 (the header overflow menu) as the owner of the durable fix and
    of the bullet's removal. **Add** the new deferrals: relationship edges from truncated turns are
    not rolled back; legacy `state_update` rows have no `fromValue` so a rewind past them cannot
    restore the stat; takes are capped at 5 and older takes are dropped; branch does not copy Neo4j
    `:Event` nodes; there is no cross-client lock, only the `expectedSeq` precondition; and the two
    open product questions H-1 (session-scoped stats) and H-2 (snapshot retention).
- **Rationale:** The brief's requirement is that the transcript ends with **one** consistent set of
  affordances rather than five features that each grew their own. This phase is where that is
  actually checked, where the mobile floor is met for controls introduced across six phases, and
  where the documentation is reconciled instead of accumulating per-phase prose — the failure mode
  `global-project-rules` calls out by name.
- *Action: Run the validation for this phase — the **full** `uv run pytest` and the full `npm test`
  in `web/frontend`, plus `npm run typecheck && npm run lint`, `node utils/scripts/check_frontend_css.mjs`,
  and a complete accessibility + responsive pass over the story player (keyboard-only: open the
  tray, switch play-throughs, re-roll a beat, flip a take, edit a beat, rewind, continue; visible
  focus throughout; AA contrast; live-region announcements; 320/375/768/1024). Once green, commit
  locally: `[Control Over the Record] (12/12) Complete: Every transcript beat carries one consistent control set, the controls meet the mobile floor, and the docs and checklist are reconciled.` Do not push or open a PR.*

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Session lineage columns | `name`, `parentSessionId`, `forkSeq` — all additive-nullable, no migration | `web/backend/app/models/session.py` |
| Session store helpers | Create-with-lineage, rename, delete, non-empty preview, persisted turn inputs | `web/backend/app/services/events_store.py` |
| Session + beat mutation routes | Create/rename/delete session, branch, rewind, edit beat, re-roll, take flip, delete image, ghostwrite | `web/backend/app/routes/play_record.py` |
| Router registration | Mount the new module under `/api` | `web/backend/app/main.py` |
| Turn-engine split | `Emitter`/`LiveSegment`/`Tracer`, the beat helpers, and the pre-loop setup extracted | `web/backend/app/services/turn_emit.py`, `beat_runner.py`, `turn_setup.py` |
| History-mutation primitives | Truncate, buffer rebuild, stat replay, graph prune, history copy, turn-boundary resolve, `expectedSeq` guard | `web/backend/app/services/session_state.py` |
| Single-beat re-run seam | Re-emit one beat into its existing id/seq; turn-scope variant | `web/backend/app/services/beat_rerun.py` |
| Scene-image regeneration | Append an `ImageTake` to an existing `scene_image` row | `web/backend/app/services/scene_moment.py` |
| Envelope growth | `BeatTake`/`ImageTake`, `takes` + `activeTake` on four payloads, `fromValue` on `StatPatch` | `web/backend/app/events/envelope.py` |
| Transport frames | `BeatRerollFrame`, `GhostwriteFrame` | `web/backend/app/events/stream.py` |
| No-text-turn relaxation | `continuation` on `TurnRequest`; `validate_turn_inputs` accepts text **or** guidance **or** continuation | `web/backend/app/schemas/play.py`, `web/backend/app/services/turn_engine.py` |
| Ghostwriter agent | POV/narrator line from the player's intent; ninth prompt-registry key | `web/backend/app/agents/ghostwriter_agent.py`, `agents/prompt_registry.py` |
| TS contract mirror | Session lineage, takes, `fromValue`, `continuation`, the two new frames | `web/frontend/lib/events.ts` |
| API client | Session CRUD, branch, rewind, beat edit/re-roll/take/delete, ghostwrite | `web/frontend/lib/api.ts` |
| Play-through tray | Header popover: list, resume, rename, delete, start fresh, snapshots | `web/frontend/components/feature/PlaythroughTray.tsx` |
| Beat control cluster | Re-roll · Edit · Rewind here · Branch here · Delete, per-kind, keyboard-reachable | `web/frontend/components/feature/BeatControls.tsx` |
| Take pager | The "1 / 2" flip between alternate takes | `web/frontend/components/feature/BeatTakePager.tsx` |
| Inline beat editor | Labelled textarea form with Save/Cancel over a beat's prose | `web/frontend/components/feature/BeatEditor.tsx` |
| Rewind notice | Announced foot-of-transcript marker with the undo link | `web/frontend/components/feature/RewindNotice.tsx` |
| Transcript foot bar | Continue + Create image as one cluster | `web/frontend/components/feature/TranscriptFootBar.tsx` |
| Ghostwrite control | Composer button, streaming state, undo | `web/frontend/components/feature/GhostwriteButton.tsx` |
| Play hook rework | `loadSession`/`openSession`, session list state, `branchFrom`, `rewindTo`, `editBeat`, `rerollBeat`, `continueTurn`, `ghostwrite`; no more `sessions[0]` | `web/frontend/features/story-player/useScenePlay.ts` |
| Reducer additions | `takes` on `SceneMessage`, `beat_reroll` clearing, `replaceBeatText` | `web/frontend/features/story-player/turn-stream.ts`, `scene-data.ts` |
| Backend tests — sessions | Session CRUD + lineage + preview behaviour | `utils/tests/backend/api/test_play_sessions_crud.py`, `utils/tests/backend/services/test_events_store_sessions.py` |
| Backend tests — primitives | Truncate, stat replay incl. the legacy fallback, buffer rebuild without Redis, history copy, `expectedSeq` 409 | `utils/tests/backend/services/test_session_state.py` |
| Backend tests — branch | Fork copies through the cut; the parent is untouched | `utils/tests/backend/api/test_play_branch.py` |
| Backend tests — rewind | Turn-boundary cut, snapshot, presence/stat re-derivation, trace pruning, degraded substrates | `utils/tests/backend/api/test_play_rewind.py` |
| Backend tests — edit | Edited text is authoritative for reload + export; type whitelist | `utils/tests/backend/api/test_play_beat_edit.py` |
| Backend tests — re-roll | Same id/seq, takes appended and capped, turn scope, image takes | `utils/tests/backend/api/test_play_beat_reroll.py`, `utils/tests/backend/services/test_beat_rerun.py` |
| Backend tests — image delete | Only `scene_image` rows are deletable | `utils/tests/backend/api/test_play_beat_delete.py` |
| Backend tests — continuation | Text-less turn runs; empty request still 400s; intent call skipped | `utils/tests/backend/api/test_play_turn_continuation.py` |
| Backend tests — ghostwriter | Prompt shape and the no-persistence guarantee | `utils/tests/backend/agents/test_ghostwriter_agent.py`, `utils/tests/backend/api/test_play_ghostwrite.py` |
| Frontend tests (co-located) | Tray, beat controls, pager, editor, foot bar, ghostwrite button, hook and reducer changes | `web/frontend/components/feature/{PlaythroughTray,BeatControls,BeatTakePager,BeatEditor,TranscriptFootBar,GhostwriteButton}.test.tsx`, `web/frontend/features/story-player/{useScenePlay,turn-stream}.test.*` |
| Responsive floor test | The new controls at the 320px floor | `web/frontend/components/feature/responsive-floor.test.ts` |
| Documentation | Endpoints + event shapes, history-mutation flow, components, routes, architecture, design system | `docs/api-contract.md`, `docs/data-flow.md`, `docs/component-map.md`, `docs/routes.md`, `docs/architecture.md`, `docs/design-system.md`, `CLAUDE.md` |
| Checklist reconciliation | Four closed items removed; six deferrals and two product questions added | `docs/checklist.md` |
