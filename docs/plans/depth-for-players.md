# Depth for Players

> **SHIPPED — 12/12 phases, 2026-08-22.** Commit series `59b10a9 … HEAD` on branch
> `play-experience`. What follows this block is the plan as written; the record below is what
> actually happened and where it differs.

## 0. Completion record

### What shipped

The scene became the place a player tunes how a turn runs. A **per-turn override envelope**
(`TurnOverrides` → `turn_settings.resolve`) sits under everything: any control can be **pinned**
to the scene or spent on the next message and then spring back, with the scope stated in text
on each row. Over it, a **named preset** answers the question a player actually has ("what kind
of scene is this") instead of the three they have to be taught to ask.

Four new controls, each with its consequence written at the point of use: **turn planning off**
(the model-free `services/beat_order`, the largest latency lever in the app, whose copy states
what it costs — no register, no mid-turn narration, no exits), a **pinned register** for one
message, **tie scope** over the story graph, and a per-character **word-choice** dial that
biases `top_p` and nothing else. The header's **☰ Scene** menu reaches the writing prompts,
each badged with the layer its live value comes from.

### What the code disagreed with, and won

Five of the twelve phases were written against a repository that had moved. Each was checked
rather than implemented:

- **Phase 2's re-export** would have been dead code — the private names it named
  (`_relationship_note`, `_apply_stat_change`) do not exist; the split landed with those
  helpers public on their owners. The module map went into the docstring and `docs/structure.md`
  instead.
- **"A nullable column needs no Alembic migration"** is false here.
  `test_alembic.py::test_baseline_columns_match_create_all` enforces it, and caught all four
  new columns.
- **Phase 8's "the register still leads"** does not hold at ±2: the dial's full range (0.12)
  is wider than the register span (0.10). The test pins the relationship that *is* true and a
  second one documents the edge.
- **Phase 11's central premise was obsolete.** Owner decision D-1 had already made play
  session-scoped, so `state_update` never touched the authored value. The real hazard is
  `carry_forward`, and it is narrower — which is what `CharacterStat.baseline` now guards.
- **Phase 11's "start fresh" checkbox was not built**, deliberately: nothing could carry (see
  below), so it would have been a control that silently does nothing — which this plan forbids
  elsewhere.

### Defects found and fixed

- `crud.create_scenario` and `create_character` enumerate their columns, so `scenePreset`,
  `plannerMode` and `looseness` were silently dropped on **create** while PATCH worked.
- `StatDefinition.carry_over` was readable by `carry_forward` but present in no schema and no
  insert, so **nothing could ever carry** — D-1's "reset, with an opt-in carry" had no way to
  opt in.
- `aria-pressed` on `role="menuitem"` is invalid ARIA; menu toggles are `menuitemcheckbox`.
- Menu-row hints were concatenating into the accessible **name** ("Turn Inspectorwhat the
  scene read…").
- Accent text on the menu ground fails AA (3.67:1 Slate); the pin footer and scope suffix use
  `--ink`, and `check_contrast.py` now carries the pair as non-text.
- The **`world` tie scope did nothing on a dense graph** — the in-scene ties filled the 8-line
  budget and the off-scene clause was always trimmed. Off-scene ties now hold a reserved share.
- The **config popover grew unreachable**: seven controls, 1004px tall at 320×720, top edge at
  -386px, not scrollable. Bounded to the viewport in Phase 12.

### What is deliberately still open

Recorded in `docs/checklist.md`, not implied away: the **`world` tie scope is a product
question** awaiting a human decision (shipped non-default); planning-off's latency and quality
trade, the looseness step size, and the value of a pinned register are all **unmeasured**;
`carry_over` has no authoring UI; scene presets are built-in only; `TurnContext.subgraph`,
`presence_casting` and `secret_reachability` all remain unused, and nothing has ever written a
`Secret` node.

### Validation at the close of the plan

`uv run pytest` — **1653 passed**. `npm test` — **1280 passed**, 130 files. `npm run typecheck`
clean; `npm run lint` 0 errors. `check_contrast.py` and `check_frontend_css.mjs` both pass.
Live pass at 320 / 375 / 768 / 1024: no horizontal page overflow, `scrollHeight ===
clientHeight` at every width, every visible target ≥44px tall under `pointer: coarse`, and the
config panel fits and scrolls. Focus indication verified **structurally** against the served
stylesheet (the bare `:focus-visible` rule is unlayered and no new control suppresses it)
because `document.hasFocus()` is false in this environment — the standing constraint recorded
in the checklist. The scene header still overflows **17px at 320** (down from 45px);
`docs/plans/reach.md` Phase 4 owns the durable fix and that bullet's removal.

---

## 1. Introduction

Mytheca already contains most of the machinery a demanding player would want: a three-layer
writing-prompt override system (`agents/prompt_registry.py`), a per-beat *register* the planner
assigns and that drives voice-sample selection and the sampler, a per-scene play-control block on
`Scenario`, a Neo4j story graph with real relationship edges, and a model-free beat picker
(`planner_agent._fallback_beat`) that is a complete substitute for the planner nobody can reach.
Almost none of it is legible or reachable from the scene the player is actually in. The prompt
overrides are buried in an authoring surface; the register is decided for the player and never
shown; every scene-config change silently and permanently rewrites the `Scenario` row; the graph
touches the prompt through exactly one narrow call; and two prompt keys are editable in Options
while doing nothing at all.

This plan surfaces that machinery rather than building more of it. The guardrail is that **more
customisability is the goal and more sliders are not the way to get it**: the scene-config popover
gains *fewer* free-floating numbers and *more* named bundles, scoped controls, and one-line
statements of consequence. Concretely it adds a per-turn override envelope on `TurnRequest` (so a
control can apply to the next turn and spring back), named scene presets over the existing
controls, a pin affordance that makes "for now" versus "for this scene" explicit, a play-time
entry point to the prompt overrides with per-layer attribution, a player-pinned register, a
per-character voice-looseness bias, a switch that turns the planner off and replaces it with the
deterministic order the fallback already implements, a bounded first real use of the story graph
for scope, and an honest answer to what stats do between scenes. Every new control is reversible,
explains its consequence where it is used, is correctly scoped, survives a reload where that is
meaningful, exists at 375 px, and adds no LLM call to the turn path — the planner switch *removes*
one.

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

- **Where a preset lives.** Assumption: a **built-in table on the backend**, `web/backend/app/content/scene_presets.py`, following the existing `content/graph_registry.py` convention ("this is *data*, not engine logic"), served read-only by `GET /api/options/scene-presets`, plus a nullable `Scenario.scene_preset` column recording which preset a scene is on. Not a frontend constant (the values must obey the same Pydantic bounds as `ScenarioUpdate`, which live on the backend), and not a storyline-authored set (that is a Library authoring surface this plan does not build — it is recorded as a deferral).
- **Pin default.** Assumption: **pinned is the default**, i.e. today's behaviour is unchanged for a player who never touches a pin. Unpinning a control means "this turn only".
- **Whether an unpinned value survives a reload.** Assumption: no, and that is correct rather than a compromise — a value scoped to the next turn is discarded by a reload exactly as the composer's unsent text is. The *persisted* (pinned) values are the ones that must survive, and they already do. This is stated in the control's own copy.
- **Whether a preset may switch the planner off.** Decided: **no**. A preset that silently disables the faculty deciding who speaks would violate the "explains its consequence at the point of use" rule. Planner mode stays a control the player flips deliberately, and the `interrogation` preset ships with the planner **on**.
- **Whether to delete or hide the two dead director prompt keys** (item 4). Decided: **hide**, do not delete. `docs/checklist.md` records, under *Research record — deliberate gaps*: "**Do not delete the dead director code while EXP-2026-08-001 is open** — it is the baseline arm." The planner-vs-director ablation is precisely the experiment that would justify or retire the planner, which is what item 6 is about. Deleting the baseline arm to tidy the Options menu would destroy the measurement. The keys leave the UI; the functions and their tests stay.
- **What replaces the planner when it is off** (item 6). Decided: **not** `director_agent.who_is_up` — reviving it contradicts the decision above, and it is an LLM call, so it would not deliver the latency the switch exists for. The replacement is `planner_agent._fallback_beat`, promoted to a public `planner_agent.scripted_beat`, wrapped in a new `services/beat_order.py` that adds round-robin continuation. Zero LLM calls.
- **How the looseness dial reaches the model.** Assumption: it composes with the existing `_REGISTER_SAMPLER` row by nudging **`top_p` only**, bounded to ±0.06 total, clamped to `[0.70, 0.98]`. It never touches `frequency_penalty`/`presence_penalty`, which stay `0.0` at every register.

### Findings from reading the code that change the shape of the work

These are not assumptions; they were verified while writing this plan and each one moves a phase.

- **Nothing in the codebase ever creates a `Secret` node.** `graph_writer` writes `Character`/`Setting` nodes, `present_at` edges, relationship edges and `Consequence` records; a repo-wide search for a `Secret` write returns nothing. Therefore `graph_reader.secret_reachability` cannot return a non-empty list on any world that exists, and "surface what a character knows" — the obvious first use of the graph — is **empty in practice**. Item 7 is built on relationship edges instead, which *are* populated (`relationships.ensure_seeded` from bios, plus the cold-path `relationship_update` writes).
- **A character's authored starting stats are destroyed by the first scene that changes them.** `CharacterStat` is keyed `(character_id, key)` with no session or scenario scope and no snapshot; `stats.set_character_stats` overwrites in place, and the turn engine calls it on every accepted `state_update`. So today's de-facto stat lifecycle is not "undecided" — it is **permanent global carry-over across every scenario and every play-through**, decided by accident, with the authored baseline unrecoverable. A second play-through of the *same* scene starts wherever the first one left off. Phase 11 records the baseline before it is lost, which is the prerequisite for any of the lifecycle options below.
- **`StatDefinition.visibility` is honoured nowhere.** It is stored, it round-trips through the API, and neither `stat_render`, the transcript, the Director rail nor the dossier reads it. Every stat is public today regardless of what the author set.
- **`turn_engine.py` is 1 986 lines** — 2.5× the 800-line ceiling — and `run_turn` spans ~400–1203. Four of this plan's phases edit `run_turn`. Splitting it is therefore Phase 2, before any seam lands, not a cleanup afterwards.

### Complex gaps — human intervention required

1. **Should off-scene relationship ties be offered to the model at all, and should they ever be the default?** Phase 10 builds a three-stop tie scope (Addressed / Scene / World). The *World* stop expands one hop past the scene: the speaker's graph edges to storyline characters who are **not** in this scenario. That is real, populated data and it is the first genuine use of the knowledge graph for scope. The risk is equally real: a character can then reference someone the player has never met and whose existence the scene never established, which reads as the model hallucinating even though the fact came from the author's own graph. Options: **(a)** ship all three stops with *Scene* as the default and *World* opt-in (the plan's recommendation); **(b)** ship only Addressed/Scene and leave the off-scene template unwired; **(c)** ship *World* as the default on the theory that a world should feel larger than its cast list. **Human intervention is needed to answer this question.**
2. **What should stats do between scenarios?** The options and their consequences are laid out in Phase 11. **(A) Reset per play-through** — every scene starts from the authored values; scenes are independent and the graph carries all continuity. **(B) Persist globally** — today's accidental behaviour, made deliberate; a character killed in one scene is dead in every scene, and replaying a scenario is never fresh. **(C) Per-stat carry-over flag** (`StatDefinition.carry_over`) with per-session values — vitals reset, standing carries; the most faithful model and the most expensive, because it needs session-scoped values, i.e. a new table and a change to every read and write path. **(D) Storyline-level default with a per-scenario opt-out.** The plan **recommends (C)**, implements only its prerequisite (the recoverable baseline) and a player-facing "Start fresh" reset, and does not commit the schema. **This is the same question as `docs/plans/control-over-the-record.md` §2 gap H-1** ("Stat lifecycle across forked play-throughs"), which reaches it from the other side: branching creates two play-throughs of one scenario that disagree about a character's health, and that plan reconciles stats to whichever session is open. Option **(C)** answers both. Answer them together. **Human intervention is needed to answer this question.**
3. **Should a `hidden`-visibility stat be invisible to the player, or visible as an unnamed movement?** Options: **(a)** omit it entirely from every player surface (the plan's recommendation; the event is still persisted so the Inspector and the export can show it); **(b)** render "something shifted" without the key or the number, which tells the player a hidden system exists; **(c)** treat `hidden` as author-only metadata and keep showing everything, i.e. delete the field. **Human intervention is needed to answer this question.** Phase 11 implements (a) and puts (b)/(c) on the checklist.

---

## 3. Hierarchical Step-by-Step Instructions

Twelve phases. Each is independently committable and leaves the app working. Phases 1–2 are
prerequisites for everything after them; 3 enables 4–7 and 10; the rest are ordered by
dependency, not by importance.

---

### Phase 1 — Hide the two dead director prompt keys

**Locations**

- `web/backend/app/agents/prompt_registry.py` — add a `hidden: bool = False` field to the `PromptSpec` dataclass; set `hidden=True` on the `DIRECTOR_WHO_IS_UP` and `DIRECTOR_RERANK` entries in `PROMPT_REGISTRY`; add a `visible_specs()` helper beside `keys()`. `keys()`, `default()` and `resolve_prompts()` are **unchanged** — hidden keys still resolve, so a stored override neither disappears nor raises.
- `web/backend/app/services/settings_store.py` — `get_prompts()` builds its `catalog` from `prompt_registry.visible_specs()` rather than `PROMPT_REGISTRY`. `set_prompts_overrides()` keeps accepting every registry key (a stored value for a dead key is inert; refusing it would be a behaviour change for no gain).
- `web/backend/app/agents/director_agent.py` — update the module docstring and the `who_is_up`/`rerank` docstrings to say plainly: superseded by `planner_agent.plan_beats`, retained **only** as the baseline arm of EXP-2026-08-001, not on the turn path, prompt keys hidden from the UI.
- `docs/checklist.md` — rewrite the *Dead code on the turn path* bullet: the decision is recorded (hidden, not deleted), with the reason (the open experiment) and the trigger for revisiting (EXP-2026-08-001 reaching a verdict).
- `docs/api-contract.md` §*Options / Settings Shape* — note that the prompts catalog exposes only the prompts that are actually consumed, and that hidden keys still resolve for stored overrides.
- Tests: `utils/tests/backend/agents/test_prompt_registry.py` (the two keys are hidden; `keys()` still contains them; `resolve_prompts` still honours an override for them), `utils/tests/backend/api/test_settings.py` (the `/api/options` catalog omits both, and every remaining catalog entry is one an agent reads). `utils/tests/backend/agents/test_director_agent.py` is **unchanged** — that is the point.

**Rationale** — This is the smallest self-contained item, it closes a standing checklist question, and it must be settled *before* Phase 6 designs the planner switch, because "revive `who_is_up`" and "delete `who_is_up`" are the two options Phase 6 has to rule out. Doing it first means Phase 6 inherits a decision instead of relitigating one. No frontend change is required: the Options › Prompts tab, `PromptOverridesModal` and `PromptOverridesEditor` are all catalog-driven.

*Action: Run the validation for this phase — `uv run pytest utils/tests/backend/agents/test_prompt_registry.py utils/tests/backend/agents/test_director_agent.py utils/tests/backend/api/test_settings.py`, then the full `uv run pytest`; plus `npm test` in `web/frontend` for `PromptOverridesEditor`/`PromptsTab`. Once green, commit locally: `[Depth for Players] (1/12) Complete: Hid the two dead director prompt keys from the catalog without deleting the experiment's baseline arm.` Do not push or open a PR.*

---

### Phase 2 — Confirm the turn-engine split, and re-export what this plan needs

> **Ownership.** The `turn_engine.py` split is **owned by `docs/plans/control-over-the-record.md`
> Phase 3**, which lands first in this program and produces `turn_emit.py` (`Emitter` /
> `LiveSegment` / `Tracer`), `beat_runner.py` (the beat-production helpers *and* the
> presence/relationship/stat appliers), `turn_setup.py` (`prepare_turn`) and, if needed,
> `turn_finalize.py`. `docs/plans/steering-the-scene.md` Phase 2 then lifts the direction helpers
> (`delivered`, `direction_lead`, `name_of`, `plan_still_valid`) into `direction_runtime.py`.
> **Do not invent a second layout.** Everywhere this plan later says `turn_beats.py` or
> `turn_effects.py`, read **`beat_runner.py`**; everywhere it says `turn_emitter.py`, read
> **`turn_emit.py`**.

**Locations**

- `web/backend/app/services/` — **verify only.** Confirm `turn_emit.py`, `beat_runner.py`,
  `turn_setup.py` and `direction_runtime.py` exist, that `turn_engine.py` retains
  `validate_turn_inputs` and `run_turn`, and that `wc -l` reports every module under 800 lines.
  If the sibling splits have not landed, do them here to **exactly** those module boundaries and
  say so in the commit body.
- `web/backend/app/services/turn_engine.py` — where a later phase of this plan needs a helper that
  now lives in `beat_runner.py` (`_relationship_note` in Phase 10, `_apply_stat_change` in Phase
  11), re-export it from `turn_engine` rather than editing tests that import the old private name;
  note the re-exported names in the `turn_engine` docstring.
- No new tests. The existing suites — `utils/tests/backend/api/test_play_turn*.py` (13 files), `utils/tests/backend/services/test_emission*.py`, `test_degenerate_beat.py`, `test_one_beat_one_passage.py`, `test_register_threading.py`, `test_never_names_the_player.py`, `test_scratchpad_never_renders.py` — are the proof.
- `docs/structure.md` and `docs/component-map.md` (backend services table) — confirm the modules and their owners are listed.

**Rationale** — Four later phases of this plan edit `run_turn`, so the file must be under the ceiling and stable before they run. Four plans in this program independently proposed a split with four different module names; converging on the one owner is what stops the second and third from producing an unmergeable rename of the same functions. A verify-and-re-export phase is a zero-behaviour-change commit and the existing 1 110-case suite is a complete regression net.

*Action: Run the validation for this phase — `uv run pytest` in full (nothing here may change an assertion), and confirm `wc -l web/backend/app/services/*.py` shows every file under 800. Once green, commit locally: `[Depth for Players] (2/12) Complete: Confirmed the agreed turn-engine module layout and re-exported the helpers this plan's later phases need.` Do not push or open a PR.*

---

### Phase 3 — A per-turn override envelope on the turn request (backend)

**Locations**

- `web/backend/app/schemas/play.py` — new `TurnOverrides(CamelModel)` with every field optional and `None`-defaulted, bounded exactly as `ScenarioUpdate` bounds its counterpart: `max_turns: int | None = Field(default=None, ge=1, le=10)`, `suggestions_count: int | None = Field(default=None, ge=0, le=4)`, `beat_length: BeatLength | None = None`. (`planner`, `register` and `ties` are added by Phases 6, 7 and 10 — the envelope is introduced once and extended in place.) Add `overrides: TurnOverrides | None = None` to `TurnRequest`, with a docstring stating the contract: an override applies to **this turn only**, is never written to the `Scenario` row, and is out of scope for the intent/direction/planner agents in the same way `taggedDocIds` is — it changes how the turn is *run*, never what the turn is *about*.
- New `web/backend/app/services/turn_settings.py` — a frozen `TurnSettings` dataclass (`max_turns`, `suggestions_count`, `beat_length`, and the fields later phases add) and `resolve(scenario, overrides) -> TurnSettings`, which takes each value from the override when present and from the `Scenario` row otherwise, re-clamping defensively (the same reasoning as `assembler`'s `context_beats` clamp: the schema guards the boundary, the resolver guards a hand-edited row). Small, pure, trivially testable, and it keeps `run_turn` from growing a resolution branch per control.
- `web/backend/app/services/turn_engine.py` — `run_turn` calls `turn_settings.resolve(scenario, req.overrides)` once, immediately after `session` is resolved, and reads `settings.max_turns` at the `max_turns = max(1, scenario.max_turns)` site (~line 611) and `settings.suggestions_count` at the follow-up-suggestions site (~line 1105).
- `web/backend/app/services/assembler.py` — `assemble_context` gains a keyword-only `beat_length_override: BeatLength | None = None`, applied where `beat_length` is currently normalised from `scenario.beat_length`. This is the correct entry point because `ctx.beat_length` is read by both `character_turn_agent` (the prompt directive and the prose allowance) and `beat_runner._runaway_chars`; overriding it after assembly would leave one of the two reading the scenario value.
- `web/backend/app/services/events_store.py` — `record_user_turn` gains an optional `overrides: dict | None` and writes it into the `user_turn` row's `data` as `data["overrides"]` when non-empty. Additive JSON key, no schema change. This is what makes a turn's settings auditable in the Inspector and the export.
- `web/backend/app/services/session_export.py` — render the overrides line for a turn that carried any.
- `web/backend/app/services/turn_engine.py` — the existing `turn` trace step's `data` gains `overrides` (the resolved non-null override map) so the Inspector can say what the turn actually ran with.
- `web/frontend/lib/events.ts` — the hand-maintained mirror: add `TurnOverridesBody` and `overrides?: TurnOverridesBody | null` to `TurnRequestBody`, with the same doc comment. **This file must change in this phase**; `web/shared/contracts/` stays empty.
- `docs/api-contract.md` §*Turn Stream* — document `overrides`: the fields, the bounds, that it is per-turn and never persisted to the scenario, that it is persisted on the `user_turn` row for audit, and that it is withheld from the intent/direction/planner agents.
- `docs/data-flow.md` §*Write + Streaming Path* — add the resolve step between "resolve session" and "assemble context".
- Tests: `utils/tests/backend/services/test_turn_settings.py` (override wins; absent override falls back to the scenario; out-of-range values from a hand-edited row are clamped; an empty envelope is identical to none), `utils/tests/backend/api/test_play_turn_overrides.py` (a turn sent with `overrides.maxTurns` stops at the override's cap and the `Scenario` row is **unchanged** afterwards; `overrides.beatLength` reaches `ctx.beat_length`; `overrides.suggestionsCount = 0` suppresses the `branch_choices` event; the `user_turn` row carries `data.overrides`), and an addition to `utils/tests/backend/services/test_assembler.py` for `beat_length_override`.

**Rationale** — This is the structural half of gap G4 and the foundation for Phases 4, 6, 7 and 10, each of which adds one field to an envelope that already exists rather than inventing its own path. Landing it with no UI keeps the phase provable by API tests alone, and the app is fully working at the end of it: a client that sends no `overrides` behaves exactly as today.

*Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services utils/tests/backend/api/test_play_turn_overrides.py`, then the full `uv run pytest`; plus `npm run typecheck` in `web/frontend` for the mirror. Once green, commit locally: `[Depth for Players] (3/12) Complete: Added the per-turn override envelope, the TurnSettings resolver, and the turn-request mirror.` Do not push or open a PR.*

---

### Phase 4 — Pins: per-turn versus permanent, visibly (frontend)

**Locations**

- `web/frontend/features/story-player/useScenePlay.ts` — new state `turnOverrides: TurnOverridesBody` and `pinned: Record<SceneControlKey, boolean>` (default all `true`). Each existing setter (`setMaxTurns`, `setSuggestionsCount`, `setBeatLength`) branches: **pinned** → today's optimistic state write plus `updateScenario(...)`, and clear any override for that key; **unpinned** → write `turnOverrides[key]` and do **not** call `updateScenario`. A new `setPinned(key, boolean)` flips a control's scope and, when re-pinning a control that has an unpinned value, discards the override rather than promoting it (promoting would make a pin click a silent permanent write, which is precisely the surprise this phase removes). `submit()` sends `overrides` when the map is non-empty; its existing `.finally()` clears `turnOverrides` — the spring-back. The hook returns `turnOverrides`, `pinned`, `setPinned`, and an `effective` view (override ?? scenario value) that the menu renders.
- `web/frontend/components/feature/SceneConfigMenu.tsx` — each control row gains a pin toggle: a 24×24 `IconButton`-sized button with `aria-pressed`, an accessible name of the form `"Max turns — pinned to this scene"` / `"Max turns — this turn only"`, and a visible state difference that is **not** colour alone (a filled versus outlined pin glyph plus a text suffix on the row label). An unpinned row shows its value with a "this turn" tag. The panel gains a footer line, rendered only when at least one control is unpinned: *"2 settings apply to your next message only, then spring back."* Each control keeps one line of consequence copy under it. **`docs/plans/making-it-legible.md` Phase 5 lands before this plan and owns that copy** (Max turns → *"How many beats one message produces"*, Suggestions → *"Follow-up ideas offered after each turn"*, Beat length → *"How much a character says at once"*, each with its own help line and cost readout, wired through `SceneControlSelect`'s `help` prop and `aria-describedby`). **Keep it; do not author a second set.** This phase adds only the pin affordance and the unpinned-scope suffix on top. If that plan has not landed, write one line per control here and expect it to be replaced.
- `web/frontend/components/feature/Composer.tsx` — pass the pin props through; when any control is unpinned, the Config button gets a small dot indicator with an `sr-only` "settings apply to this turn only" so the state is visible without opening the popover.
- `web/frontend/lib/api.ts` — no change (`postTurn` already takes a `TurnRequestBody`).
- `docs/design-system.md` §*Story-Player Layout* — document the pin idiom (what pinned/unpinned mean, and that scope is shown as text, never colour alone).
- `docs/routes.md` / `docs/component-map.md` — note the SceneConfigMenu's new responsibility.
- Tests, co-located: `web/frontend/components/feature/SceneConfigMenu.test.tsx` — a pin toggle exists per control, its accessible name states the scope, unpinning does not call the scenario setter, the footer appears only when something is unpinned, everything is reachable by keyboard. `web/frontend/features/story-player/useScenePlay.test.ts` — a pinned change calls `updateScenario` and no override is sent; an unpinned change sends `overrides` on the next turn and does **not** call `updateScenario`; the override is cleared after the turn settles (including on the error path, since the clear lives in `.finally`); re-pinning discards the pending override.

**Rationale** — This closes gap G4 from the player's side. It is deliberately a separate commit from Phase 3 so that the wire contract and the interaction model can each fail independently, and so the backend is provably correct before any UI depends on it. The default (pinned) means a player who ignores the feature sees no change whatsoever.

*Action: Run the validation for this phase — `npm test` in `web/frontend` for `SceneConfigMenu`, `Composer` and `useScenePlay`, plus `npm run typecheck && npm run lint`; and an accessibility + responsive pass (keyboard reach and visible focus on every pin, AA contrast on the pinned/unpinned treatments, non-colour-only state, popover layout at 320/375/768/1024 — the popover is 264 px wide inside a composer that must not overflow at 320). Once green, commit locally: `[Depth for Players] (4/12) Complete: Scene-config controls can now apply to one turn and spring back, with the scope shown on each row.` Do not push or open a PR.*

---

### Phase 5 — Scene presets instead of more sliders

**Locations**

- New `web/backend/app/content/scene_presets.py` — `BUILTIN_SCENE_PRESETS: list[dict]`, four entries, each `{id, label, blurb, values}`. `blurb` is the sentence rendered at the point of use and it names the trade, not the numbers. Proposed table (values chosen to be recognisably different from each other and from the defaults, all inside the existing schema bounds):
  - `fast_banter` — max turns 3, beat length `short`, suggestions 4. *"Short beats, quick exchanges, plenty of follow-ups. Scenes move; nobody monologues."*
  - `slow_burn` — max turns 6, beat length `long`, suggestions 2. *"Long beats, fewer of them. Each message takes noticeably longer to play out."*
  - `cinematic` — max turns 8, beat length `medium`, suggestions 0. *"The most beats per message and no follow-ups — the scene carries itself. The longest turns in the app."*
  - `interrogation` — max turns 2, beat length `medium`, suggestions 3. *"Two beats a message: you ask, someone answers. Nothing runs away from you."*
  Deliberately **not** in the bundle: `contextBeats` (see the cross-plan note below) and `plannerMode` (see the decided gap in §2).
- `web/backend/app/models/scenario.py` — `scene_preset: Mapped[str | None] = mapped_column(String, nullable=True, default=None)`. **A new nullable column needs no Alembic migration** — the additive reconciler self-heals it; follow the `beat_length` comment's warning about `server_default` only if a non-null default is ever wanted (it is not).
- `web/backend/app/schemas/scenario.py` — `scene_preset: str | None` on `ScenarioBase`, `ScenarioUpdate` and `ScenarioRead`; validated against the known preset ids (unknown → 422, matching how `beat_length` is a `Literal` rather than a free string).
- `web/backend/app/schemas/settings.py` — `ScenePresetRead(CamelModel)` (`id`, `label`, `blurb`, `values: ScenePresetValues`).
- `web/backend/app/routes/options.py` — `GET /options/scene-presets -> list[ScenePresetRead]`, read-only, no DB access.
- `web/frontend/lib/types.ts` — `Scenario.scenePreset?: string | null`. `web/frontend/lib/api.ts` — `ScenePreset` interface and `getScenePresets()`.
- `web/frontend/features/story-player/useScenePlay.ts` — fetch the presets once on mount, best-effort (a failure leaves the list empty and the picker simply does not render — the same degradation shape as `getLlmContextWindow`). `applyPreset(id)` writes all bundled values through the **pinned** path (a preset is a statement about the scene, not about one turn) in a single `updateScenario` call together with `scenePreset: id`. A derived `presetState` is `"none" | "clean" | "modified"`, computed by comparing the live values against the named preset's.
- `web/frontend/components/feature/SceneConfigMenu.tsx` — a preset row at the **top** of the popover: a `SceneControlSelect` of `Custom` + the four presets, the selected preset's `blurb` underneath, a `· modified` suffix when the values have drifted, and a `Reset to preset` button (reversibility) shown only in the `modified` state. Choosing `Custom` clears `scenePreset` without touching any value.
- `docs/api-contract.md` — the new endpoint and the `scenePreset` field on the scenario shape. `docs/data-flow.md` §*Settings Flow*. `docs/design-system.md` — the preset-then-controls ordering in the popover.
- Tests: `utils/tests/backend/api/test_options.py` (the endpoint returns four presets; every preset's values validate against `ScenarioUpdate`, which is the test that stops the table drifting out of bounds), `utils/tests/backend/api/test_scenarios.py` (`scenePreset` round-trips; an unknown id is 422). Co-located `web/frontend/components/feature/SceneConfigMenu.test.tsx` (picking a preset applies every bundled value in one call and records the id; the blurb renders; `modified` appears after a manual change and `Reset to preset` restores) and `useScenePlay.test.ts` (a failed preset fetch leaves the scene fully usable).

**Rationale** — This is the item the guardrail is aimed at: it replaces "learn what three numbers do" with "pick the kind of scene you want", while leaving every underlying control exactly where it was for a player who wants it. It lands after Phase 4 because a preset writes through the pinned path and the "modified" state is only meaningful once pinned-versus-per-turn exists. **Cross-plan note:** `contextBeats` ("Number of beats") is deliberately absent from every preset. If the *Making It Legible* plan has already removed that control, nothing here changes; if it has not, leave the slider standing, un-presetted and un-pinned, and let that plan remove it.

*Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api/test_options.py utils/tests/backend/api/test_scenarios.py` then the full `uv run pytest`; `npm test` in `web/frontend` for `SceneConfigMenu` and `useScenePlay`, plus `npm run typecheck && npm run lint`; and an accessibility + responsive pass (the preset select and its blurb inside the 264 px popover at 320/375/768/1024, keyboard reach, visible focus, AA contrast on the `modified` tag). Once green, commit locally: `[Depth for Players] (5/12) Complete: Named scene presets over the existing controls, with a modified state and a reset.` Do not push or open a PR.*

---

### Phase 6 — Turn planning can be switched off

**Locations**

- `web/backend/app/agents/planner_agent.py` — rename `_fallback_beat` to a public `scripted_beat` (keep a module-private alias if any test imports the old name, and update `plan_beats`'s four internal call sites). Rewrite its docstring: it is no longer only the offline fallback, it is the **deliberate planner-off order**, and it is the one beat decision in the app that costs nothing.
- New `web/backend/app/services/beat_order.py` — `next_beat(ctx, intent, acted, *, scene_opening, locked_id, direction, beats_left) -> BeatDecision`. It delegates to `planner_agent.scripted_beat` first (which already honours an outstanding direction, walks the whole cast on a group-scoped intent, answers an addressed character, gives one responder on a freeform mid-scene line, and narrator-opens a cold scene). When that returns `end` *and* a present, non-POV character has not taken a beat this turn *and* `beats_left > 0`, it instead returns `speak` for the next such character in cast order — the round-robin that keeps a planner-off scene from collapsing to one line per message. `register` and `stakes` are always `None`/`""` on this path; that is the honest consequence, not an omission.
- `web/backend/app/schemas/play.py` — `PlannerMode = Literal["planner", "off"]`; `planner: PlannerMode | None` on `TurnOverrides`.
- `web/backend/app/models/scenario.py` — `planner_mode: Mapped[str | None]`, nullable, default `None` (= `"planner"`). Additive; no migration.
- `web/backend/app/schemas/scenario.py` — `planner_mode: PlannerMode | None` on base/update/read.
- `web/backend/app/services/turn_settings.py` — `planner` on `TurnSettings`, resolved override → scenario → `"planner"`.
- `web/backend/app/services/turn_engine.py` — inside the beat loop, the block that currently calls `planner_agent.plan_beats` branches on `settings.planner`. With planning off it calls `beat_order.next_beat` and skips the `planned` queue and the lookahead entirely; the `planning` trace step's title and detail change to *"Planning off — the cast answers in order"* with `data={"planner": "off"}`. Everything downstream is untouched: the exchange guard, the forced direction schedule (`direction_agent.schedule`), `_plan_still_valid`, the POV backstop, the silent-turn backstop, the runaway backstop and the hard `max_turns` cap all still apply, because they are the engine's rules and not the planner's.
- `web/frontend/lib/events.ts` — `planner?: "planner" | "off" | null` on `TurnOverridesBody`. `web/frontend/lib/types.ts` — `Scenario.plannerMode`.
- `web/frontend/features/story-player/useScenePlay.ts` — `plannerMode` + `setPlannerMode`, pinnable like the rest.
- `web/frontend/components/feature/SceneConfigMenu.tsx` — a **Turn planning** control with two options and consequence copy that states the loss, not just the gain: *"On — a director reads each moment, decides who speaks, sets the scene between beats, and pitches how tense the beat is. Off — the cast answers in order. Much faster (planning is over half of a turn), but nothing judges the moment: no scene-setting narration between beats, no read of how tense things are, and a character the story has written out stays in the rotation until you remove them from the cast rail."*
- `web/frontend/components/feature/TurnStatusStrip.tsx` — render the planning-off `planning` step's copy rather than "Deciding who speaks next", so a fast turn does not look like a broken one.
- `docs/api-contract.md` §*Turn Stream* and `docs/architecture.md` — the planner is now optional; name the deterministic replacement and its consequences. `docs/documentation.md` — the agent list gains the note that `planner_agent` can be bypassed. `docs/checklist.md` — add the deferral that the latency and quality difference between the two modes is **unmeasured**, and that the experiment is an interleaved A/B in one session (per the checklist's own rule that day-apart comparisons on this endpoint are worthless).
- Tests: `utils/tests/backend/services/test_beat_order.py` (round-robin walks the present cast then ends; the POV character is never selected; an outstanding direction still outranks the rotation; a departed character is skipped; no LLM call is made — assert with an unconfigured endpoint), `utils/tests/backend/api/test_play_turn_planner_off.py` (a turn with `overrides.planner = "off"` produces beats, emits the planning-off trace step, respects `maxTurns`, and never calls the planner — monkeypatch `planner_agent.plan_beats` to raise), and an addition to `utils/tests/backend/agents/test_planner_agent.py` for the rename. Co-located `SceneConfigMenu.test.tsx` (the control renders both options and the consequence copy) and `TurnStatusStrip.test.tsx`.

**Rationale** — This is the owner's explicit request, and the honest version of it: the replacement is code that already exists and is already exercised on every unconfigured-LLM path, so switching the planner off is not a new code path so much as a deliberately-chosen old one. It lands after Phase 3 (the envelope) and after Phase 1 (which ruled out reviving `who_is_up`). It is the single largest latency lever available to a player — roughly 56 % of turn time — and the control has to say what it costs, because it costs something real.

*Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services/test_beat_order.py utils/tests/backend/api/test_play_turn_planner_off.py utils/tests/backend/agents` then the full `uv run pytest`; `npm test` in `web/frontend` for `SceneConfigMenu` and `TurnStatusStrip`, plus `npm run typecheck && npm run lint`; and an accessibility + responsive pass on the new control and its copy at 320/375/768/1024. Once green, commit locally: `[Depth for Players] (6/12) Complete: The planner can be switched off, replaced by the model-free scripted beat order, with its consequences stated at the control.` Do not push or open a PR.*

---

### Phase 7 — A player-pinned register

**Locations**

- `web/backend/app/schemas/play.py` — `Register = Literal["light", "neutral", "tense", "grave"]`; `register: Register | None` on `TurnOverrides`. Per-turn **only** — no `Scenario` column, because "how this moment is pitched" is a property of a moment. The scene-config row therefore renders without a pin and says so.
- `web/backend/app/services/turn_settings.py` — `register: str | None` on `TurnSettings`, plus `pitch(settings, decision) -> tuple[str | None, str]` returning `(register, source)` where `source` is `"player"` when the player pinned one and `"planner"` otherwise. One helper, so the precedence lives in one place.
- `web/backend/app/services/turn_engine.py` — apply `pitch()` at **every** path that produces a character beat, not only the planner's: the planner `speak` branch, the forced-direction `_beat_or_skip` call, the forced-exchange responder, the silent-turn backstop, and the puppet loop's `_generate_speaker` call (which passes no register today — a pinned register is exactly the case where it should). The `speaker` trace step's `data` gains `registerSource`.
- **Nothing in `character_turn_agent` changes.** The pinned register flows through the existing `register=` parameter into `_voice_params` → `_REGISTER_SAMPLER` (selecting an existing row, changing no number), `assembler.select_voice_samples` (choosing the tagged samples) and `_REGISTER_DIRECTIVES` (the recency-tail directive). This is the whole point: the machinery is built, it just had no player-facing input. In particular **no frequency/presence penalty is reintroduced** — the `_REGISTER_SAMPLER` table is not edited by this phase.
- `web/frontend/lib/events.ts` — `register` on `TurnOverridesBody`.
- `web/frontend/features/story-player/useScenePlay.ts` — `register` + `setRegister`; unlike the other controls it always writes to `turnOverrides` and always springs back.
- `web/frontend/components/feature/SceneConfigMenu.tsx` — a **Register** control: `Auto (the scene decides)` · `Light` · `Neutral` · `Tense` · `Grave`, with copy: *"Pins how this moment is pitched for your next message only. It picks which of a character's voice samples they draw on and how far their word choice can wander — it does not decide who speaks."* The row carries a permanent "this turn" tag instead of a pin.
- `web/frontend/components/feature/TurnInspectorPanel.tsx` — render `registerSource` on the speaker step ("pitched by you" / "pitched by the scene"), so the Inspector answers the question the control invites.
- `docs/api-contract.md` §*Turn Stream* — the field, its per-turn-only scope, and the three consumers it drives. `docs/data-flow.md` §*Write + Streaming Path* — the register's provenance now has two sources.
- `docs/checklist.md` — extend the existing *"Nothing measures whether the register works"* bullet: a player-pinned register makes a manner-adaptation eval cheaper to run (the register becomes an independent variable the harness can set directly instead of coaxing out of the planner), and note that nothing in this phase constitutes evidence that the pin improves output.
- Tests: `utils/tests/backend/services/test_turn_settings.py` (pitch precedence: player over planner, planner when unpinned, `None` when neither), `utils/tests/backend/services/test_register_threading.py` (extend: a pinned register reaches the character call from the puppet path and from the silent-turn backstop, both of which carry none today), `utils/tests/backend/api/test_play_turn_overrides.py` (a pinned register appears on the `speaker` trace step with `registerSource: "player"`). Co-located `SceneConfigMenu.test.tsx` and `TurnInspectorPanel.test.tsx`.

**Rationale** — The register is the app's most-developed and least-visible piece of expressive machinery: it already reaches three separate consumers and the player has never been able to touch it. Pinning it is a one-field change on a contract that Phase 3 already built, and it pairs directly with Phase 6 — with the planner off, the pin becomes the *only* source of a register, which is a real reason to want it.

*Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services/test_turn_settings.py utils/tests/backend/services/test_register_threading.py utils/tests/backend/api/test_play_turn_overrides.py` then the full `uv run pytest`; `npm test` in `web/frontend` for `SceneConfigMenu` and `TurnInspectorPanel`, plus `npm run typecheck && npm run lint`; and an accessibility + responsive pass on the new row at 320/375/768/1024. Once green, commit locally: `[Depth for Players] (7/12) Complete: The player can pin a beat's register for one turn; it reaches the sampler, the voice samples and the prompt tail.` Do not push or open a PR.*

---

### Phase 8 — A per-character voice-looseness bias

**Locations**

- `web/backend/app/models/character.py` — `looseness: Mapped[int | None] = mapped_column(nullable=True, default=None)`, documented as a **bias on top of the beat's register**, in `[-2, +2]`, `None` meaning neutral. Additive nullable; no migration.
- `web/backend/app/schemas/character.py` — `looseness: int | None = Field(default=None, ge=-2, le=2)` on the base/update/read models.
- `web/backend/app/services/assembler.py` — `CastMember.looseness: int | None`, populated in `_build_cast` from `char.looseness`.
- `web/backend/app/agents/character_turn_agent.py` — `_voice_params` gains `looseness: int | None = None` and a module-level `_LOOSENESS_STEP = 0.03` with `_LOOSENESS_BOUNDS = (0.70, 0.98)`. The register's `top_p` is nudged by `looseness * _LOOSENESS_STEP` and clamped. `frequency_penalty` and `presence_penalty` are **not** touched and stay `0.0`; write that constraint into the comment beside the constant, with the reason (EXP-2026-08-007: the penalties fall on the tokens prose is made of, and the arms did not overlap). The three call sites that build params (`generate_line_with_usage` and the two streaming variants) pass `speaker.looseness`.
- `web/frontend/lib/types.ts` — `Character.looseness?: number | null`.
- `web/frontend/components/feature/VoiceSamplesEditor.tsx` — a 5-stop `input[type="range"]` above the sample rows, `min=-2 max=2 step=1`, with an associated `<label>` and a text readout (`Controlled · Measured · Natural · Expressive · Loose`) plus one line of consequence: *"How far this character's word choice may wander. The moment's register still leads; this only leans against it."* The readout is text, not colour, and the control is a native range so keyboard operation is free.
- `web/frontend/components/feature/CharacterModal.tsx` — pass the value/handler through the existing Voice & tone section (`lib.setDraft("looseness", n)`); the file is 540 lines and this is a handful, well inside the ceiling.
- `web/frontend/components/feature/CharacterDossier.tsx` — render the value **read-only** at play time, next to the character's speech style, so a player can see why someone sounds the way they do without leaving the scene. Editing from the dossier is a recorded deferral.
- `docs/api-contract.md` §*Character shape* and `docs/design-system.md` — the field and the control.
- `docs/checklist.md` — two new bullets: (i) the `±0.03`-per-step size is **chosen, not measured**; the experiment that would settle it is a blinded matched-scene comparison at `-2 / 0 / +2` on the deployed model, interleaved in one session; (ii) restate the standing constraint that the dial must never be extended to the penalty columns without first running the **drift eval** the checklist already names (repetition of a character's own phrasings across a long session, or blinded speaker attribution, run with the penalties off and on) — EXP-2026-08-007 measured sentence structure, not drift, and it ran on one model only.
- Tests: `utils/tests/backend/agents/test_character_turn_agent.py` (a looseness of `+2` raises `top_p` by exactly `0.06` over the register's row and `-2` lowers it; the result is clamped into `[0.70, 0.98]`; `None` is byte-identical to today; **the penalties stay `0.0` at every combination** — that assertion is the guard against a future edit quietly reintroducing them), `utils/tests/backend/api/test_characters.py` (the field round-trips; out-of-range is 422). Co-located `VoiceSamplesEditor.test.tsx` (labelled, keyboard-operable, readout matches the value) and `CharacterDossier.test.tsx`.

**Rationale** — The second half of item 5, and the one place in the app where a player's taste about a *character* (rather than a scene) can be recorded. It reuses the sampler seam the register already established, moves the one axis the existing measurement supports, and is explicitly walled off from the axis it does not.

*Action: Run the validation for this phase — `uv run pytest utils/tests/backend/agents/test_character_turn_agent.py utils/tests/backend/api/test_characters.py` then the full `uv run pytest`; `npm test` in `web/frontend` for `VoiceSamplesEditor`, `CharacterModal` and `CharacterDossier`, plus `npm run typecheck && npm run lint`; and an accessibility + responsive pass (the range control's label, readout and 44 px touch target at 320/375/768/1024). Once green, commit locally: `[Depth for Players] (8/12) Complete: Per-character looseness biases the register's top_p only, with the penalty columns explicitly held at zero.` Do not push or open a PR.*

---

### Phase 9 — "How this world writes": the prompt overrides as a play-time tool

**Locations**

- New `web/frontend/lib/promptLayers.ts` — a pure `resolveLayers(catalog, layers) -> Record<string, "default" | "global" | "storyline" | "scenario">`, mirroring the backend precedence in `prompt_registry.resolve_prompts` (last non-blank wins). Co-located `promptLayers.test.ts` including the blank-means-inherit case, which is the rule most likely to be got wrong.
- `web/frontend/components/feature/PromptOverridesEditor.tsx` — an optional `sources?: Record<string, PromptLayer>` prop; when present, each prompt renders a small text badge naming where its live value comes from (`Default` · `Everywhere` · `This world` · `This scene`). Existing callers pass nothing and are unchanged.
- `web/frontend/components/feature/PromptOverridesModal.tsx` — accept an optional `storylineOverrides` so it can pass all three layers to `resolveLayers` (it already fetches the global layer). Player-facing `heading`/`subtitle` come from the caller.
- New `web/frontend/components/feature/SceneMenu.tsx` — one popover in the scene header replacing three inline controls. Items: **Writing…** (opens the prompt modal), **Turn Inspector** (a toggle, `aria-pressed`), **Export as JSON**, **Export as Markdown**. Native button list, Esc/outside-click close, focus moved into the panel on open — the same idiom `SceneConfigMenu` already uses.
  > **Shared with `docs/plans/reach.md` Phase 4, which lands after this plan and *extends* this
  > same file rather than creating a second one.** Build it now to the interface Reach needs, so
  > that phase is an extension and not a rewrite: an **ordered `items` array** of
  > `{ key, label, hint?, icon?, onSelect, disabled?, pressed?, render? }` plus an
  > `extraSlot?: React.ReactNode` at the foot, where `render` lets a non-button control (Reach
  > puts `ThemeSwitcher` here) sit as a labelled row. Reach adds the `useMediaQuery` narrow/wide
  > split, the drill-down-in-place rule for panel-owning items, and the remaining header controls.
- `web/frontend/components/layout/SceneHeader.tsx` — replace the inline `ExportMenu` and the Inspector button with `SceneMenu`. This collapses the control cluster and **relieves the standing 320 px defect** (the checklist's *"the scene-header Inspector icon clips ~7 px and the button is genuinely unreachable"*), which the checklist itself says needs exactly this: collapsing controls below `sm`, a design decision rather than a layout tweak. Take the whole width, not just below `sm`, so there is one behaviour to test.
  > **Do not close the checklist bullet here.** By this phase the header also carries Control Over
  > the Record's `PlaythroughTray` and Making It Legible's four-state model-health indicator, and
  > `docs/plans/reach.md` Phase 4 owns the **durable** fix — an item model that still works after
  > the *next* control is added. Measure at 320 px, record the measurement, and **narrow** the
  > bullet to name what is still at risk; Reach Phase 4 removes it.
- Delete `web/frontend/components/feature/ExportMenu.tsx` and `ExportMenu.test.tsx` (its `ExportFormat` type moves to `SceneMenu.tsx`); it has no other consumer. Update the imports in `StoryPlayerView.tsx`.
- `web/frontend/features/story-player/StoryPlayerRoute.tsx` / `useSceneData.ts` — ensure the storyline's `promptOverrides` is available to the view (it already loads the storyline for `storylineName`); pass it through `StoryPlayerView` to the modal as `baseline`/`storylineOverrides`.
- `web/frontend/features/story-player/StoryPlayerView.tsx` — hold the modal's open state; on save, `updateScenario(scenario.id, { promptOverrides })` and update local state so the next turn resolves the new text. Heading: **"How this world writes"**. Subtitle: *"These are the instructions the narrator and the cast are given. Changes here apply to this scene only — clear a field to fall back to the world's version."*
- `docs/design-system.md` §*Writing-Agent Prompt Overrides UI* — the play-time entry point and the layer badges. `docs/component-map.md` — `SceneMenu` in, `ExportMenu` out. `docs/routes.md` — the story player's header controls. `docs/checklist.md` — **narrow** (do not remove) the 320 px scene-header clipping bullet from *Known UI limitations*, recording the measurement taken here and naming `docs/plans/reach.md` Phase 4 as the owner of the durable fix and of the bullet's removal.
- Tests, co-located: `SceneMenu.test.tsx` (every item reachable by keyboard, Esc closes, the Inspector item carries `aria-pressed`, export items call back with the right format, the export items are disabled with an explanation before a session exists), `PromptOverridesEditor.test.tsx` (badges render the right layer per prompt and are absent when `sources` is omitted), `StoryPlayerView.test.tsx` (opening the modal from the header and saving calls `updateScenario` with the scenario layer), plus `components/feature/responsive-floor.test.ts` if it enumerates header controls.

**Rationale** — The prompt override system is genuinely the deepest customisation in Mytheca and it lives two navigations away from the only place where its effect is observable. Bringing it to the scene header — with each value's origin labelled, which the editor has never shown — turns three abstract layers into something a player can reason about while reading the prose they produced. Folding it into a single scene menu means the header gains capability while *losing* width, which is why this phase also closes a defect rather than deepening one.

*Action: Run the validation for this phase — `npm test` in `web/frontend` for `SceneMenu`, `PromptOverridesEditor`, `PromptOverridesModal`, `SceneHeader` and `StoryPlayerView`, plus `npm run typecheck && npm run lint`; and a full accessibility + responsive pass (keyboard-only open/traverse/close, visible focus, AA contrast on the badges, and — specifically — measure the scene header at **320** to confirm no control is clipped and `documentElement.scrollHeight === clientHeight`, plus 375/768/1024). Once green, commit locally: `[Depth for Players] (9/12) Complete: Writing prompts are reachable from the scene with per-layer attribution, via a scene menu that also fixes the 320px header clip.` Do not push or open a PR.*

---

### Phase 10 — Tie scope: the knowledge graph, under the player's control

**Locations**

- `web/backend/app/services/graph_reader.py` — one new read-only parameterized template, `_REL_OFFSCENE`, matching the speaker's direct character↔character edges where the other end is **not** in the scenario's cast, `LIMIT 8`; and a `offscene_ties(character_id, scene_ids, storyline_id) -> list[dict]` orchestrator wrapping it in the exact shape `relationship_context` already uses (guard on `neo4j.is_enabled()`, `read_session()`, `except Exception → []`). Best-effort throughout: Neo4j off means every stop behaves identically to today.
- `web/backend/app/services/beat_runner.py` (Control Over the Record Phase 3's module — see Phase 2) — `_relationship_note(ctx, speaker_id, other_ids, *, scope)` gains the scope parameter with three behaviours:
  - `"addressed"` — today's behaviour: the caller's `other_ids` (just the addressee when the planner named one).
  - `"scene"` — **the default** — always every other present cast member, so a speaker carries the room's ties rather than only the addressee's. Zero new queries; it changes only which ids are passed to the existing call.
  - `"world"` — `"scene"` plus `offscene_ties`, rendered as a clearly-marked trailing clause (*"Elsewhere: you resent Corvin, who is not in this scene."*), inside the existing 8-line cap so the prompt cannot grow unboundedly.
- `web/backend/app/schemas/play.py` — `TieScope = Literal["addressed", "scene", "world"]`; `ties: TieScope | None` on `TurnOverrides`. `web/backend/app/models/scenario.py` — `tie_scope: Mapped[str | None]`, nullable, additive. `web/backend/app/schemas/scenario.py` and `web/backend/app/services/turn_settings.py` — the usual resolve chain, defaulting to `"scene"`.
- `web/backend/app/routes/play.py` — `GET /{scenario_id}/relationships` returns `{"relationships": [...], "graphAvailable": bool}` (from `graph_reader.scenario_graph(...)["available"]`). Additive field; existing clients ignore it.
- `web/backend/app/services/turn_engine.py` — thread `settings.ties` into the `_relationship_note` calls; the existing `relationship` trace step's `data` gains `scope` and the off-scene count.
- `web/frontend/lib/api.ts` / `lib/events.ts` / `lib/types.ts` — the `graphAvailable` field, the `ties` override field, `Scenario.tieScope`.
- `web/frontend/features/story-player/useScenePlay.ts` — store `graphAvailable` from the relationships fetch; `tieScope` + `setTieScope`, pinnable.
- `web/frontend/components/feature/SceneConfigMenu.tsx` — a **Ties** control, disabled with an explanatory line when `graphAvailable` is false (*"The story graph is off for this install, so nobody carries their history into a beat."* — a disabled control that says why, never a control that silently does nothing). Copy per stop: *Addressed* — "only how the speaker feels about whoever they are talking to"; *Scene* — "how the speaker feels about everyone in the room"; *World* — "…and about people elsewhere in this world. Characters may then mention someone the scene has never introduced."
- `docs/story-graph-neo4j.md` — the new template, the three stops, and the explicit statement that this is prompt-side edge expansion, **not** the RAG-side `related`-edge expansion the checklist lists as unbuilt. `docs/api-contract.md` (the `ties` field and `graphAvailable`), `docs/data-flow.md` §*Story Graph Flow*.
- `docs/checklist.md` — three edits: record the finding that **nothing writes `Secret` nodes**, so `graph_reader.secret_reachability` can never return a row on any existing world and is dead in a stronger sense than "no callers"; keep the *`TurnContext.subgraph` is fetched but unused* bullet **open** (this phase does not consume it, and pretending otherwise would be exactly the drift the docs rules forbid); and add the *World*-stop product decision as a blocking question.
- Tests: `utils/tests/backend/services/test_graph_reader.py` (`offscene_ties` returns `[]` with the graph disabled, and excludes in-scene characters when it is enabled — using the suite's existing Neo4j stubbing), `utils/tests/backend/services/test_relationship_scope.py` (each of the three scopes produces the expected id set and note shape; the 8-line cap holds at `world`), `utils/tests/backend/api/test_play_turn_overrides.py` (a turn with `overrides.ties` records the scope on the `relationship` trace step), `utils/tests/backend/api/test_play_sessions.py` (the relationships endpoint reports `graphAvailable`). Co-located `SceneConfigMenu.test.tsx` (the disabled state renders its explanation).

**Rationale** — This is the owner's "why not permit usage of the Knowledge Graph in some capacity". It is deliberately the *smallest* thing that is both real and visible: two of the three stops are pure re-parameterisation of a call the engine already makes every beat, and only the third adds a query. It is honest about what it is not — it does not give `TurnContext.subgraph` a job, it does not touch RAG retrieval, and it cannot use the secret-reachability query because the data that query reads has never existed. **Human intervention is needed** on whether the *World* stop should be offered at all (see §2, complex gap 1); ship it behind a non-default option and revisit.

*Action: Run the validation for this phase — `uv run pytest utils/tests/backend/services/test_graph_reader.py utils/tests/backend/services/test_relationship_scope.py utils/tests/backend/api` then the full `uv run pytest` (which must pass with **no** Neo4j running — the best-effort degradation is the point); `npm test` in `web/frontend` for `SceneConfigMenu` and `useScenePlay`, plus `npm run typecheck && npm run lint`; and an accessibility + responsive pass on the new control including its disabled state at 320/375/768/1024. Once green, commit locally: `[Depth for Players] (10/12) Complete: A player-controlled tie scope puts the story graph's relationship edges to work, degrading to today's behaviour when the graph is off.` Do not push or open a PR.*

---

### Phase 11 — What stats do between scenes

**Locations**

- `web/backend/app/models/stat.py` — `CharacterStat.baseline: Mapped[int | None]`, nullable, default `None`. The **authored** starting value, recoverable. Additive; no migration.
- `web/backend/app/services/stats.py` — `set_character_stats(db, character_id, values, *, authored: bool = False)`. When `authored=True` (the authoring PUT route and the creation-time starting-stats write) it sets both `value` and `baseline`. When `authored=False` (the turn engine) it records `baseline = <pre-change value>` **only if `baseline is None`**, then writes `value`. New `reset_character_stats(db, character_id) -> dict[str, int]` restoring each row's `value` from its `baseline` where one exists. This is the fix for the finding in §2: today the first accepted `state_update` destroys the authored value with nothing kept.
- `web/backend/app/routes/characters.py` — the existing stats PUT passes `authored=True`; new `POST /characters/{id}/stats/reset -> Record<str, int>`.
- `web/backend/app/services/beat_runner.py` (see Phase 2) — `_apply_stat_change` emits the `state_update` with `visibility="hidden"` when the stat's `StatDefinition.visibility` is `hidden`. `_Emitter.emit` already persists a hidden event and declines to yield it, so this needs no new machinery: the row stays in the log for the Inspector and the export, and the transcript never sees it. The `stat` **trace** step is unchanged — the Inspector is a diagnostic surface and should show everything.
- `web/frontend/features/story-player/turn-stream.ts` — `rehydrateFromHistory` skips persisted events whose `visibility === "hidden"`, so a reload agrees with the live stream (today it would replay them).
- `web/frontend/components/feature/CharacterDossier.tsx` and `DirectorRail.tsx` / `features/story-player/scene-data.ts` — filter stats whose `StatDefinition.visibility` is `hidden` out of the player-facing chips and sliders. `statDefs` is already passed into `StoryPlayerView`, so no fetch is added.
- `web/frontend/components/feature/BeginSceneModal.tsx` — a **"Start this scene fresh"** checkbox with one line of consequence: *"Stats carry over from every scene you have played. Tick this to put the cast back to the values they were written with."* When ticked, `LibraryView`'s begin handler calls the reset endpoint for each cast member before navigating. Reversible in the honest sense: it is opt-in per entry, and it restores an authored value rather than an arbitrary one.
- `web/frontend/lib/api.ts` — `resetCharacterStats(id)`.
- `web/frontend/components/feature/CharacterDossier.tsx` — one line stating the actual rule: *"Carried over from every scene in this world."* A player currently cannot find this out at all.
- `docs/documentation.md` (domain model — the Stat system's real lifecycle), `docs/data-flow.md` §*Stat Change Flow* (the baseline write and the hidden-visibility branch), `docs/api-contract.md` (the reset endpoint and the `hidden` visibility on `state_update`).
- `docs/checklist.md` — replace the *Stat lifecycle across scenarios* row in *Undesigned decisions* with the recorded finding (permanent global carry-over, decided by accident; the authored baseline **was** unrecoverable and now is not), the four options with their consequences, the recommendation (**C**), and the note that it stays blocked on sign-off because it requires session-scoped values (a new table and a change to every stat read and write). Add the hidden-stat rendering decision (option **a** implemented, **b**/**c** open).
- Tests: `utils/tests/backend/api/test_stats.py` (an authoring write sets both fields; an engine write records the baseline once and never again; reset restores; a stat that has never been touched by play resets to itself), `utils/tests/backend/services/test_validator.py` or a new `utils/tests/backend/api/test_play_turn_hidden_stat.py` (a `hidden` stat's `state_update` is persisted but **not** streamed, while its trace step is), `utils/tests/backend/data/test_models.py` (the new column). Co-located `turn-stream.test.ts` (hidden events are skipped on rehydrate), `CharacterDossier.test.tsx` and `DirectorRail.test.tsx` (hidden stats are absent), `BeginSceneModal.test.tsx` (the checkbox is labelled, keyboard-operable, and its handler fires per cast member).

**Rationale** — A player cannot reason about whether trust earned in one scene counts in the next, and the truthful answer turned out to be "yes, permanently, and there is no way back". This phase does three separable things in one commit because they are one story: it stops the authored baseline being destroyed, it gives the player one honest sentence and one reversible action, and it makes the author's `hidden` flag mean something for the first time. It deliberately does **not** commit the deeper lifecycle model — that is a product decision with a schema cost, and it is flagged rather than guessed.

*Action: Run the validation for this phase — `uv run pytest utils/tests/backend/api/test_stats.py utils/tests/backend/data/test_models.py utils/tests/backend/api/test_play_turn_hidden_stat.py` then the full `uv run pytest`; `npm test` in `web/frontend` for `turn-stream`, `CharacterDossier`, `DirectorRail` and `BeginSceneModal`, plus `npm run typecheck && npm run lint`; and an accessibility + responsive pass on the Begin-scene checkbox and the dossier line at 320/375/768/1024. Once green, commit locally: `[Depth for Players] (11/12) Complete: Stats now keep a recoverable authored baseline, hidden stats stay hidden, and the carry-over rule is stated where the player can see it.` Do not push or open a PR.*

---

### Phase 12 — Whole-plan verification, docs reconciliation, and the checklist

**Locations**

- Full gate: `uv run pytest` (1 110 cases plus everything this plan added) and `npm test` in `web/frontend`, both from clean. `npm run typecheck && npm run lint`. `uv run python utils/scripts/check_contrast.py` **if** any theme token changed (none is planned — if a phase introduced one, this is where it is proven). `node utils/scripts/check_frontend_css.mjs`.
- A single live pass over the story player at **320 / 375 / 768 / 1024**: keyboard-only traversal of the scene menu, the config popover with every new control, and the writing modal; `:focus-visible` verified structurally against the served stylesheet if the browser pane still reports `document.hasFocus() === false` (the standing environment constraint recorded in `docs/checklist.md` §*Deferred verification*); no horizontal page overflow and `documentElement.scrollHeight === clientHeight` at every width; every new interactive target at ≥44 px under `pointer: coarse`. Record anything that cannot be verified live, and why, in `docs/checklist.md` rather than claiming it.
- `docs/checklist.md` — final reconciliation. **Remove** the now-closed items: the dead-prompt-key decision (Phase 1, now recorded as decided), the 320 px scene-header clip (Phase 9). **Rewrite** the *Stat lifecycle* row (Phase 11) and the *Dead code on the turn path* bullet (Phase 1). **Keep open and say why**: `TurnContext.subgraph` unused, `presence_casting` unused, the RAG-side KG edge expansion, Text2Cypher. **Add** the deferrals this plan created: storyline-authored scene presets; editing looseness from the dossier; the unmeasured looseness step size; the unmeasured planner-off latency/quality trade; the unmeasured value of a pinned register; the *World* tie-scope product decision; the per-session stat model awaiting sign-off; and the hidden-stat rendering options b/c.
- `docs/documentation.md` §*Status* — the story player's play-time customisation surface, in one paragraph that will still be true next month.
- `docs/plans/depth-for-players.md` — no change; the plan is the record of intent, the docs are the record of behaviour.

**Rationale** — Eleven phases each ran their own targeted validation; this one proves they compose, and it is the phase where the checklist stops being a plan artefact and becomes true again. The repo's documentation rule is that docs change in the same phase as behaviour, which every phase above honours — this phase exists for the cross-cutting reconciliation no single phase owns, and for the one live accessibility pass that is only meaningful once every control is in place.

*Action: Run the validation for this phase — the full gate (`uv run pytest`, `npm test`, `npm run typecheck`, `npm run lint`, `node utils/scripts/check_frontend_css.mjs`, and `uv run python utils/scripts/check_contrast.py` if any token moved) plus the live accessibility + responsive pass at 320/375/768/1024. Once green, commit locally: `[Depth for Players] (12/12) Complete: Full gate green, docs reconciled, and the checklist reflects what is now decided, built, and still open.` Do not push or open a PR.*

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Hidden prompt specs | `PromptSpec.hidden` + `visible_specs()`; the two dead director keys leave the catalog, keep resolving | `web/backend/app/agents/prompt_registry.py`, `web/backend/app/services/settings_store.py` |
| Turn-engine layout confirmed | The split is **owned by Control Over the Record Phase 3**; this plan verifies it and re-exports the helpers its later phases need | `web/backend/app/services/turn_engine.py`, `turn_emit.py`, `beat_runner.py`, `turn_setup.py` |
| Per-turn override envelope | `TurnOverrides` on `TurnRequest`; per-turn, never written to the scenario, persisted on the `user_turn` row | `web/backend/app/schemas/play.py`, `web/backend/app/services/events_store.py` |
| Turn-settings resolver | `TurnSettings` + `resolve()` + `pitch()`; one place where override-vs-scenario precedence lives | `web/backend/app/services/turn_settings.py` |
| Contract mirror | `TurnOverridesBody` on `TurnRequestBody` (hand-maintained FE↔BE mirror) | `web/frontend/lib/events.ts` |
| Pins | Per-control scope (pinned = permanent, unpinned = next turn then spring back), stated as text | `web/frontend/components/feature/SceneConfigMenu.tsx`, `web/frontend/features/story-player/useScenePlay.ts` |
| Scene presets | Four built-in bundles + `GET /options/scene-presets` + `Scenario.scene_preset` + modified/reset state | `web/backend/app/content/scene_presets.py`, `web/backend/app/routes/options.py`, `web/backend/app/models/scenario.py`, `web/frontend/components/feature/SceneConfigMenu.tsx` |
| Planner off switch | `planner` override + `Scenario.planner_mode` + the deterministic replacement order | `web/backend/app/services/beat_order.py`, `web/backend/app/agents/planner_agent.py` (`scripted_beat`), `web/backend/app/services/turn_engine.py` |
| Pinned register | `register` override reaching the sampler row, voice-sample selection and the prompt tail, with `registerSource` on the trace | `web/backend/app/schemas/play.py`, `web/backend/app/services/turn_settings.py`, `web/backend/app/services/turn_engine.py` |
| Looseness dial | `Character.looseness` in `[-2,+2]` biasing `top_p` only; penalties held at `0.0` | `web/backend/app/models/character.py`, `web/backend/app/agents/character_turn_agent.py`, `web/frontend/components/feature/VoiceSamplesEditor.tsx` |
| Scene menu | One header popover: Writing · Inspector · Export ×2; replaces and deletes `ExportMenu`; closes the 320 px clip | `web/frontend/components/feature/SceneMenu.tsx`, `web/frontend/components/layout/SceneHeader.tsx` |
| Prompt-layer attribution | `resolveLayers` + per-prompt origin badges, reused by every override surface | `web/frontend/lib/promptLayers.ts`, `web/frontend/components/feature/PromptOverridesEditor.tsx` |
| Play-time writing modal | "How this world writes" from the scene header, saving to the scenario layer | `web/frontend/features/story-player/StoryPlayerView.tsx`, `web/frontend/components/feature/PromptOverridesModal.tsx` |
| Tie scope | Three-stop graph scope + the off-scene edge template + `graphAvailable` on the relationships endpoint | `web/backend/app/services/graph_reader.py`, `web/backend/app/services/beat_runner.py`, `web/backend/app/routes/play.py` |
| Recoverable stat baseline | `CharacterStat.baseline`, an `authored` write flag, `reset_character_stats`, `POST /characters/{id}/stats/reset` | `web/backend/app/models/stat.py`, `web/backend/app/services/stats.py`, `web/backend/app/routes/characters.py` |
| Hidden-stat rendering | `hidden`-visibility `state_update` persisted but never streamed or rehydrated; omitted from player chips | `web/backend/app/services/beat_runner.py`, `web/frontend/features/story-player/turn-stream.ts`, `web/frontend/components/feature/CharacterDossier.tsx` |
| Start-fresh control | Opt-in stat reset on entering a scene, with the carry-over rule stated | `web/frontend/components/feature/BeginSceneModal.tsx`, `web/frontend/features/library/LibraryView.tsx` |
| Backend tests — settings & envelope | Resolver precedence, clamping, and the turn honouring overrides without touching the scenario | `utils/tests/backend/services/test_turn_settings.py`, `utils/tests/backend/api/test_play_turn_overrides.py` |
| Backend tests — planner off | Round-robin order, POV exclusion, direction precedence, zero LLM calls | `utils/tests/backend/services/test_beat_order.py`, `utils/tests/backend/api/test_play_turn_planner_off.py` |
| Backend tests — register & sampler | Pitch precedence, register reaching the puppet and backstop paths, `top_p` bias arithmetic, penalties pinned at `0.0` | `utils/tests/backend/services/test_register_threading.py`, `utils/tests/backend/agents/test_character_turn_agent.py` |
| Backend tests — graph scope | `offscene_ties` degradation and exclusion; the three scopes' id sets and the 8-line cap | `utils/tests/backend/services/test_graph_reader.py`, `utils/tests/backend/services/test_relationship_scope.py` |
| Backend tests — presets, prompts, stats | Preset values validate against `ScenarioUpdate`; hidden keys omitted from the catalog; baseline/reset/hidden-stat behaviour | `utils/tests/backend/api/test_options.py`, `utils/tests/backend/agents/test_prompt_registry.py`, `utils/tests/backend/api/test_stats.py`, `utils/tests/backend/api/test_play_turn_hidden_stat.py` |
| Frontend tests (co-located) | Pins, presets, planner/register/ties controls, scene menu, layer badges, looseness, hidden stats, start-fresh | `web/frontend/components/feature/SceneConfigMenu.test.tsx`, `SceneMenu.test.tsx`, `PromptOverridesEditor.test.tsx`, `VoiceSamplesEditor.test.tsx`, `CharacterDossier.test.tsx`, `DirectorRail.test.tsx`, `BeginSceneModal.test.tsx`, `TurnStatusStrip.test.tsx`, `TurnInspectorPanel.test.tsx`, `web/frontend/features/story-player/useScenePlay.test.ts`, `turn-stream.test.ts`, `StoryPlayerView.test.tsx`, `web/frontend/lib/promptLayers.test.ts` |
| Docs updated in-phase | Contract, data flow, architecture, design system, component map, routes, story graph, checklist | `docs/api-contract.md`, `docs/data-flow.md`, `docs/architecture.md`, `docs/design-system.md`, `docs/component-map.md`, `docs/routes.md`, `docs/structure.md`, `docs/story-graph-neo4j.md`, `docs/documentation.md`, `docs/checklist.md` |
