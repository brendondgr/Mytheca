# Narrative Style Instructions

## 1. Introduction

Mytheca's prose currently sounds the way the model was trained to sound. The world primer
tells the cast *what is true*; nothing tells them *how this story is written*. This plan adds
a **narrative style guide** to each storyline — an optional, author-owned set of writing
instructions that shapes what the prose dwells on, how people sound, how a turn is paced, the
world's recurring texture, and what must never happen. It is overridable per scenario, saved
and reusable across worlds, editable and clearable at every level, and drafted by an agent
when the author wants that.

The architecture is deliberately unoriginal: it reuses the shape the repo already has for
per-storyline **prompt overrides** — a layered resolver (`prompt_registry.resolve_prompts`), a
frontend precedence mirror (`lib/promptLayers.ts`), and one editor component surfaced at the
world level (`LibraryView`) and the scene level (`StoryPlayerView`). What is genuinely new is
the **placement discipline**: the guide rides in the *cached system prefix*, between the
character output contract and the world primer, so it costs the model nothing per beat.
`EXP-2026-08-018` measured that the model reads it from there (`proximity_per_1k` 5.70 ± 3.81
→ 9.62 ± 3.41, higher in 5 of 6 matched pairs, arms overlapping) — so the design does not need
to spend the recency tail on it. Only one short **Signature** line does.

## 2. Decisions & Assumptions

**Decided by the owner, 2026-08-29.** These were open questions; the answers are recorded
here because two of them diverge from the pattern this feature otherwise copies.

1. **No global style layer.** Resolution is **`storyline → scenario` only**. This is a
   deliberate divergence from `prompt_overrides` (`global → storyline → scenario`): a global
   style guide would push one voice onto every world, which fights the premise that different
   worlds should feel different. The preset library below is a **library, not a layer** —
   applying a preset fills a storyline's fields; it never sits above them. Anyone implementing
   the resolver must not "fix" this into a three-layer chain.
2. **Saved presets are app-wide, in Options.** Built-ins ship in `content/`; an author's own
   saved guides go in an `app_settings` row (the same store as prompt overrides and Comfy
   config) and are surfaced in a new Options tab. Saving a storyline's guide as a named preset
   and applying it to another world is the "reusable across other stories" requirement.
3. **A new world gets a drafted guide, and the agent may pick an existing preset instead of
   writing one.** The drafting agent is handed the current preset catalog (built-ins plus the
   author's saved ones) and returns *either* a preset id it judges to fit *or* a freshly
   written guide. Either way the result lands in the editable fields, pre-filled, with
   one-click clear — the same shape the World Primer already has. Choosing a preset must
   **copy its text into the fields**, never store a reference, so every block stays editable
   afterwards.
4. **The Signature ships now, and Phase 7 separates it.** `EXP-2026-08-018`'s style arm carried
   the prefix guide *and* the tail Signature, so it cannot say which did the work. The field
   goes in; the three-arm separation runs at the end; the field comes out if it proves
   redundant.

**Simple — assumptions stated, proceeding.**

- **Block set:** six fields — `attention`, `voice`, `pacing`, `texture`, `never`, `signature`.
  Ids are a persisted contract, like `art_styles`; never rename one without migrating stored
  values.
- **Scenario override composes as an appended delta, not an in-place rewrite.** Rewriting a
  block inside the storyline guide diverges the cached prefix at that block and discards
  everything after it; appending moves the divergence to the last bytes and gives the override
  recency. The cost is that the model sees both versions, which the delta's own precedence
  line addresses. Recorded as measurable, not assumed.
- **No counts, ever.** No block may contain a paragraph, beat, sentence or word count. The
  three-tier `beatLength` control and `maxTurns` were removed for exactly this reason, and
  `EXP-2026-08-007` measured a word count moving prose the wrong way. Enforced by a test that
  scans the built-in presets.
- **Style text is literal and never interpolated.** No `{Character}`, no register, no stat
  values. One templated token makes the block volatile and destroys the cache design.
- **Style is never authored through `prompt_overrides`.** Overriding
  `CHARACTER_OUTPUT_CONTRACT` changes the first bytes of the system message and kills the
  prefix for every call.
- **Columns are nullable with no server default**, so `core/bootstrap._reconcile_additive_columns`
  adds them with a plain `ADD COLUMN` and no Alembic migration is required. A world written
  before this feature reads as "no style", which is the correct behaviour.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — The catalog, the columns, and the one resolver

Backend only, no behaviour change: nothing reads the resolver yet. Landing it alone means the
byte-stability rules that the whole cache design rests on are tested before anything depends
on them.

- **Locations:**
  - `web/backend/app/content/style_blocks.py` (new) — the six-block catalog: id, display order,
    author-facing label and helper text, and which agent consumes it (`prose` · `planner` ·
    `both`). Modeled on `content/art_styles.py`, including its "ids are a persisted contract"
    docstring and its fall-back-rather-than-raise behaviour for unknown ids.
  - `web/backend/app/content/style_presets.py` (new) — the three built-ins (`mystery` ·
    `romance` · `action`), verbatim from the approved drafts. The `romance` preset is the exact
    text measured in `EXP-2026-08-018`; its provenance comment names that experiment.
  - `web/backend/app/models/storyline.py` · `models/scenario.py` — `style_blocks`
    (`JSONColumn`, nullable, default `None`).
  - `web/backend/app/services/style_guide.py` (new) — the single owner of resolution and
    rendering. `resolve(storyline, scenario) -> ResolvedStyle` (**two layers only** — see
    decision 1); `render_prefix()` (the four prose blocks + any scenario delta),
    `render_signature()`, `render_planner()`.
  - `web/backend/app/services/settings_store.py` — `get_style_presets` / `save_style_preset` /
    `delete_style_preset` over a new `app_settings` row, alongside the existing prompt-override
    and Comfy accessors. Built-ins are read-only and cannot be shadowed by a saved id.
- **Rationale:** one module answers "what style, composed how?", the same way
  `settings_store.resolve_art_style` is the one answer to "what look, with which LoRA?".
  Every byte-stability rule — fixed block order, whitespace normalised once, absent blocks
  emitting *nothing at all* rather than empty scaffolding — lives here and nowhere else,
  because two places deciding it is how one of them ends up wrong.
- **Tests:** `utils/tests/backend/services/test_style_guide.py` — resolution precedence;
  blank-at-a-layer means inherit, not blank; unknown block id ignored; **byte-stability** (two
  renders of the same guide are identical strings); absent blocks emit nothing; the scenario
  delta appends rather than rewrites. `utils/tests/backend/data/test_style_presets.py` — every
  built-in parses, and **no preset contains a digit-bearing length instruction**.
- **Action:** Run `uv run pytest utils/tests/backend/services utils/tests/backend/data`. Once
  green, commit: `Narrative Style (1/7) Complete: style block catalog, presets, columns and the
  resolver, with byte-stability pinned.`

### Phase 2 — Into the prompts, at the cacheable position

- **Locations:**
  - `web/backend/app/services/assembler.py` — `_build_stable_prefix` gains the resolved style
    and emits it at the **head** of the stable prefix. Because all three prose agents compose
    `system = contract + "\n\n" + ctx.stable_prefix`, that lands the guide exactly between the
    contract and `WORLD:` — widest sharing scope first. `TurnContext` gains the resolved style
    so the tail and the planner can read it without re-resolving.
  - `web/backend/app/agents/character_turn_agent.py` — `_build_user_prompt` fuses the Signature
    into the existing act-now cue (the `_REGISTER_DIRECTIVES` branch and its else-branch both).
  - `web/backend/app/agents/planner_agent.py` — `plan_beats` appends `render_planner()`
    (Pacing + Never) to its system message at the call site near line 209.
  - `narrator_agent.py` and `scene_script_agent.py` need **no change** — they already inherit
    `ctx.stable_prefix`.
- **Rationale:** this is the placement the design and `EXP-2026-08-018` exist to justify. The
  prose blocks are constant for a whole scene, so paying for them per beat in the volatile tail
  would be waste; only the one-clause Signature earns a place in recency.
- **Tests:** `utils/tests/backend/agents/test_style_in_prompts.py` (new) — the composed system
  message is **byte-identical across two beats and two speakers** of the same scene; a scenario
  delta changes only the tail of it; the Signature appears exactly once and only in the user
  message; the planner's system carries Pacing but the prose agents' does not; a storyline with
  no style produces a system message byte-identical to today's.
- **Action:** Run `uv run pytest utils/tests/backend/agents utils/tests/backend/services`. Once
  green, commit: `Narrative Style (2/7) Complete: the guide rides the cached prefix, the
  Signature the tail, Pacing the planner.`

### Phase 3 — API contract

- **Locations:** `web/backend/app/schemas/storyline.py` · `schemas/scenario.py` (`style_blocks`
  on Read/Create/Update, with the same `field_validator` shape `prompt_overrides` uses for
  null-tolerance); `routes/storylines.py` and `routes/scenarios.py` PATCH paths;
  `routes/options.py` — `GET /options/style-presets` returning the built-ins, mirroring the
  existing scene-presets endpoint. `docs/api-contract.md` and `docs/data-flow.md` updated **in
  this same phase**.
- **Rationale:** the contract has to exist before the editor can round-trip against it, and the
  docs duty is same-change by project rule.
- **Tests:** `utils/tests/backend/api/test_style_blocks_api.py` — round-trip on both entities;
  a blank block clears to inherit; an unknown block id is ignored rather than 422'd (old
  clients); the presets endpoint lists three.
- **Action:** Run `uv run pytest utils/tests/backend/api`. Once green, commit:
  `Narrative Style (3/7) Complete: style blocks on the storyline and scenario contract, plus
  the presets endpoint.`

### Phase 4 — Frontend contract and the editor

- **Locations:** `web/frontend/lib/types.ts` (the hand-mirrored `styleBlocks` field);
  `web/frontend/lib/styleBlocks.ts` (new) — the block catalog mirror plus per-block layer
  resolution, the direct sibling of `lib/promptLayers.ts` and carrying the same warning that it
  is a mirror of a backend rule; `components/feature/StyleGuideEditor.tsx` and
  `StyleGuideModal.tsx` (new) — one textarea per block, an inherited/overridden chip per block
  (reusing `Chip`/`Tag`), clear-to-inherit per block, and a preset picker that fills the fields
  rather than storing a preset id. Built directly on the `PromptOverridesEditor` /
  `PromptOverridesModal` pair.
- **Rationale:** per-block override state is the thing the UI has to make legible — "this
  scene changes Attention and inherits everything else" is the feature. Filling fields from a
  preset rather than storing a reference keeps every block editable afterwards, which is the
  stated requirement.
- **Tests (co-located):** `StyleGuideEditor.test.tsx` — renders one field per block; shows the
  right layer chip; clearing a field marks it inherited; the preset picker fills fields and
  leaves them editable. `StyleGuideModal.test.tsx` — open/close, focus trap, save payload
  omits untouched blocks.
- **Action:** Run `cd web/frontend && npm test` for the new components plus
  `npm run typecheck && npm run lint`. Once green, commit: `Narrative Style (4/7) Complete: the
  style guide editor, with per-block inheritance made visible.`

### Phase 5 — The three surfaces

- **Locations:** `features/library/LibraryView.tsx` (world level, beside the existing
  `PromptOverridesModal` entry); `features/story-player/StoryPlayerView.tsx` +
  `components/feature/SceneConfigMenu.tsx` (scene level, the override); `features/options/tabs/`
  — a new `StyleTab.tsx` for the saved-preset library (list, rename, delete, and "save this
  world's guide as a preset").
  `docs/component-map.md` and `docs/routes.md` updated in this phase.
- **Rationale:** these are the exact three places prompt overrides are already reachable from,
  so the author learns one mental model, not two. Below `lg` the modal must open as a `Drawer`
  bottom sheet mounting the same content component, per the rails pattern.
- **Tests:** co-located route/view tests asserting the entry point renders and opens; existing
  `LibraryView` / `StoryPlayerView` tests still pass.
- **Action:** Run `cd web/frontend && npm test`, `npm run typecheck && npm run lint`, plus an
  **accessibility + responsive pass** (keyboard, focus order, contrast, 320/375/768/1024) and
  `uv run python utils/scripts/check_contrast.py`. Once green, commit: `Narrative Style (5/7)
  Complete: the guide is reachable at the world, the scene, and the preset library.`

### Phase 6 — The agent that drafts it (or picks one that already fits)

- **Locations:** `web/backend/app/agents/style_agent.py` (new) — `draft_style_guide(db, premise,
  seed, docs_overview, presets)`, the direct sibling of `storyline_agent.generate_world_primer`,
  using `prompt_registry` for its system prompt so it is operator-overridable like every other
  writing agent; `routes/storylines.py` — `POST /storylines/style` alongside `/primer`;
  `features/library/useStorylineCreator.ts` + `storylineCreator.ts` to draft during world
  creation; `agents/scenario_agent.py` for an optional per-scene delta when the author allows it.
  `docs/data-flow.md` updated.
- **The two-outcome contract.** The agent receives the **current preset catalog** — built-ins
  plus the author's saved ones, each as `{id, name, one-line summary}` — and returns either
  `{"preset": "<id>"}` when one genuinely fits the world, or a freshly written six-block guide
  when none does. The route resolves a returned preset id to its text and **copies that text
  into the fields**; it never stores a preset reference, so every block stays editable
  afterwards and a later edit to the preset cannot silently rewrite a shipped world. An
  unknown or malformed preset id falls back to "write one" rather than raising.
- **Rationale:** the guide is downstream of the world the author already described, so drafting
  it from the premise is the same move `generate_world_primer` already makes — and a drafted
  guide the author edits beats an empty form they skip. Letting the agent *recognise* a fit
  rather than always inventing one is what makes the preset library compound: the author's
  saved guides get reused instead of quietly re-written slightly worse each time.
- **Validation of the agent's own output.** Whatever comes back is checked against the
  **no-counts rule** before it is stored. An agent that writes "two paragraphs" into Attention
  reintroduces exactly what `EXP-2026-08-007` measured out, and it is the one failure mode a
  writing agent will reach for unprompted.
- **Tests:** `utils/tests/backend/agents/test_style_agent.py` — mocked LLM; the preset-id branch
  resolves to that preset's text in the fields; an unknown preset id falls back to writing; a
  malformed reply falls back to no style rather than raising; a drafted block containing a
  length count is rejected. Co-located test for the create-flow wiring.
- **Action:** Run `uv run pytest utils/tests/backend/agents utils/tests/backend/api` and the
  touched frontend tests. Once green, commit: `Narrative Style (6/7) Complete: the style guide
  is drafted from the premise or matched to a saved preset, with the no-counts rule enforced.`

### Phase 7 — Docs, checklist, and the measurement that is still owed

- **Locations:** `CLAUDE.md` (a facts-block entry: what the six blocks are, where each lands,
  that the prefix placement is load-bearing, and that `EXP-2026-08-018` is why);
  `docs/documentation.md` · `docs/architecture.md` · `docs/api-contract.md` ·
  `docs/data-flow.md` · `docs/component-map.md` · `docs/checklist.md`.
  `docs/research/experiments/EXP-2026-08-019-…` — the three-arm separation (`baseline` ·
  `prefix-only` · `prefix+signature`), which `EXP-2026-08-018` records as owed, plus a
  cache-regression check reading `usage_out["reusable_prefix_chars"]` across a real turn loop
  rather than a single call.
- **Rationale:** the confound is recorded, not resolved, and shipping the Signature without
  separating it leaves a field in the contract that nothing justifies. The cache claim is
  likewise still a design argument rather than a measurement across a turn loop.
- **Action:** Run the full gate — `uv run pytest`, `cd web/frontend && npm test`,
  `npm run typecheck && npm run lint`, `node utils/scripts/check_frontend_css.mjs`,
  `make validate-research && make research-index`. Once green, commit: `Narrative Style (7/7)
  Complete: docs, checklist, and the three-arm separation of the Signature from the prefix.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Block catalog | Six blocks, ids as a persisted contract | `web/backend/app/content/style_blocks.py` |
| Built-in presets | Mystery · Romance · Action | `web/backend/app/content/style_presets.py` |
| Columns | `style_blocks` on both entities, nullable | `web/backend/app/models/{storyline,scenario}.py` |
| Resolver | Precedence, delta composition, byte-stable rendering | `web/backend/app/services/style_guide.py` |
| Prefix placement | Guide at the head of the stable prefix | `web/backend/app/services/assembler.py` |
| Signature | Fused into the act-now cue | `web/backend/app/agents/character_turn_agent.py` |
| Pacing | Appended to the planner's system message | `web/backend/app/agents/planner_agent.py` |
| Schemas + routes | Contract + `GET /options/style-presets` | `web/backend/app/schemas/`, `routes/{storylines,scenarios,options}.py` |
| Preset store | App-wide saved guides in `app_settings` | `web/backend/app/services/settings_store.py` |
| Drafting agent | Premise → a preset id, or six fresh blocks | `web/backend/app/agents/style_agent.py` |
| TS mirror | Field + per-block layer resolution | `web/frontend/lib/{types,styleBlocks}.ts` |
| Editor | Per-block editing with visible inheritance | `web/frontend/components/feature/StyleGuide{Editor,Modal}.tsx` |
| Surfaces | World · scene · preset library | `features/library/LibraryView.tsx`, `features/story-player/StoryPlayerView.tsx`, `features/options/tabs/` |
| Backend tests | Resolver, prompt placement, API, agent | `utils/tests/backend/{services,agents,api,data}/` |
| Frontend tests | Editor, modal, surfaces — co-located | beside each component |
| Experiment | Three-arm separation + turn-loop cache check | `docs/research/experiments/EXP-2026-08-019-…` |
| Docs | Same-change updates | `CLAUDE.md`, `docs/*.md` |
