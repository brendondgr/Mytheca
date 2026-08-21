# Steering the Scene

## 1. Introduction

Mytheca already has a real director's contract inside the turn loop. The player's
direction is parsed into `direction_agent.DirectionRequirement`s, the planner is shown what
is still owed and how many beats remain, and once the budget runs as tight as the direction
is long the engine stops asking and schedules the rest itself
(`direction_agent.schedule`). What is missing is everywhere the contract meets the player:
the direction box only exists once a POV character has been picked, the direction is never
persisted so a reload loses it, a direction cannot be sent without also speaking a line, the
`@` menu can only name a *file* and not a *person*, `directedAt` is supported by the backend
and never sent by the UI, and there is no way to say "this part is Mei's" other than hoping
an LLM infers it from prose. This plan makes directing the scene a first-class, legible,
reliable act: the direction becomes a persisted part of the turn record, a turn can be pure
direction, the direction surface exists from the first frame of play, `@Mei` means Mei, one
tap writes real phrasing, and every requirement can be aimed at a named character and
carried forward until it actually lands.

**The diagnosis the owner asked for — why requirements get dropped.** Reading
`services/turn_engine.py` (`run_turn` ≈ 400–1203, `_delivered` at 1247, `_direction_lead` at
1279, `_plan_still_valid` at 1300) and `agents/direction_agent.py` end to end, there are
**seven distinct causes**, and they are not one bug:

1. **The satisfaction signal is a promise, not an observation, and it fires too early.**
   `_delivered()` calls `SceneDirection.satisfy(owed)` *before* the beat is generated — in
   the puppet path (line 665) before `_generate_speaker`, in the planner path (line 993)
   before `_beat_or_skip`, in the narrate path (line 924) before `_narrator_interstitial`.
   `_beat_or_skip` correctly reports `played=False` for a beat that came back empty, was
   withheld as a scratchpad leak, or failed against the endpoint — and the loop correctly
   declines to count it against `scene_beats`. But **nothing un-satisfies the requirement**.
   A beat that never reached the page has already ticked its requirement off permanently.
   This is the largest single cause of "it forgets what happens".
2. **The actor binding is guessed and then silently discarded.**
   `direction_agent.resolve_requirements` maps the model's `actor` number through
   `roster_ids.get(_as_int(...) or -1)`; a name instead of a number, an out-of-range index
   or a missing field all degrade to `actor_id=None` — the narrator — with no signal. The
   player has no way to state the target at all.
3. **`rebind()` re-owns to the narrator on every loop iteration.** It runs at line 721 on
   each pass, re-owning any requirement whose actor is not `is_present` *or is the POV
   character*. Under POV, anything the player aimed at the character they are voicing is
   instantly narrator-owned; a character who steps out mid-turn hands their requirement to
   the narrator and never gets it back if they return.
4. **A long direction is compressed rather than spread.**
   `open_limit = None if max_turns <= len(direction.requirements) else 1` (line 616) lets the
   opening narration absorb *every* narrator-owned requirement in one paragraph, and
   `schedule()`'s `remaining <= 1 and len(outstanding) > 1` rule bundles all remaining
   requirements into one closing narrator beat. With `max_turns` defaulting to 5 and
   `MAX_REQUIREMENTS = 6`, an ordinary long direction reaches both.
5. **Only one of an actor's requirements ever rides a planned beat.** Both the narrate site
   (line 923) and the speak site (line 992) slice `[:1]`, while the puppet site (line 664)
   takes all of them. A two-part requirement for the same character needs two beats it may
   never be given.
6. **The direction does not survive the turn.** `SceneDirection` is constructed inside
   `run_turn` and discarded at the end. The closing trace names what went undelivered, and
   then the information is gone — the composer has already cleared `guidance`, so the next
   turn starts from nothing. The player watches the checklist print `✕ did not fit this
   scene` and then watches it vanish. That is what "it forgets" feels like from the outside.
7. **The direction is never persisted.** `events_store.record_user_turn` writes
   `{text, directedAt, pov}`. Nothing can compare asked-vs-delivered after the fact, no
   export shows it, and a reload cannot restore it.

The fix follows the diagnosis rather than papering over it, and it costs **no additional LLM
calls** — the repo has already rejected an LLM "did that happen?" verifier on cost, and the
planner is already ~56 % of turn time. Causes 1 and 6 are structural and are fixed
structurally: split the single `satisfied` flag into **attempted** (carried into a prompt)
and **delivered** (a beat actually existed and reached it), and give the session a
**standing direction** so an undelivered requirement is carried into the next turn instead
of evaporating. The "did it reach it?" signal is a cheap, deterministic, in-process
**lexical coverage** check (`services/direction_check.py`) over the emitted beat text — no
network, no model, unit-testable — and it is used *conservatively in one direction only*: a
high score confirms, a low score never erases a delivery, it only declines to confirm one.
Cause 2 is fixed by letting the UI send an **explicit per-requirement actor target**, cause 3
by making an explicitly pinned target immune to `rebind` (and reporting it as *blocked*
rather than silently narrating it), causes 4 and 5 by pacing against the real remaining
budget instead of a fixed `[:1]`.

---

## 2. Gaps & Unanswered Questions

**Assumptions taken (simple gaps — stated and proceeded with):**

- **The Control Over the Record plan lands first.** `docs/plans/control-over-the-record.md`
  owns the session tray, rewind/edit/branch, the Continue button, and the
  `turn_engine.validate_turn_inputs` relaxation that permits a text-less turn. This plan
  *consumes* the relaxation in Phase 3 and does not re-own it. If Phase 3 finds
  `validate_turn_inputs` (currently `turn_engine.py:390`) still hard-requiring `text`, land
  the minimal relaxation there — accept a turn whose `text` is empty only when `guidance`,
  `directives` or `outcome` is non-empty — and note the overlap in the commit message.
- **The "starting five" direction verbs do not exist in the repo today.** Grepping for
  `escalate` / `time skip` / `calm it down` across `web/frontend` finds only branch-outcome
  test fixtures. So "expand the five" means *build the surface once, richly*, rather than
  ship five and then widen them. Phase 10 builds the grouped, context-aware surface directly.
- **`directedAt` is a single id, but a player may type several `@` cast mentions.** Rule:
  the **first** cast mention in the *message* box becomes `directedAt`; later ones still
  render as chips and still reach the intent agent as plain names (which they now do,
  because Phase 5 makes the name survive the strip). Cast mentions in the *direction* box
  never set `directedAt` — they pin a requirement's actor.
- **The coverage threshold starts at 0.5** (half of a requirement's content words appear in
  the beat) and is a settings value, not a constant baked into the algorithm. It is
  conservative by construction: a false negative costs one extra beat plus a visible
  "not confirmed" carry-over item; a false positive costs nothing worse than today's
  behaviour. Tuning it is an experiment, not a code change — see the deferral below.
- **Carry-over lives on the session, not re-derived from the event log.** A new nullable
  JSON column `PlaySession.standing_direction` is explicit, cheap to read, and additive
  (`core/bootstrap._reconcile_additive_columns` self-heals it — no Alembic migration).
  Re-deriving it by scanning `TurnTrace` rows would be fragile and would break the moment
  the trace copy changes.
- **A joined character is session-scoped, not written into `Scenario.cast_ids`.** Bringing
  someone in mid-play must not silently re-author the scene for every other play-through.
  `assembler._build_cast` unions the scenario's `cast_ids` with any character that has a
  `character_status_change` event on *this* session.
- **Decline is recorded as presence, not as a new resolution mechanism.** Accepting a cast
  request posts `character_status_change {status: "present", auto: false}`; declining posts
  `{status: "departed", auto: false, reason: "declined"}`. Both fold through the existing
  reducer, both survive reload, and "have we already asked about this character?" reduces to
  "does this character have a status event on this session?".
- **`mode` stays unexposed.** `TurnRequest.mode` reaches exactly one place in the engine —
  the `turn` trace payload at `turn_engine.py:451`. It changes nothing. The review's
  guardrail says do not expose it until it can be described in one sentence a player would
  care about, and it cannot. Phase 11 documents it as inert and deprecated on both sides of
  the mirror; it is not removed, so no existing caller breaks.

**Complex gaps — Human intervention is needed to answer these questions:**

1. **Should the composer render a resolved mention as an inline chip inside the text?**
   The composer is a plain `<textarea>` today (`Composer.tsx`), which cannot host inline
   elements. Two options, both real work: (a) an **overlay mirror** — an `aria-hidden`,
   absolutely-positioned div behind a transparent-caret textarea, painting highlight spans;
   ~100–150 lines, must mirror font metrics, padding, wrapping and `scrollTop` exactly, and
   drifts under browser zoom and `text-size-adjust`; (b) **contenteditable** — correct chips,
   but it rewrites every key path in `Composer.tsx` (send-on-Enter, the mention sync, caret
   restoration, IME composition, paste) and would put the whole co-located `Composer.test.tsx`
   suite through a rewrite. This plan ships the below-the-box chip list that already exists,
   extended with the cast namespace, and does **not** build either. *Human intervention is
   needed to answer this question.*
2. **What should happen to a carried-over requirement the player never dismisses?** The
   standing direction is capped at `MAX_REQUIREMENTS` and ordered oldest-debt-first, so a
   persistently-undeliverable requirement will crowd out newer ones. Options: expire after N
   turns, expire on a scene/setting change, or keep it until dismissed. This plan keeps it
   until dismissed and caps the list, because silently dropping the player's direction is the
   exact failure being fixed — but "forever" is a product call.
   *Human intervention is needed to answer this question.*
3. **Should an unconfirmed delivery be shown to the player as a distinct third state, or
   folded into "outstanding"?** Showing three states (`delivered` / `attempted, not
   confirmed` / `outstanding`) is honest but exposes the heuristic's uncertainty in the UI,
   and a false negative then reads as the app doubting prose the player just watched land.
   Phase 8 implements three states behind a plain-language label ("the scene may not have
   reached this"), but whether that is the right thing to put in front of a reader is a
   product call. *Human intervention is needed to answer this question.*

**New deferrals to add to `docs/checklist.md` (Phase 11):**

- The coverage threshold has never been measured. It needs an experiment under
  `docs/research/experiments/` (a set of directions with hand-labelled delivered /
  not-delivered beats, sweeping `DIRECTION_COVERAGE_THRESHOLD`, reporting precision/recall
  per threshold) and an entry in `docs/research/OPEN_QUESTIONS.md`. Not run in this plan.
- Inline mention chips (gap 1 above).
- Standing-direction expiry (gap 2 above).

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — The persisted direction becomes visible: reload, export, Inspector

> **Boundary.** `docs/plans/control-over-the-record.md` Phase 1 adds `guidance` to
> `events_store.record_user_turn` and passes it from the engine; its own text says
> *"Steering owns the composer restore"*. So this phase **consumes** that write and owns
> everything downstream of it. Before starting, confirm `record_user_turn` accepts and stores
> `guidance`; if that plan has not landed, add the keyword and the engine call here (two lines,
> purely additive to a JSON column — no schema change, no migration) and say so in the commit.

- **Locations:**
  - `web/backend/app/services/turn_engine.py` — the `turn` trace step (~line 447) carries
    `guidance` in its `data`, so the Inspector can put "asked" next to the `direction` steps'
    "delivered". (The `record_user_turn` call itself belongs to the sibling plan.)
  - `web/backend/app/services/session_export.py` — `group_turns`: add `"guidance"` to the
    per-turn `player` dict; `render_markdown`: render a `_Direction:_ …` line under the
    player's line when present. `_STEP_LABELS`: add `"direction": "Scene direction"` and
    `"files": "Tagged files"` (both already emitted, neither labelled).
  - `web/frontend/features/story-player/turn-stream.ts` — new `latestGuidance(events)`
    mirroring `latestPov`: walk backwards to the most recent `user_turn` and return
    `data.guidance` or `""`.
  - `web/frontend/features/story-player/useScenePlay.ts` — in the resume effect (~line 249,
    beside `setPov(latestPov(...))`), restore `setGuidance(latestGuidance(history.events))`.
  - `web/frontend/components/feature/TurnInspectorPanel.tsx` — add `direction` and `files` to
    `STEP_META` (`{ tag: "Direct", color: "#c2410c" }` / the existing Files teal) so direction
    rows stop rendering with a raw step name, and render the `turn` step's `guidance` under the
    player's line so the panel shows what was asked next to what the direction steps report
    was delivered.
  - `docs/api-contract.md` (§ NDJSON Event Stream → the `user_turn` row shape) and
    `docs/data-flow.md` (§ Write + Streaming Path, § Scene Persistence, Resume & Export).
  - Tests: a new `utils/tests/backend/services/test_session_export_direction.py` (the JSON and
    Markdown renders both carry the direction), and co-located
    `web/frontend/features/story-player/turn-stream.test.ts` (`latestGuidance`) +
    `useScenePlay.test.ts` (resume restores the direction box). Add the `guidance` round-trip
    assertion to `utils/tests/backend/services/test_events_store.py` only if the sibling plan
    has not already put one there.
- **Rationale:** Everything later in this plan reads the direction as part of the turn record —
  the carry-over in Phase 8 needs a persisted "what was asked", the export needs it, and the
  reload restore is the first thing a player notices. It is also the smallest possible change,
  so it is the right first commit.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services utils/tests/backend/api` and, from `web/frontend`, `npm test -- turn-stream useScenePlay TurnInspectorPanel` plus `npm run typecheck`; for web/UI changes also an accessibility + responsive pass (keyboard, visible focus, AA contrast, 320/375/768/1024). Once green, commit locally: `[Steering the Scene] (1/11) Complete: The persisted scene direction is restored into the composer on reload and shown in exports and the Inspector.` Do not push or open a PR.*

---

### Phase 2 — Extract the direction machinery into its own module

> **Boundary.** `docs/plans/control-over-the-record.md` Phase 3 already splits
> `turn_engine.py` (1986 lines) into `turn_emit.py` + `beat_runner.py` + `turn_setup.py`
> (+ `turn_finalize.py` if needed) and explicitly **leaves the direction helpers behind** —
> `_delivered`, `_name_of`, `_direction_lead`, `_plan_still_valid` stay in `turn_engine.py`.
> Those are exactly the functions this plan grows, so this phase takes the remaining slice.
> Before starting, run `wc -l web/backend/app/services/turn_engine.py`. If the sibling split
> has not landed, do it here first, to the module boundaries that plan names — do not invent a
> second, incompatible layout.

- **Locations:**
  - **`web/backend/app/services/direction_runtime.py`** (new) — move verbatim from
    `turn_engine.py`: `_delivered` → `delivered`, `_direction_lead` → `direction_lead`,
    `_name_of` → `name_of`, `_plan_still_valid` → `plan_still_valid`, plus the direction block
    currently inlined in `run_turn` (~lines 564–594: build the `SceneDirection` from `guidance`
    or `intent`, `rebind`, emit the opening `direction` trace) exported as
    `build_direction(db, ctx, req, intent, pov_id)`. If the sibling plan's `turn_setup.py`
    already calls that block, have `turn_setup.prepare_turn` import it from here instead of
    holding a copy — one owner, not two.
  - `web/backend/app/services/turn_engine.py` — import from `direction_runtime`; update the
    module docstring to name the module split.
  - `utils/tests/backend/` — update any test importing the renamed private symbols
    (`test_degenerate_beat.py:100` is the known one, and belongs to the sibling split).
  - `docs/architecture.md` + `docs/structure.md` + `CLAUDE.md`'s backend services table.
  - Tests: no new behaviour, so **no new test file**. The gate is the unchanged
    `uv run pytest` plus `wc -l` on every touched module reporting **≤ 800**.
- **Rationale:** A pure, behaviour-free move before the engine work means Phases 7, 8 and 9
  produce readable diffs in a module that is about one thing, instead of adding several hundred
  lines of direction bookkeeping to the file that also owns the beat loop.
- *Action: Run the validation for this phase — `uv run pytest` (the full backend suite; a refactor subset proves nothing), plus `wc -l` on each touched module. Once green, commit locally: `[Steering the Scene] (2/11) Complete: The direction machinery moved into services/direction_runtime.py, with no behaviour change.` Do not push or open a PR.*

---

### Phase 3 — Direction-only turns

- **Locations:**
  - `web/backend/app/services/turn_engine.py` — `validate_turn_inputs` (line 390). **Owned by
    `docs/plans/control-over-the-record.md` Phase 9**, which lands first and states the whole
    rule: a turn is valid when any of `text`, `guidance`, `outcome` or `continuation` carries
    content, and an entirely empty turn is still a 400 raised *before* the 200 stream opens.
    **Consume it; do not re-edit this function.** Only if that plan has not landed, relax it here
    to exactly that four-way rule and say so in the commit body.
  - `web/backend/app/services/turn_setup.py` — **`docs/plans/control-over-the-record.md` Phase 9
    lands first and owns the empty-text branch here** (it already skips `buffer.push_turn`, skips
    `intent_agent.interpret`, seeds `turn_beats` empty and still writes the `user_turn` row). This
    phase **extends that one branch** to the `guidance`-only case rather than adding a second —
    the only genuinely new part is the `turn` trace's `detail` falling back to the direction text.
    The assumptions keyed to non-empty text, restated so the branch is complete:
    - `record_user_turn` is still written (the turn happened) with `text=""`; the
      `turn` trace's `detail` falls back to the direction text so the Inspector row is not blank.
    - the buffer push (`buffer.push_turn`) is **skipped** for an empty line — pushing `""` into
      the recent-turn buffer would poison the transcript window with a blank player beat.
    - `turn_beats` seeds **empty** rather than with a blank player/character beat, so the first
      speaker does not see `Player:` followed by nothing.
    - `assemble_context(..., player_text="")` already tolerates an empty string; the
      `retrieval_gate` will simply not fetch, which is correct — there is no line to ground.
  - `web/backend/app/services/turn_engine.py` — the `scene_opening` / `may_ask` conditions read
    `not ctx.recent_beats` and are unaffected; the **silent-turn backstop** (`scene_beats == 0`)
    must still fire, because a direction-only turn that produces nothing is exactly the case it
    exists for.
  - `web/backend/app/services/events_store.py` — `user_turn_stats`: `preview` currently takes
    the first player line, which for a direction-only opener would be `""`. Fall back to the
    row's `guidance` so the session list still has a human label.
  - `web/backend/app/services/session_export.py` — `render_markdown`: when `text` is empty
    render `**You** _(direction only)_` rather than a dangling `**You**: `.
  - `web/frontend/features/story-player/useScenePlay.ts` — `submit()` and `send()`: drop the
    `if (!t) return` guards in favour of "send when there is a message **or** a direction".
    The optimistic bubble becomes: a message → today's bubble; direction-only → a new
    `{ kind: "direction", text }` `SceneMessage` variant.
  - `web/frontend/features/story-player/scene-data.ts` — add the `direction` variant to
    `SceneMessage`.
  - `web/frontend/components/feature/TranscriptBeat.tsx` — render the `direction` variant as a
    quiet centred aside (reuse the "— the scene is joined —" typography), not as a speech
    bubble: the player did not say it out loud.
  - `web/frontend/features/story-player/turn-stream.ts` — `rehydrateFromHistory`: a `user_turn`
    row with empty `text` and non-empty `guidance` replays as the `direction` variant.
  - `web/frontend/components/feature/Composer.tsx` — the send guard (`onFieldKeyDown` and the
    Send button's `disabled`) becomes "message or direction is non-empty".
  - `docs/api-contract.md` (§ Turn Stream — the request precondition) and `docs/data-flow.md`.
  - Tests: new `utils/tests/backend/api/test_play_turn_direction_only.py` (a `guidance`-only
    POST streams beats; a fully empty POST is a 400 *before* the stream opens; the `user_turn`
    row is written with an empty `text`; the buffer is not pushed), plus co-located
    `web/frontend/features/story-player/useScenePlay.test.ts` and
    `web/frontend/components/feature/Composer.test.tsx` additions.
- **Rationale:** "Push the scene without speaking" is the most-requested shape of directing and
  it is currently impossible. It has to land before the always-visible direction row (Phase 4),
  or that row would be a box the player can fill and cannot send.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api utils/tests/backend/services` and, from `web/frontend`, `npm test -- useScenePlay Composer TranscriptBeat turn-stream` plus `npm run typecheck && npm run lint`; for web/UI changes also an accessibility + responsive pass (keyboard, visible focus, AA contrast, 320/375/768/1024). Once green, commit locally: `[Steering the Scene] (3/11) Complete: A turn can now be pure direction with no spoken line, end to end.` Do not push or open a PR.*

---

### Phase 4 — The direction row exists from the first frame

- **Decision, and why.** The direction row is **always rendered**; what changes between modes
  is its *role*, never whether it exists. In **narrator mode** the row is not a second
  textarea — it is a one-line labelled strip above the message box reading *"Direction — this
  message steers the scene"* (plus, from Phase 10, the verb bar). There is still exactly one
  text input, so the two modes cannot read as duplicate fields. In **POV mode** the same row
  expands into the direction textarea that exists today, because the message box is now the
  character's own line and has nowhere left to steer from. One concept, one place on screen,
  two targets. The rejected alternative — a collapsed second textarea in both modes — puts two
  empty boxes in front of a new player and makes them guess which one is "the scene"; the
  strip answers that question in words instead.
- **Locations:**
  - `web/frontend/components/feature/DirectionRow.tsx` (new) + `DirectionRow.test.tsx` —
    owns the strip/textarea switch, the label, and (from Phase 10) the verb bar slot. Props:
    `mode: "narrator" | "pov"`, `value`, `onChange`, `povName`, and a `children` slot for the
    verb bar. In narrator mode it renders the label plus the slot and **no** textarea; in POV
    mode the label, the slot, and the auto-growing textarea currently inlined in `Composer.tsx`.
  - `web/frontend/components/feature/Composer.tsx` — replace the `showGuidance` branch with
    `<DirectionRow …/>`, unconditionally. `showGuidance` (`Boolean(onGuidanceChange) && Boolean(pov)`)
    becomes `hasDirection = Boolean(onGuidanceChange)`; the mention plumbing for the
    `"guidance"` field must only run when the textarea is actually mounted (POV), so
    `syncMention("guidance", …)` stays behind the POV branch.
  - `web/frontend/features/story-player/useScenePlay.ts` — `choosePov` currently clears
    `guidance` when leaving POV (line ~"if (id === null) setGuidance('')"). That is now wrong:
    the direction is a scene-level intent, not a POV artefact. Keep the text; the narrator-mode
    strip explains that the message box carries it, and `send()` still only puts `guidance` on
    the wire under POV (narrator mode sends the message as the direction, exactly as today).
    Retain the clear-on-send behaviour.
  - `web/frontend/components/feature/Composer.tsx` — the panel's `focus-within:border-accent`
    and the hairline rule between the row and the message box must survive; check the row does
    not add a second visible border at 320px.
  - `docs/component-map.md` (new `DirectionRow` entry) and `docs/design-system.md` if the strip
    introduces a token.
  - Tests: co-located `DirectionRow.test.tsx` (renders the strip and no textarea in narrator
    mode; renders a labelled textarea in POV mode; the label is programmatically associated)
    and updates to `Composer.test.tsx` (the row is present with `pov === null`).
- **Rationale:** Until this lands, the entire direction concept is invisible to any player who
  has not happened to pick a POV character — which is most of them. Every later surface (the
  verb bar in Phase 10, the pinning affordance in Phase 8, the owed/delivered strip) attaches
  to this row, so it has to exist before them.
- *Action: Run the validation for this phase — `uv run pytest` (unchanged backend) and, from `web/frontend`, `npm test -- DirectionRow Composer useScenePlay StoryPlayerView` plus `npm run typecheck && npm run lint` and `node utils/scripts/check_frontend_css.mjs`; for web/UI changes also an accessibility + responsive pass (keyboard, visible focus, AA contrast, 320/375/768/1024). Once green, commit locally: `[Steering the Scene] (4/11) Complete: The direction row is always present — a labelled strip in narrator mode, the direction box under POV.` Do not push or open a PR.*

---

### Phase 5 — Fix the mention strip: the name survives, only the sigil goes

- **Locations:**
  - `web/frontend/features/story-player/mentions.ts` — `stripMentions`. Today, on a match it
    appends nothing, advances past the name, and swallows one trailing space, so `"Hey @Mei"`
    is sent as `"Hey"`. Change it to append the matched run **as the player typed it**
    (`text.slice(i + 1, i + 1 + hit.name.length)`, preserving their casing) and **not** swallow
    the trailing space. Result: `"Hey @Mei"` → `"Hey Mei"`, `"read @maerin.md"` →
    `"read maerin.md"`. The id still resolves, so nothing downstream changes.
  - `web/frontend/features/story-player/mentions.ts` — new `removeMention(text, option): string`.
    `Composer.removeTag` currently untags by calling `stripMentions(value, [option])` and
    testing `ids.length`; with the name surviving, that no longer removes anything. `removeMention`
    deletes the whole `@<name>` token *and* one trailing space, which is the chip's "×" behaviour
    and is now a different operation from "prepare the text to send".
  - `web/frontend/components/feature/Composer.tsx` — `removeTag` calls `removeMention` for both
    boxes.
  - `web/frontend/features/story-player/mentions.test.ts` — the existing assertions pin the old
    behaviour and must be rewritten in this phase: the name survives, the sigil is dropped, the
    ids are unchanged, whitespace collapse still applies, and a longest-first match still wins
    for a filename containing spaces.
  - `web/frontend/features/story-player/useScenePlay.test.ts` — the send path assertion on the
    stripped text.
  - `docs/data-flow.md` § "@-tagged context files (the `@` command)" — correct the sentence that
    says the token is removed.
  - Tests: the rewritten `mentions.test.ts` plus a `Composer.test.tsx` case for the chip "×"
    going through `removeMention`.
- **Rationale:** The owner calls the current behaviour "a visual nightmare", and it is equally
  wrong for documents — the sent prose loses the noun the player wrote. It must be fixed before
  the cast namespace lands in Phase 6, or `@Mei` would delete the one word the intent agent most
  needs in order to bind the line to Mei.
- *Action: Run the validation for this phase — `uv run pytest` (unchanged backend) and, from `web/frontend`, `npm test -- mentions Composer useScenePlay` plus `npm run typecheck && npm run lint`; for web/UI changes also an accessibility + responsive pass (keyboard, visible focus, AA contrast, 320/375/768/1024). Once green, commit locally: `[Steering the Scene] (5/11) Complete: An @mention now keeps its name in the sent text and only drops the sigil.` Do not push or open a PR.*

---

### Phase 6 — `@` a character, not just a document

- **Locations:**
  - `web/frontend/features/story-player/mentions.ts` —
    - `MentionOption` gains `kind: "doc" | "cast"` and optional `mono` / `color` / `portrait`
      for cast rows.
    - `filterMentions` keeps its prefix-first ordering but **orders cast before docs** within
      each tier, so a typed `@M` offers Mei before `maerin.md`.
    - `stripMentions` returns `{ text, docIds, castIds }` (both id lists derived from the final
      text, same invariant as today). Keep a thin `ids` alias equal to `docIds` **only** if
      that avoids churn; otherwise update every call site — there are two (`Composer.tsx`,
      `useScenePlay.ts`).
  - `web/frontend/components/feature/MentionMenu.tsx` — two `role="group"` sections with
    `aria-label="Cast"` / `aria-label="Context files"` and visible group headings. A cast row
    renders a `Monogram` (portrait → monogram fallback, exactly as `CastRail` does) and the
    character's colour; a doc row keeps the `⎙` glyph and its `charCount`. `aria-activedescendant`
    and the roving `activeIndex` continue to address a **flat** index across both groups, so the
    composer's existing Arrow/Enter/Tab/Escape handling is unchanged.
  - `web/frontend/components/feature/Composer.tsx` — the tagged-chip list below the box becomes
    two visually distinct chip styles: a cast chip carries the monogram and the character's
    colour on its border; a doc chip keeps the existing `⎙` mono chip. The list's
    `aria-label` becomes "Tagged in this turn". The `mentionOptions` prop now carries both
    kinds.
  - `web/frontend/features/story-player/StoryPlayerView.tsx` — build the combined mention list:
    `contextDocs` mapped to `kind: "doc"`, plus the **present** cast mapped to `kind: "cast"`,
    memoised beside `povOptions`.
  - `web/frontend/features/story-player/useScenePlay.ts` — `send()` resolves
    `stripMentions(composer, mentionOptions)`; the **first** `castIds` entry from the *message*
    box becomes `directedAt` on the request body (see the Gaps rule). Cast ids from the
    *direction* box are held for Phase 8's pinning and are not sent yet in this phase.
  - `web/frontend/lib/events.ts` — `TurnRequestBody.directedAt` is already declared; add the
    doc comment explaining that the UI now sets it from an `@` cast mention. No backend change:
    `turn_engine` already honours `req.directed_at` (line 544) by appending it to
    `intent.addressed` and promoting `freeform` to `direct`.
  - `docs/api-contract.md` (§ Turn Stream request body — `directedAt` now has a UI producer)
    and `docs/data-flow.md`.
  - Tests: `mentions.test.ts` (cast/doc split, ordering, `castIds`), `MentionMenu.test.tsx`
    (two labelled groups; a cast row is distinguishable by accessible name), `Composer.test.tsx`
    (the two chip styles both render and both remove), `useScenePlay.test.ts` (the first cast
    mention lands on `directedAt`), and a backend `utils/tests/backend/api/test_play_turn.py`
    addition asserting `directedAt` reaches `intent.addressed`.
- **Rationale:** This closes half of structural gap G5 with a mechanism the player already
  knows, and it is the natural producer for the explicit actor target Phase 8 needs. It has to
  come after Phase 5 or the name would be deleted from the prose that the intent agent reads.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api` and, from `web/frontend`, `npm test -- mentions MentionMenu Composer useScenePlay StoryPlayerView` plus `npm run typecheck && npm run lint`; for web/UI changes also an accessibility + responsive pass (keyboard, visible focus, AA contrast, 320/375/768/1024). Once green, commit locally: `[Steering the Scene] (6/11) Complete: The @ menu has a second namespace — mentioning a cast member sets directedAt and reads as a distinct chip.` Do not push or open a PR.*

---

### Phase 7 — Attempted vs. delivered: a cheap signal that a requirement actually landed

- **Locations:**
  - `web/backend/app/services/direction_check.py` (new, ~90 lines) —
    - `content_words(text: str) -> set[str]`: lowercase, tokenise `[a-z0-9']+`, drop a module
      stopword list, drop tokens shorter than 3 characters, truncate each to a 5-character
      prefix (crude stemming so `storms` / `stormed` / `storm` collapse).
    - `coverage(requirement: str, beat: str, *, ignore_names: list[str] = []) -> float` —
      `|req ∩ beat| / |req|`, `0.0` for an empty requirement. `ignore_names` removes the bound
      actor's own name from the requirement's word set, because a requirement reads *"Mei snaps
      back"* while Mei's own first-person beat never says "Mei" — without this every in-voice
      delivery under-scores.
    - `reached(requirement, beat, *, threshold, ignore_names) -> bool`.
  - `web/backend/app/core/config.py` + `.env.example` + `docs/deployment.md` —
    `DIRECTION_COVERAGE_THRESHOLD` (float, default `0.5`) and `DIRECTION_MAX_ATTEMPTS`
    (int, default `2`).
  - `web/backend/app/agents/direction_agent.py` — `DirectionRequirement` gains
    `attempted: bool = False`, `delivered: bool = False`, `attempts: int = 0`; `satisfied`
    becomes a read-only property returning `delivered` so nothing that reads it breaks.
    `SceneDirection.outstanding()` returns requirements that are not `delivered` **and** have
    `attempts < DIRECTION_MAX_ATTEMPTS`; add `unconfirmed()` (attempted, not delivered,
    attempts exhausted) and `attempt(reqs)` (mark attempted, bump `attempts`). `satisfy()`
    stays, and now means *confirm delivered*.
  - `web/backend/app/services/direction_runtime.py` —
    - `attempted(tracer, ctx, direction, owed, by=…)` replaces today's `_delivered` at the
      three scheduling sites: it marks `attempted`, bumps `attempts`, and traces
      *"N part(s) of your direction are riding on this beat"*.
    - `confirm(tracer, ctx, direction, owed, beat_text, by=…)` is called **after** the beat,
      with the text the beat actually emitted: it runs `direction_check.reached` per
      requirement and marks `delivered` only for those that pass, tracing the same
      `direction` step shape the client's `applyDirection` reducer already folds
      (`data.delivered` = the confirmed texts) plus a new `data.unconfirmed` list.
    - A beat that produced **no text at all** (`_beat_or_skip` returned `played=False`, or
      `_narrator_interstitial` returned `False`) skips `confirm` entirely — the requirement
      simply stays outstanding. This alone fixes diagnosis cause 1 without any heuristic.
  - `web/backend/app/services/turn_engine.py` — the three call sites (puppet ~665,
    narrate ~924, speak ~993) and the forced-schedule site (~778) split into
    `attempted(...)` before and `confirm(...)` after. `_generate_speaker` /
    `_beat_or_skip` / `_narrator_interstitial` in `beat_runner.py` must return the beat's
    **emitted text** so `confirm` has something to score — they already accumulate it
    (`_LiveSegment.text`); widen their return tuple rather than re-reading the DB.
  - `web/backend/app/services/turn_engine.py` — the closing trace (~1074) reports three
    counts: delivered, unconfirmed, undelivered.
  - Pacing fix (diagnosis causes 4 and 5), same phase because it is the same code:
    replace the fixed `direction.for_actor(actor.id)[:1]` and `for_actor(None)[:1]` slices with
    a `pace(owed, remaining_beats)` helper in `direction_runtime.py` that takes
    `max(1, ceil(len(owed) / max(1, remaining)))` — one per beat when there is room, more only
    when the budget forces it. `open_limit` at line 616 uses the same helper instead of the
    all-or-one `None`/`1` switch.
  - `web/frontend/features/story-player/turn-stream.ts` — `DirectionItem` gains
    `state: "outstanding" | "attempted" | "delivered"`; `applyDirection` folds
    `data.unconfirmed` into `attempted`.
  - `web/frontend/components/feature/DirectionChecklist.tsx` — a third glyph/label for
    `attempted` (`◐`, "the scene may not have reached this"), colour-independent as the existing
    two are.
  - `docs/api-contract.md` (the `direction` trace step's `data` shape) and `docs/data-flow.md`.
  - Tests: `utils/tests/backend/services/test_direction_check.py` (coverage arithmetic, the
    name-stripping rule, the empty-requirement guard, the threshold boundary),
    `utils/tests/backend/services/test_direction_delivery.py` (a beat that returns no text
    leaves its requirement outstanding; a beat whose prose covers the requirement confirms it;
    a beat whose prose does not marks it attempted and retries once, then stops),
    `utils/tests/backend/api/test_play_turn_direction.py` additions (the closing trace reports
    three counts), and co-located `DirectionChecklist.test.tsx` + `turn-stream.test.ts`.
- **Rationale:** This is the owner's highest priority in the plan, and it is the half of the
  fix that costs nothing: no extra LLM call, no network, one pure function. It must land before
  carry-over (Phase 8), because carrying over a requirement is only meaningful once "not
  delivered" means something more honest than "the beat failed and we ticked it anyway".
- *Action: Run the validation for this phase — `uv run pytest` (the full backend suite; the direction paths are widely covered) and, from `web/frontend`, `npm test -- DirectionChecklist turn-stream` plus `npm run typecheck`; for web/UI changes also an accessibility + responsive pass (keyboard, visible focus, AA contrast, 320/375/768/1024). Once green, commit locally: `[Steering the Scene] (7/11) Complete: A requirement is confirmed delivered by the prose that landed, not by being put in a prompt, and a long direction paces against the real budget.` Do not push or open a PR.*

---

### Phase 8 — Aim a requirement at one character, and carry the rest forward

- **Locations:**
  - **The explicit target (diagnosis causes 2 and 3).**
    - `web/backend/app/schemas/play.py` — new `TurnDirective(CamelModel)` with
      `text: str` and `actor_id: str | None = None`; `TurnRequest` gains
      `directives: list[TurnDirective] = Field(default_factory=list)`. When `directives` is
      non-empty the engine uses them **verbatim** and does **not** call
      `direction_agent.parse` — the player already said what and who, so spending an LLM call
      to re-guess it is both slower and worse.
    - `web/backend/app/agents/direction_agent.py` — `DirectionRequirement` gains
      `pinned: bool = False`; `from_directives(items, cast_ids) -> SceneDirection` builds a
      direction directly from the request (dropping any `actor_id` not in the cast).
      `rebind()` skips `pinned` requirements — a target the player set is never silently
      re-owned by the narrator. A pinned requirement whose actor is **not present** is marked
      `blocked` (a new field) rather than rebound.
    - `web/backend/app/services/direction_runtime.py` — a `blocked` requirement is reported on
      its own `direction` trace step (*"Mei is not in the scene — this part is waiting"*),
      is excluded from `outstanding()` for scheduling purposes, and is carried over (below).
      In Phase 9 this is the exact hook that offers to bring the character in.
    - `web/frontend/lib/events.ts` — mirror `directives` on `TurnRequestBody`.
    - `web/frontend/components/feature/DirectionRow.tsx` — the direction textarea's content is
      split into directives on send: each **line** of the box is one directive, and a `@Cast`
      mention on that line pins its `actorId` (resolved via `mentions.stripMentions`'s
      `castIds`, per line). A line with no cast mention sends `actorId: null`. Show the
      resolved target as a small inline chip at the end of each line's row in the box's
      helper area, so the player can see what was understood before sending. When the box is a
      single free-prose paragraph with no mentions, send `directives: []` and let the backend
      parse it exactly as today — nothing regresses for a player who ignores the feature.
  - **Carry-over (diagnosis cause 6).**
    - `web/backend/app/models/session.py` — `PlaySession.standing_direction: Mapped[dict | None]`
      (`JSONColumn`, `nullable=True`, default `None`). **New nullable column → no Alembic
      migration**; `core/bootstrap._reconcile_additive_columns` adds it at preflight.
    - `web/backend/app/services/direction_runtime.py` — `load_standing(session)` and
      `save_standing(db, session, direction)`. At turn start the standing items are merged
      **ahead of** this turn's new requirements (oldest debt first), capped at
      `direction_agent.MAX_REQUIREMENTS`. At turn end everything not `delivered` is written
      back with a `fromTurn` seq; an empty list clears the column to `None`.
    - `web/backend/app/schemas/play.py` — `SessionHistoryResponse` gains
      `standing_direction: list[StandingItem]` so a resumed scene can show the debt.
    - `web/backend/app/routes/play.py` — `POST /{scenario_id}/sessions/{session_id}/standing-direction`
      taking `{"itemIds": [...] | null}`: dismiss the named items, or `null` to clear all.
      Returns the remaining list. This is the player's "no, forget that" control, and it must
      exist — a debt the player cannot cancel is a bug, not a feature.
    - `web/frontend/lib/api.ts` — `clearStandingDirection(scenarioId, sessionId, itemIds)`.
    - `web/frontend/lib/events.ts` — `SessionHistory.standingDirection`.
    - `web/frontend/features/story-player/useScenePlay.ts` — resume seeds `direction` state
      from `history.standingDirection`; a dismiss handler calls the endpoint optimistically.
  - **The visible record.**
    - `web/frontend/components/feature/DirectionChecklist.tsx` — a "Carried over" badge on any
      item with a `fromTurn`, a per-item dismiss button (24×24 minimum target, labelled
      *"Stop asking for …"*), and the existing `aria-live` summary extended to
      *"N of M delivered, K carried over"*.
    - `web/backend/app/services/session_export.py` — `group_turns` adds a per-turn `direction`
      block (`asked` / `delivered` / `unconfirmed` / `carried`) built from that turn's
      `direction` trace rows; `render_markdown` prints it under the diagnostics heading.
  - `docs/api-contract.md` (the `directives` field, the new endpoint, the history response),
    `docs/data-flow.md` (a "Scene direction lifecycle" subsection under the write path),
    `docs/architecture.md` (the standing-direction column and why it is not derived).
  - Tests: `utils/tests/backend/agents/test_direction_agent.py` additions (`from_directives`,
    `rebind` skips pinned, blocked marking), a new
    `utils/tests/backend/services/test_direction_carryover.py` (an undelivered requirement is
    written to the session and reappears on the next turn; delivering it clears it; the cap
    holds), a new `utils/tests/backend/api/test_play_turn_directives.py` (explicit directives
    bypass `direction_agent.parse` — assert the LLM transport is never called for it) and
    `utils/tests/backend/api/test_play_sessions.py` additions for the dismiss endpoint;
    co-located `DirectionChecklist.test.tsx`, `DirectionRow.test.tsx` and `useScenePlay.test.ts`.
- **Rationale:** Phase 7 made "not delivered" mean something true; this phase makes it *act*.
  Together they are the answer to "right now it forgets what happens so often": the target is
  stated rather than guessed, a target the player set cannot be quietly taken away, and a
  requirement the turn could not reach outlives the turn instead of disappearing with it.
- *Action: Run the validation for this phase — `uv run pytest` (full backend suite) and, from `web/frontend`, `npm test -- DirectionChecklist DirectionRow useScenePlay turn-stream api` plus `npm run typecheck && npm run lint`; for web/UI changes also an accessibility + responsive pass (keyboard, visible focus, AA contrast, 320/375/768/1024). Once green, commit locally: `[Steering the Scene] (8/11) Complete: A requirement can be aimed at one character from the UI, is never silently re-owned, and is carried forward until delivered or dismissed.` Do not push or open a PR.*

---

### Phase 9 — Bring someone into the scene mid-play, with manual approval

- **The approval rule, stated first.** After this phase **the AI never introduces a character
  on its own initiative.** There is no planner action that brings someone in. Every arrival is
  either a direct player action (the cast rail's "Bring into the scene") or a **request** the
  player accepts or declines. Three things can raise a request, none of which costs an extra
  LLM call: a pinned directive whose actor is absent (Phase 8's `blocked` state), a plain
  longest-first **name match** of the direction text against the storyline's absent character
  names (the same matcher `stripMentions` already uses, run server-side), and the
  "someone arrives" verb in Phase 10 naming an absent character explicitly.
- **Locations:**
  - `web/backend/app/services/assembler.py` — `_build_cast` (line ~297) unions
    `scenario.cast_ids` with any character id carrying a `character_status_change` event on
    **this session** (read from the already-fetched `presence_map`), resolving each through
    `crud.get_character` and skipping ids outside the storyline. The scenario row is never
    mutated: a guest belongs to the play-through, not to the authored scene.
  - `web/backend/app/routes/play.py` — `set_presence`: the guard
    `if data.character_id not in (scenario.cast_ids or [])` widens to "is a character of this
    scenario's storyline", so a storyline character can be admitted. An id from another
    storyline is still a 404.
  - `web/backend/app/events/envelope.py` — new `CastRequestData(character_id, reason)` +
    `CastRequestEvent(type: Literal["cast_request"])`, added to the `StoryEvent` union and
    `__all__`; `web/backend/app/schemas/base.py` — `"cast_request"` added to `EventType`.
    **The mirror is updated in this same phase**: `web/frontend/lib/events.ts` gains
    `CastRequestEvent` and adds it to the `PlayEvent` union.
  - `web/backend/app/services/direction_runtime.py` — `cast_requests(db, ctx, scenario, direction)`
    returns the absent storyline characters the direction names (blocked pins first, then name
    matches), filtered to those with **no** `character_status_change` event on this session —
    so a character already declined is never asked about twice. `turn_engine.run_turn` emits one
    `cast_request` per result immediately after the opening `direction` trace, before any beat.
  - `web/frontend/features/story-player/turn-stream.ts` — `mergeFrame` folds `cast_request` into
    a new `{ kind: "castRequest", who, reason, resolved }` `SceneMessage`;
    `rehydrateFromHistory` replays it and marks it `resolved` when a later
    `character_status_change` for the same character exists.
  - `web/frontend/components/feature/CastRequestBeat.tsx` (new) + test — a centred aside in the
    transcript: *"The scene is asking for Kael."* with **Bring them in** / **Not now**. Accept →
    `setPresence(id, "present")`; decline → `setPresence(id, "departed")` with
    `reason: "declined"`. Once resolved it renders as a quiet settled line, never a live
    control.
  - `web/frontend/components/feature/TranscriptBeat.tsx` — route the new kind.
  - `web/frontend/components/feature/CastRail.tsx` — a third section, **"Elsewhere in the
    world"**, listing storyline characters that are neither in `cast_ids` nor already joined,
    each with a "Bring into the scene" button. It needs the storyline's full character list,
    which `useSceneData` already fetches via `listCharacters(storylineId)` and currently
    narrows away in `resolveScenario`; thread it through as a new
    `ResolvedScenario`-adjacent `storylineCast` prop from `StoryPlayerView`.
  - `web/frontend/features/story-player/useScenePlay.ts` — `setPresence` currently no-ops
    without a session (`if (!sid) return`). Bringing someone in before the first turn must
    work, so create the session first via the existing resume path, or disable the control with
    an explanatory title until a session exists — pick the latter (no new session-creation
    endpoint) and say so in the button's title.
  - `docs/api-contract.md` (§ Event types — the ninth type and its payload),
    `docs/data-flow.md` (§ Scene presence — guests and the approval gate),
    `docs/component-map.md` (§ Event → renderer mapping + `CastRequestBeat`),
    `CLAUDE.md`'s "8 story-event types" line becomes the correct count.
  - Tests: `utils/tests/backend/services/test_assembler.py` additions (a session-joined guest
    appears in `ctx.cast`; a foreign-storyline id does not),
    `utils/tests/backend/api/test_play_presence.py` additions (a storyline character not in
    `cast_ids` can be admitted; a foreign one is a 404), a new
    `utils/tests/backend/services/test_cast_request.py` (a direction naming an absent character
    emits exactly one `cast_request`; a second turn naming the same declined character emits
    none), and co-located `CastRequestBeat.test.tsx`, `CastRail.test.tsx`,
    `turn-stream.test.ts`.
- **Rationale:** The presence bus already accepts a manual override and is deliberately not
  bound by `can_transition` — the machinery exists. What is missing is the *framing*: the rail
  only ever offers the scenario's authored roster, and there is no way for the scene to ask.
  Building the request as an event (rather than as a planner action) is what keeps the owner's
  requirement literally true: the AI can raise a question, and only the player can answer it.
- *Action: Run the validation for this phase — `uv run pytest` (full backend suite; the envelope union is widely asserted) and, from `web/frontend`, `npm test -- CastRequestBeat CastRail TranscriptBeat turn-stream useScenePlay` plus `npm run typecheck && npm run lint`; for web/UI changes also an accessibility + responsive pass (keyboard, visible focus, AA contrast, 320/375/768/1024). Once green, commit locally: `[Steering the Scene] (9/11) Complete: The storyline's absent cast can join a scene, and any AI-raised arrival is a request the player accepts or declines.` Do not push or open a PR.*

---

### Phase 10 — One-tap direction verbs, expanded

- **The surface.** Four labelled groups on the direction row, not a flat row of five buttons:
  - **Pace** — *Push it forward* · *Slow down* · *Skip ahead* · *Cut to later*
  - **Tone** — *Escalate* · *Calm it down* · *Turn it warm* · *Turn it cold*
  - **Event** — *Someone arrives* · *An interruption* · *Something breaks* · *A revelation*
  - **Exit** — *Wrap this up* · *End the scene* · *Move the scene*
  Each verb owns a short phrasing (not a label repeated as text) that is written into the
  direction target for the player to edit — the point is to give them a sentence to argue
  with, not a command to fire.
- **Context awareness.** A verb that cannot mean anything is not offered:
  *Someone arrives* only when the storyline has cast outside the scene (the list Phase 9
  already computes) and it expands to a submenu naming them, which raises a Phase 9 request
  rather than an arrival; *End the scene* / *Wrap this up* only after 3 or more player turns in
  the session; *Move the scene* only when the storyline has more than one `Setting`.
- **Locations:**
  - `web/frontend/lib/sceneVerbs.ts` (new) + `sceneVerbs.test.ts` — the verb catalogue as data
    (`{id, group, label, text, requires?}`) and `availableVerbs(ctx)` applying the gates, where
    `ctx` is `{absentCast, settingCount, playerTurns}`. Pure, so the gating is unit-tested with
    no DOM.
  - `web/frontend/components/feature/SceneVerbBar.tsx` (new) + test — `role="toolbar"`,
    `aria-label="Direction"`, **roving tabindex** (one tab stop into the bar, Left/Right move
    between verbs, Home/End jump), each group a `role="group"` with an `aria-label`. Horizontal
    `overflow-x: auto` in its own container so it never grows the page at 320px. Activating a
    verb calls `onVerb(text)`.
  - `web/frontend/components/feature/DirectionRow.tsx` — renders `SceneVerbBar` in its slot in
    **both** modes. The verb's text is written into the direction textarea under POV and into
    the **message box** in narrator mode (where the message *is* the direction) — one concept,
    two targets, which is exactly the distinction Phase 4 put into words. After insertion, focus
    the target and **select the inserted phrase** so it can be overwritten with one keystroke.
  - `web/frontend/features/story-player/useScenePlay.ts` — expose `playerTurns` (count of
    `kind: "player" | "direction"` messages) for the Exit gate.
  - **Scenario-authored verbs.**
    - `web/backend/app/models/scenario.py` — `direction_verbs: Mapped[list | None]`
      (`JSONColumn`, `nullable=True`, default `None`). **New nullable column → no migration.**
    - `web/backend/app/schemas/scenario.py` — `direction_verbs: list[SceneVerb] = []` on
      `ScenarioBase` / `ScenarioRead`, `| None` on `ScenarioUpdate`, with
      `SceneVerb(label: str, group: Literal["pace","tone","event","exit"], text: str)` and a
      cap of 8 entries.
    - `web/frontend/lib/types.ts` — mirror `directionVerbs` on `Scenario` / `ResolvedScenario`.
    - `web/frontend/components/feature/ScenarioForm.tsx` — a small repeatable editor for the
      scene's own verbs (label + group + phrasing), following the `VoiceSamplesEditor` pattern
      already in the repo.
    - Authored verbs are appended to their group after the built-ins.
  - `docs/api-contract.md` (the scenario shape), `docs/component-map.md`,
    `docs/design-system.md` (the toolbar's chip treatment if it introduces one),
    `docs/routes.md` only if the scenario editor gains a section.
  - Tests: `sceneVerbs.test.ts` (each gate), `SceneVerbBar.test.tsx` (roving tabindex, group
    labelling, activation writes and selects), `DirectionRow.test.tsx` (the narrator-mode target
    is the message box, the POV target is the direction box),
    `ScenarioForm.test.tsx` (authored verbs round-trip), and
    `utils/tests/backend/api/test_scenarios.py` additions (the column round-trips, the cap and
    the group enum are enforced).
- **Rationale:** The owner's complaint is that this surface is boring and unread, so it is built
  last, on top of everything that makes a verb worth tapping: a direction row that always
  exists (Phase 4), a turn that can be direction-only (Phase 3), an arrival that is a request
  (Phase 9), and a requirement that is actually tracked (Phases 7–8). `docs/checklist.md`
  already names `end_scene` and `move_scene` as buildable on the presence bus; the Exit group
  is where they surface.
- *Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api utils/tests/backend/data` and, from `web/frontend`, `npm test -- sceneVerbs SceneVerbBar DirectionRow ScenarioForm useScenePlay` plus `npm run typecheck && npm run lint` and `node utils/scripts/check_frontend_css.mjs`; for web/UI changes also an accessibility + responsive pass (keyboard, visible focus, AA contrast, 320/375/768/1024, plus the roving-tabindex path with a keyboard only). Once green, commit locally: `[Steering the Scene] (10/11) Complete: A grouped, context-aware, keyboard-operable direction-verb bar with scenario-authored verbs.` Do not push or open a PR.*

---

### Phase 11 — Close structural gap G5, reconcile the docs

- **Locations:**
  - **`outcome` — wire it, with a player-facing name.** `TurnRequest.outcome` already makes the
    turn open with a fuller "progression" narration that plays a chosen branch out
    (`turn_engine.py` ~line 613); the UI has never sent it, so that behaviour is dead code
    reachable only by tests. Give it the name **"Play it out"**: `branch_choices` suggestions
    already round-trip an `outcome` through `branchOptionsToChoices`, so add a second action to
    each suggestion chip in `web/frontend/components/feature/TranscriptBeat.tsx` — the primary
    click still writes the text into the composer for editing (unchanged), and "Play it out"
    submits it immediately as a **direction-only** turn (Phase 3) with `outcome` set.
    `web/frontend/features/story-player/useScenePlay.ts` gains `playOut(choice)`;
    `web/frontend/lib/events.ts` drops the "(legacy)" wording from `TurnRequestBody.outcome`.
    One sentence a player cares about: *"skip the typing and let the scene play this choice
    out."*
  - **`mode` — do not expose it.** It reaches exactly one place in the engine (the `turn` trace
    payload at `turn_engine.py:451`) and changes nothing. Mark it deprecated and inert in the
    `TurnRequest` docstring, in `web/frontend/lib/events.ts`, and in `docs/api-contract.md`;
    keep accepting it so no existing caller breaks; build no UI. Record the decision in
    `docs/architecture.md` so the next reader does not re-litigate it.
  - **`docs/checklist.md`** — remove the items this plan closed: *"The scene direction is not
    persisted"*, *"A guidance-only turn cannot be sent"*, *"Nothing verifies that a requirement
    was actually met"* (rewrite rather than delete — the LLM verifier is still rejected; what
    exists now is a lexical signal with a stated failure mode), *"A direction longer than the
    scene's turn cap is compressed, not spread"* (now paced), and *"`end_scene` / `move_scene`
    verbs"*. Add the three new deferrals from §2: the unmeasured coverage threshold, inline
    mention chips, standing-direction expiry.
  - **`docs/research/OPEN_QUESTIONS.md`** — add the coverage-threshold sweep as an open
    question, with the protocol sketch (hand-labelled direction/beat pairs, precision and recall
    per threshold, per-run rows and no aggregate over a partial failure).
  - **`CLAUDE.md`** — the "8 story-event types" fact line becomes the correct count including
    `character_prose` and the new `cast_request`; the `services/` table gains `beat_runner.py`,
    `direction_runtime.py`, `turn_setup.py`, `direction_check.py`; the `docs/plans/` count.
  - **`docs/documentation.md`** — the status paragraph on directing the scene.
  - Tests: `utils/tests/backend/api/test_play_turn.py` addition (an `outcome`-only turn opens
    with the progression narration) and co-located `TranscriptBeat.test.tsx` +
    `useScenePlay.test.ts` for "Play it out".
- **Rationale:** G5 named three backend-supported fields the UI never sends. Phase 6 closed
  `directedAt`; this phase closes `outcome` with a name a player would recognise and closes
  `mode` by writing down, once, that it will not be exposed — which is a decision, not an
  omission. The docs sweep belongs in the same commit as the last behaviour change, per the
  repo's documentation rule.
- *Action: Run the validation for this phase — `uv run pytest` (full backend suite) and, from `web/frontend`, `npm test` (full suite) plus `npm run typecheck && npm run lint`; for web/UI changes also an accessibility + responsive pass (keyboard, visible focus, AA contrast, 320/375/768/1024). Once green, commit locally: `[Steering the Scene] (11/11) Complete: Wired outcome as "Play it out", documented mode as inert, and reconciled the checklist and docs.` Do not push or open a PR.*

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Direction restore | The persisted `guidance` comes back into the composer on reload | `web/frontend/features/story-player/{turn-stream,useScenePlay}.ts` |
| Direction in exports | Per-turn asked / delivered / unconfirmed / carried block | `web/backend/app/services/session_export.py` |
| Direction module | Direction machinery lifted out of the beat loop; every module ≤ 800 lines | `web/backend/app/services/direction_runtime.py` |
| Direction-only turns | Relaxed validation consumed; every empty-text assumption fixed | `web/backend/app/services/{turn_engine,turn_setup,events_store,session_export}.py`, `web/frontend/features/story-player/{useScenePlay,scene-data,turn-stream}.ts` |
| Direction row | Always present — narrator strip / POV textarea | `web/frontend/components/feature/DirectionRow.tsx` |
| Mention strip fix | The name survives; only the `@` is dropped | `web/frontend/features/story-player/mentions.ts` |
| Mention removal | `removeMention` for the chip "×", now a separate operation | `web/frontend/features/story-player/mentions.ts` |
| Cast mention namespace | `kind: "doc" \| "cast"`, grouped menu, distinct chips, sets `directedAt` | `web/frontend/features/story-player/mentions.ts`, `web/frontend/components/feature/{MentionMenu,Composer}.tsx` |
| Delivery check | Deterministic lexical coverage — no LLM call | `web/backend/app/services/direction_check.py` |
| Attempted vs delivered | Split flag, retry cap, budget-aware pacing | `web/backend/app/agents/direction_agent.py`, `web/backend/app/services/direction_runtime.py` |
| Explicit actor target | `TurnRequest.directives`, pinned requirements immune to `rebind` | `web/backend/app/schemas/play.py`, `web/backend/app/agents/direction_agent.py` |
| Carry-over | `PlaySession.standing_direction` (nullable JSON, no migration) + dismiss endpoint | `web/backend/app/models/session.py`, `web/backend/app/routes/play.py` |
| Owed-vs-delivered UI | Three states, carried-over badge, per-item dismiss | `web/frontend/components/feature/DirectionChecklist.tsx` |
| `cast_request` event | Ninth story-event type + hand-mirrored TS contract | `web/backend/app/events/envelope.py`, `web/backend/app/schemas/base.py`, `web/frontend/lib/events.ts` |
| Approval affordance | Accept / decline in the transcript; guests in the cast rail | `web/frontend/components/feature/{CastRequestBeat,CastRail}.tsx` |
| Session-scoped guests | `_build_cast` unions the scenario roster with session joiners | `web/backend/app/services/assembler.py` |
| Verb catalogue | Data + context gates, pure and unit-tested | `web/frontend/lib/sceneVerbs.ts` |
| Verb bar | Grouped `role="toolbar"` with roving tabindex | `web/frontend/components/feature/SceneVerbBar.tsx` |
| Authored verbs | `Scenario.direction_verbs` (nullable JSON) + editor | `web/backend/app/models/scenario.py`, `web/frontend/components/feature/ScenarioForm.tsx` |
| G5 close | `outcome` wired as "Play it out"; `mode` documented inert | `web/frontend/components/feature/TranscriptBeat.tsx`, `web/backend/app/schemas/play.py` |
| Backend tests — export | Guidance + direction block in JSON and Markdown | `utils/tests/backend/services/test_session_export_direction.py` |
| Backend tests — direction-only | Stream, 400 on empty, row + buffer behaviour | `utils/tests/backend/api/test_play_turn_direction_only.py` |
| Backend tests — coverage | Arithmetic, name stripping, threshold boundary | `utils/tests/backend/services/test_direction_check.py` |
| Backend tests — delivery | No-text beat stays outstanding; confirm/retry/stop | `utils/tests/backend/services/test_direction_delivery.py` |
| Backend tests — carry-over | Persist, reappear, clear, cap | `utils/tests/backend/services/test_direction_carryover.py` |
| Backend tests — directives | Explicit targets bypass the parse call; pins survive `rebind` | `utils/tests/backend/api/test_play_turn_directives.py`, `utils/tests/backend/agents/test_direction_agent.py` |
| Backend tests — cast request | Emitted once, never re-asked after a decline | `utils/tests/backend/services/test_cast_request.py` |
| Backend tests — guests | Session-joined cast resolves; foreign ids do not | `utils/tests/backend/services/test_assembler.py`, `utils/tests/backend/api/test_play_presence.py` |
| Backend tests — verbs | `direction_verbs` round-trip, cap, group enum | `utils/tests/backend/api/test_scenarios.py` |
| Frontend tests — mentions | Name survives; cast/doc split; ordering; removal | `web/frontend/features/story-player/mentions.test.ts` |
| Frontend tests — direction row | Mode switch, labelling, verb target | `web/frontend/components/feature/DirectionRow.test.tsx` |
| Frontend tests — verb bar | Gates, roving tabindex, insert-and-select | `web/frontend/lib/sceneVerbs.test.ts`, `web/frontend/components/feature/SceneVerbBar.test.tsx` |
| Frontend tests — checklist | Three states, carried badge, dismiss | `web/frontend/components/feature/DirectionChecklist.test.tsx` |
| Frontend tests — cast request | Accept / decline / resolved rendering | `web/frontend/components/feature/CastRequestBeat.test.tsx` |
| Frontend tests — play hook | Direction-only send, resume restore, `directedAt`, `playOut` | `web/frontend/features/story-player/useScenePlay.test.ts` |
| Docs | Contract, data flow, components, architecture, checklist, research | `docs/{api-contract,data-flow,component-map,architecture,structure,design-system,documentation,checklist}.md`, `docs/research/OPEN_QUESTIONS.md`, `CLAUDE.md` |
