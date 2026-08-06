# Scene Presence & Director Actions — plan

Give the turn engine a first-class notion of **who is present in the scene** and a
reusable **scene-action bus** so the director/orchestration can *manipulate* the scene
(remove a character on death or departure, bring one back) rather than only choosing the
next speaker. Fixes the reported defect: a character who has died or left keeps being
picked to talk, because the planner selects from the whole static cast with no concept of
presence.

## Problem

- `Scenario.cast_ids` is the only roster and it is **static** — there is no runtime
  presence/status per character.
- `planner_agent.next_beat` picks a speaker from the **full** `ctx.cast` every beat; a
  dead/departed character is never excluded.
- A health stat reaching `0` is "incapacitated" in guidance prose only — nothing
  mechanical stops selection.
- There is no event, no store, and no UI for a character entering/leaving/dying.

## Design decisions (settled with the user)

- **Control model — auto + undo.** Auto-detection removes characters, but every transition
  is a visible, reversible action (undo toast + a manual per-character control in the cast
  rail). The engine acts; the player can always override.
- **General scene-action bus** (not a one-off removal): one validated status-change verb
  now carries `exit`/re-entry; `end_scene`/`move_scene` slot in later without new plumbing.
- **Distinct lethality**, five runtime statuses:

  | status | body in scene? | selectable? | reversible? |
  | --- | --- | --- | --- |
  | `present` | yes | **yes** | — |
  | `unconscious` | yes (dormant) | no | yes (revive) |
  | `departed` | yes (soul gone, body remains) | no | yes (soul returns) |
  | `left` | no (walked out of the location) | no | yes (re-enter) |
  | `dead` | no (dematerialized) | **no** | terminal |

  Selectable ⇔ `present`. Legal transitions: `present ⇄ {unconscious, departed, left}`,
  `{present, unconscious, departed, left} → dead`; nothing exits `dead` (except an explicit
  player override — undo is a player action, not an engine one).

## Architecture — durable presence via the event log

Presence lives at the **session runtime level** (changes mid-scene, must survive reload).
Rather than a new table or a Redis dependency (which is best-effort / off in tests), the
**Event log is the store**: presence = the fold of `character_status_change` events for the
session (default `present`). This is durable in Postgres/SQLite, survives reload, works in
tests with no Redis, and rehydrates through the exact reducer pipeline the transcript uses.

Detection layers (combined, not either/or):
1. **Deterministic** — a `health`-keyed stat clamped to its `min` → auto `unconscious`.
2. **Planner `exit` action** — the orchestrator, reading the transcript, decides a
   character has died/left/collapsed and emits the transition (the primary narrative path).
3. **Self-declaration** — a character emits a `<type:presence_change>` block in-voice.
4. **Manual** — the player sets any status from the cast rail (`POST …/presence`), and undo
   posts the inverse.

## Phases (commit per phase; `[Scene Presence Actions] (n/6) Complete: …`)

### P1 — `character_status_change` event + durable presence resolution (backend)
- `schemas/base.py`: add `character_status_change` to `EventType`.
- `events/envelope.py`: `CharacterStatusChangeData` (`characterId`, `status`, `reason`,
  `auto: bool`) + `CharacterStatusChangeEvent` + union + `__all__`.
- New `services/presence.py`: `STATUSES`, `SELECTABLE = {"present"}`, `is_selectable`,
  `normalize_status`, `vital_status_for(definition, value)` (health→min ⇒ `unconscious`),
  and `current_presence(db, session_id) -> dict[str, str]` folding the session's
  status-change events (latest per character wins; default `present`).
- `assembler.py`: `CastMember.presence: str = "present"`; `_build_cast` sets it from
  `current_presence`; `assemble_context` resolves the map once and passes it in.
- Tests: envelope validates the new event; `current_presence` fold (default, latest-wins,
  multi-character); assembler stamps presence onto cast.

### P2 — planner present-only roster + `exit` action + empty-scene guard (backend)
- `planner_agent.py`: roster built from **present** members only (numbers local to the
  call); `_ACTIONS += {"exit"}`; `BeatDecision.status` for the exit target; system-prompt
  rule for choosing `exit` with a `status`; `_fallback_beat` skips non-present members;
  empty present-cast → `end`.
- `turn_engine.py`: handle `decision.action == "exit"` → emit `character_status_change`,
  **mutate the in-memory `ctx.cast` member's `presence`** so the next beat sees it, trace
  it; guard the loop when no present members remain. Reflection targets → present only.
- Tests: planner omits a non-present member + never selects it; exit decision emits the
  event and stops re-selection; empty present-cast ends cleanly.

### P3 — deterministic vital trigger + self-declaration `presence_change` (backend)
- `emission.py`: recognize a `presence_change` JSON block as a segment type.
- `validator.py`: `validate_presence(raw, *, current)` → a legal `(status, reason)` or
  `None` (drops illegal transitions / unknown statuses / a change out of `dead`).
- `turn_engine.py`: apply a `presence_change` segment (emit + mutate `ctx.cast`); after a
  stat change, run `presence.vital_status_for` and auto-emit `unconscious` on health→min.
- `character_turn_agent.py`: contract mentions the optional `<type:presence_change>` block.
- Tests: emission parses the block; validator legal/illegal; health→0 auto-unconscious; a
  self-declared exit removes the character from selection.

### P4 — manual presence endpoint + undo signal (backend)
- `schemas/play.py`: `PresenceRequest` (`sessionId`, `characterId`, `status`, `reason`).
- `routes/play.py`: `POST /play/{scenarioId}/presence` → validate scenario + session +
  character + status, persist a `character_status_change` (`auto=False`), touch session,
  return the persisted event shape. Auto (engine) events carry `auto=True` so the client
  shows an undoable toast; manual ones don't.
- Tests: endpoint persists + returns; unknown scenario/session/character/status errors;
  the event shows up in session history (fold works end-to-end).

### P5 — frontend presence state + cast rail states + manual control + undo (frontend)
- `lib/events.ts`: `CharacterStatusChangeEvent` + `PresenceStatus` in the `PlayEvent` union;
  `lib/api.ts`: `setPresence`.
- `turn-stream.ts`: `applyPresence(map, event)` reducer + `rehydrateFromHistory` folds
  status events into a `presenceByChar` map.
- `useScenePlay.ts`: `presenceByChar` state; `onFrame` routes `character_status_change`
  (auto → undo toast); `setPresence(characterId, status)` optimistic + `POST`; rehydrate.
- `CastRail.tsx`: render status (present normal; unconscious/departed dimmed + badge; left/
  dead grouped as "Departed"/struck), a labeled per-character presence `<select>` (full
  manual control, keyboard-operable), speaking marker unchanged.
- `StoryPlayerView` threads `presenceByChar` + `setPresence` to `CastRail`.
- Tests: `applyPresence` fold; rehydrate; hook routes event + undo; CastRail renders each
  status + fires `setPresence`.

### P6 — docs + validation + merge
- `api-contract.md` (new event + endpoint), `data-flow.md` (presence layer + detection
  paths), `design-system.md` (cast-rail states), `component-map.md` (CastRail/presence),
  `documentation.md` status, this plan's checklist entry.
- Validation: `uv run pytest`; frontend `npm test` + `typecheck` + `lint` + `next build`;
  a11y note for the cast-rail control. Merge to `main`.

## Non-goals / deferred
- `end_scene` / `move_scene` verbs (the bus is built to take them; not wired here).
- Player-directed puppeting of a non-present character is left to the player's discretion
  (manual override remains available); the engine simply never auto-selects a non-present
  one.
- No Alembic migration — presence is event-log-derived, so no schema change.
