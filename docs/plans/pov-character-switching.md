# Player POV — speak as a character in the scene

## 1. Introduction

Today the player is always the scene's *guide/narrator*: every submitted line is recorded as a `role: "player"` beat, the intent interpreter decides who reacts, and the AI voices every character. This plan adds a **Player POV** control that lets the player *become* one of the characters in the scene. When POV is set to Mei, the player's message **is Mei's line** (spoken in Mei's slot on the right of the transcript, with Mei's monogram/name), the other present characters and the narrator react to it, and the turn loop runs until it naturally settles — then hands control back to the player *as Mei* for the next line. Selecting "Narrator" (the default) preserves today's exact behavior.

The approach reuses the machinery already built for the Reactive Turn Director "puppet" path (`docs/plans/reactive-turn-director.md`) and the turn loop runtime (`docs/plans/turn-loop-runtime.md`). A POV line is a *player-authored character beat*: it is seeded into `turn_beats`/the Redis buffer as a `character` beat (so later speakers react to *Mei said X*), persisted on the `user_turn` row so reload is faithful, but **not re-emitted** as a visible character event (the client already renders it optimistically / on rehydrate). The only new engine rule is that the POV character is removed from the planner's selectable roster, so the AI never speaks for them; the loop then ends on its own when the remaining cast is done reacting. No new tables, no new streaming primitives — a new request field, one new `user_turn` data key, one new suggestion variant, and a handful of frontend rendering changes.

This is single-local-player only; simultaneous / multi-seat POV is out of scope.

---

## 2. Gaps & Unanswered Questions

- **Naming collision with the existing `mode` field (resolved by assumption).** `schemas/play.py` already defines `TurnMode = Literal["pov", "narrator"]` on `TurnRequest.mode`, but that field is a *rendering* switch (narrator interstitials on/off) and is unrelated to speaking as a character. **Assumption:** leave `mode` untouched and add a *separate* field `pov_character_id: str | None` (camel `povCharacterId`). `None` = today's guide/narrator behavior.
- **Loop stopping (resolved by decision #1).** The planner is best-effort and cannot be relied on to "stop when it's the player's turn." **Decision:** the POV character is simply *excluded from the selectable roster* so the loop runs as far as it wants and ends naturally (bounded by the existing `TURN_MAX_BEATS` and per-scene `max_turns` caps). A defensive coercion — if the planner ever returns `speak(actor == pov)`, treat it as `end` — is kept only as a backstop; it is not the primary mechanism.
- **Out-of-character player lines (resolved by decision #2).** POV lines are authoritative and bypass the continuity guard, exactly like puppet beats. Characters are meant to be fluid and adapt; no OOC guardrails are added, and reflection still runs for the POV character so their interior stance stays current for when control is handed back to the AI.
- **Solo POV (resolved by decision #3).** When the POV character is the only present cast member, the turn is the player's line plus (optionally) the narrator filling in around it. This already falls out of the loop — nothing special required.
- **Action vs. dialogue in a POV line (assumption).** **Assumption:** the player's text renders as the character's *dialogue* by default; `*asterisk*` spans are parsed into a `character_action` beat via the existing `services.emission.parse_emission`. This is a small nicety inside Phase 1 and can be dropped without affecting the rest.
- **Idle POV switch before sending (assumption).** Current POV is reconstructed on reload from the most recent `user_turn.data.pov`. **Assumption:** switching POV but not yet sending a turn is *not* separately persisted in v1 (it takes effect on the next send). A dedicated `pov_change` marker event is a documented future seam if idle-switch persistence is wanted later.
- **`directedAt` + POV coexistence (assumption).** **Assumption:** a POV player may still address another character (be Mei, address Luna); `directedAt`/intent `addressed` continues to route the reaction. The only constraint is that the POV character is never the auto-selected responder.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend: the POV turn path + persistence

- **Locations:**
  - `web/backend/app/schemas/play.py` — add `pov_character_id: str | None = None` to `TurnRequest` (document it alongside the existing `mode`, calling out that they are orthogonal).
  - `web/backend/app/services/events_store.py` — `record_user_turn` gains a `pov: str | None` parameter and writes it into the event `data` (`{"text", "directedAt", "pov"}`).
  - `web/backend/app/services/turn_engine.py` — `run_turn`:
    - Resolve the POV member: `pov = ctx.cast_by_id(req.pov_character_id)` only when present and `is_present`; otherwise fall back to `None` (narrator behavior).
    - Pass `pov=req.pov_character_id` into `record_user_turn` so it lands on the `user_turn` row (`validate_turn_inputs` is unchanged — it only pre-flights scenario/text/session).
    - When `pov` is set: seed `turn_beats` with `{"role": "character", "text": text, "characterId": pov.id}` instead of the `player` beat, and call `buffer.push_turn(session.id, "character", text, character_id=pov.id)` instead of the `player` push. Do **not** emit a visible `character_dialogue`/`character_action` event for this line (mirrors how the player line is seeded-but-not-emitted today). Optionally run `emission.parse_emission` on the text so `*action*` spans seed an additional `character_action` beat.
    - Thread a `locked_id=pov.id` argument into the ReAct loop's `planner_agent.next_beat` call so the POV character is never chosen to speak.
    - Exclude the POV character from the **puppet** path too: `puppet_members` drops any `directed_actors` id equal to `pov.id` (the player IS the POV character — the AI must never voice a second beat for them). This keeps "the AI never speaks for the POV character" true across both the planner and the puppet paths.
    - Backstop: if a `BeatDecision` comes back as `speak` with `actor_id == pov.id`, coerce it to `end`.
    - Leave narrator interstitials, presence handling, stat/relationship application, and the final quiet-holding narration unchanged.
  - `web/backend/app/agents/planner_agent.py` — `next_beat` (and `_fallback_beat`) accept `locked_id: str | None = None` and drop it from the selectable roster (`present`) before building the options and in every fallback branch (broadcast walk, addressed, freeform), so a locked character never appears as an option even offline.
- **Rationale:** Attribution is the whole feature — later speakers must see the player's line as *the character's* line, and reload must reproduce it. Excluding the POV character from the roster (rather than special-casing an early stop) is what lets the scene "run as far as it wants until it stops normally," per decision #1.
- **Action:** Run validation for this phase — `uv run pytest utils/tests/backend/api/test_play_turn_pov.py utils/tests/backend/agents/test_planner_pov.py utils/tests/backend/services/test_events_store.py` (new `test_play_turn_pov.py`, `test_planner_pov.py` covering: POV line seeded as a character beat + buffered with `characterId`; no duplicate visible event; POV char excluded from planner roster; loop ends naturally with only-POV-remaining; `speak(pov)` coerced to `end`; `pov` persisted on `user_turn`). Update `docs/api-contract.md` (the new request field + `user_turn.pov`) and `docs/data-flow.md` (POV beat path) in this same change. Once green, commit locally: `POV Switching (1/4) Complete: Backend POV turn path — player line seeded/persisted as the chosen character; POV char excluded from the AI roster.`

### Phase 2 — Backend: POV-aware suggestions

- **Locations:**
  - `web/backend/app/agents/director_agent.py` — add a POV variant of `propose_branches` (e.g. `propose_pov_lines(db, ctx, turn_beats, speaker, count)`) that returns **first-person candidate next lines in the POV character's voice** rather than situation-wide branches. Reuse the roster/`_recent_sequence` context and the same `_MAX_BRANCHES` clamp; a new prompt (registered in `agents/prompt_registry.py` for editability, following the existing `DIRECTOR_BRANCH` pattern) instructs "write N short lines *Mei* might say next, in her voice."
  - `web/backend/app/services/turn_engine.py` — when `pov` is set and `suggestions_count > 0`, call the POV suggestion path instead of `propose_branches`; still emit them via the existing `branch_choices` event so the client's compose-from-suggestion flow is unchanged. Keep `reflection.dispatch_reflection` running for all present characters **including** the POV character (so the "other characters' thoughts build" while the player reads, and the POV character's interior stays current for when the AI takes them back over — decision #2).
- **Rationale:** In POV the end-of-turn suggestions must read like something *Mei* would say (they flow into the composer via the existing `choose → composer` path), not a narrator-level fork. Reusing `branch_choices` avoids any new event type or client reducer. This is the already-budgeted extra LLM call (decision #4).
- **Action:** Run validation — `uv run pytest utils/tests/backend/agents/test_director_pov_suggestions.py` (POV suggestions are first-person/in-voice, count-clamped, empty on no-LLM) and re-run the Phase 1 engine tests for the suggestion branch. Update `docs/api-contract.md` to note that `branch_choices` carries POV lines when a POV is active. Once green, commit locally: `POV Switching (2/4) Complete: POV-aware in-voice suggestions; reflection retained for the POV character.`

### Phase 3 — Frontend: contract, submit, and reload

- **Locations:**
  - `web/frontend/lib/types.ts` + `web/frontend/lib/api.ts` — add `povCharacterId?: string | null` to the `postTurn` request body type; ensure the `user_turn` persisted-event data type includes optional `pov`.
  - `web/frontend/features/story-player/scene-data.ts` — add `fromPlayer?: boolean` to `SceneMessage`.
  - `web/frontend/features/story-player/useScenePlay.ts` — add `pov: string | null` state (+ `setPov`), default `null`. `submit`/`send` pass `povCharacterId: pov`; the optimistic bubble becomes `{ kind: "char", who: pov, fromPlayer: true, text }` when `pov` is set (else the existing `{ kind: "player" }`). On resume, derive current POV from the most recent `user_turn.data.pov` in history. Reset `pov` to `null` if the chosen character is no longer present (watch `presenceByChar`). Expose `pov`/`setPov` from the hook.
  - `web/frontend/features/story-player/turn-stream.ts` — in `rehydrateFromHistory`, a `user_turn` row with `data.pov` set becomes `{ kind: "char", who: pov, fromPlayer: true, text }`; without `pov` it stays a `player` beat. (No change to live `mergeFrame`, since the engine does not emit a visible event for the POV line.)
- **Rationale:** The contract and reducers must carry "this character beat was authored by the player" end to end, or a reopened scene will mis-render POV lines as left-side AI beats or duplicate them.
- **Action:** Run validation — `cd web/frontend && npm test` for `turn-stream.test.ts` (rehydrate: POV `user_turn` → right-side character beat; non-POV unchanged; no duplication) and a `useScenePlay` test (optimistic POV bubble, POV reset on presence loss), plus `npm run typecheck`. Update `docs/data-flow.md` (client POV state + rehydrate) in this change. Once green, commit locally: `POV Switching (3/4) Complete: FE contract, optimistic POV bubble, and faithful reload of player-authored character beats.`

### Phase 4 — Frontend: the Player POV selector, right-side character rendering, and polish

> **Deviation from the original draft (per the user's instruction):** the POV selector lives in the **composer's controls bar, immediately to the right of the Config button** — *not* in the `CastRail` above "In the Scene". Everything else (right-side character rendering, resume, presence-loss reset) is unchanged.

- **Locations:**
  - `web/frontend/components/feature/PovSelect.tsx` *(new)* — a small, self-contained **"Speaking as"** control: a labeled native `<select>` (same accessible pattern as `CastRail`'s `PresenceControl`) whose options are **"Narrator"** (value `""` → `null`) plus each *present* cast member (`{ id, name }`). Props: `pov`, `onPovChange`, `options`. Renders nothing (or a disabled "Narrator"-only state) when there are no present cast members. Styled to sit inline in the composer controls row next to the Config pill (mono, compact, `focus-visible` ring).
  - `web/frontend/components/feature/Composer.tsx` — render `PovSelect` in the bottom-left controls bar **directly after** the `SceneConfigMenu` (the Config button), before the flex spacer. Thread through new props `pov`, `onPovChange`, `povOptions`. The message-textarea placeholder reflects the active POV (e.g. "Speaking as Mei…" vs the current "Speak, or describe what you do…").
  - `web/frontend/components/feature/TranscriptBeat.tsx` — add a `PlayerAsCharacterMessage` renderer: right-aligned like `PlayerMessage`, but with the character's `Monogram`, name, and color instead of "You". Route it from `TranscriptBeat` when `m.kind === "char" && m.fromPlayer`.
  - `web/frontend/features/story-player/StoryPlayerView.tsx` — compute the present-cast POV options (`scenario.cast` filtered by `scene.presenceByChar`) and thread `scene.pov`, `scene.setPov`, and `povOptions` into `Composer`; `TranscriptBeat` already receives the message so no new prop is needed beyond `fromPlayer` on it. Optionally reflect the active POV in the `CastRail` `TurnOrder` "You" chip (it occupies the POV character's slot) — nice-to-have, not required.
- **Rationale:** This is the visible feature: choose your POV right next to the Config button in the composer, then see your own lines appear on your side of the transcript but wearing the character's identity, persisted across reloads. Putting it in the composer keeps the "who am I speaking as" choice adjacent to where the player types.
- **Action:** Run validation — `cd web/frontend && npm test` (new `PovSelect` test; `Composer` POV-selector wiring test; `TranscriptBeat` player-as-character rendering test), `npm run typecheck && npm run lint`, plus the required **accessibility + responsive pass** per `docs/skills/accessibility-mobile/SKILL.md` and `docs/skills/ada-compliance/SKILL.md` (labeled select, keyboard/focus, contrast on the right-side character bubble, 320/375/768/1024). Update `docs/component-map.md` (composer `PovSelect`, `PlayerAsCharacterMessage`), `docs/design-system.md` (right-side character-bubble variant), and add a `docs/checklist.md` follow-up entry. Once green, commit locally: `POV Switching (4/4) Complete: Player POV selector (right of Config) + right-side character rendering + composer polish, a11y/responsive verified.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| `povCharacterId` request field | New turn field selecting the character the player speaks as (`None` = narrator) | `web/backend/app/schemas/play.py` |
| POV `user_turn` persistence | `pov` written into the `user_turn` event data for faithful reload | `web/backend/app/services/events_store.py` |
| POV turn path | Seed the player line as a character beat, buffer it as `character`, withhold the visible event, lock the POV char out of the roster, backstop `speak(pov)→end` | `web/backend/app/services/turn_engine.py` |
| Planner roster lock | `next_beat`/`_fallback_beat` accept `locked_id` and drop it from selection | `web/backend/app/agents/planner_agent.py` |
| In-voice POV suggestions | First-person candidate next lines for the POV character | `web/backend/app/agents/director_agent.py`, `web/backend/app/agents/prompt_registry.py` |
| Backend POV tests | Engine + planner + suggestion behavior. **Note:** the turn engine is exercised end-to-end through the play route, so the engine POV tests live in `utils/tests/backend/api/test_play_turn_pov.py` (matching the existing `test_play_turn.py` pattern) rather than under `services/`. | `utils/tests/backend/api/test_play_turn_pov.py`, `utils/tests/backend/agents/test_planner_pov.py`, `utils/tests/backend/agents/test_director_pov_suggestions.py` |
| FE turn contract | `povCharacterId` on `postTurn`; `pov` on `user_turn` data; `SceneMessage.fromPlayer` | `web/frontend/lib/types.ts`, `web/frontend/lib/api.ts`, `web/frontend/features/story-player/scene-data.ts` |
| POV client state | `pov`/`setPov`, optimistic POV bubble, resume-derived POV, presence-loss reset | `web/frontend/features/story-player/useScenePlay.ts` |
| POV reload reducer | `user_turn.pov` → right-side player-authored character beat | `web/frontend/features/story-player/turn-stream.ts` |
| Player POV selector | "Speaking as" select **to the right of the Config button** in the composer | `web/frontend/components/feature/PovSelect.tsx`, `web/frontend/components/feature/Composer.tsx` |
| Player-as-character bubble | Right-aligned bubble wearing the character's identity | `web/frontend/components/feature/TranscriptBeat.tsx` |
| View + composer wiring | Thread POV through the story player; POV-aware placeholder | `web/frontend/features/story-player/StoryPlayerView.tsx`, `web/frontend/components/feature/Composer.tsx` |
| FE POV tests | Rehydrate, optimistic bubble, selector, rendering | `web/frontend/features/story-player/turn-stream.test.ts`, `web/frontend/features/story-player/useScenePlay.test.ts`, `web/frontend/components/feature/CastRail.test.tsx`, `web/frontend/components/feature/TranscriptBeat.test.tsx` |
| Docs | Contract, data flow, components, design system, checklist | `docs/api-contract.md`, `docs/data-flow.md`, `docs/component-map.md`, `docs/design-system.md`, `docs/checklist.md` |

## 5. Notes & Future Seams

- **`pov_change` marker event** — if idle POV switches (changed but not yet sent) need to survive a reload, persist a small `pov_change` event and fold it in `rehydrateFromHistory`; deferred in v1 (current POV is reconstructed from the last `user_turn`).
- **Reflection ownership** — reflection intentionally continues for the POV character so the AI has an up-to-date interior when control is handed back. If this ever conflicts with player intent, the seam is to base the POV character's reflection on the player-authored line only (or skip it).
- **Voice consistency of POV lines** — POV lines bypass the continuity guard by design (player authority + fluid characters). If a soft "did that read as Mei?" hint is ever wanted, it belongs as an optional, non-blocking check, never a gate.
