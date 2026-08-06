# Plan — Statistics descriptions & per-band guidance in prompts

## 1. Introduction

In the new/edit-storyline authoring area, a universal stat today carries a bare
one-line `description` and a set of value **bands** that hold only a `label`
(e.g. Stamina 0–20 = "Exhausted"). Two things are missing: (1) the auto-generated
stat description is thin and generic, and (2) each band has no explanatory text,
so when the story engine hands a character their current stat at runtime the LLM
only sees `stamina=45` — it has no words for what "45" *means* for this character
right now.

This plan enriches the stat schema so a generated stat gets a fuller 1–2 sentence
description **and** every band gets its own description, both written with a
`{Character}` placeholder. At prompt-assembly time the placeholder is substituted
with the acting character's name and only the band matching the character's
current value is surfaced, so the character agent reads, e.g., *"Stamina 45/100
(Capable): Marethel still has the fight to continue forward."* Work spans the
FastAPI backend (schema, generation prompt, a new render helper, the character
turn agent) and the Next.js authoring UI (`StatsEditor`, types), plus docs.

The band JSON already lives in a `JSONColumn`, so adding a `description` key is
purely additive — **no Alembic migration** and the dev DB's additive-column
reconcile is untouched.

## 2. Gaps & Unanswered Questions

- **Placeholder token (simple gap → assume):** use the literal `{Character}`
  token exactly as the user specified. The substitution helper will replace
  `{Character}` (and, defensively, `{character}`) with the character's display
  name. No other tokens.
- **What to inject per turn (simple gap → assume):** inject, per stat the
  character has, one compact line = display name + `value/max` + the **current**
  band's label + that band's `{Character}`-substituted description. Also prepend
  the stat's `{Character}`-substituted general description once. Stats are few
  (~4 default) so token cost is bounded; keep it to one region in the HEAD block.
- **Band description required? (simple gap → assume):** optional. A band with an
  empty description still renders (label only), matching today's behavior — this
  keeps existing seed/hand-authored stats valid.
- **General stat `description` location (simple gap → assume):** because a
  `{Character}`-templated description is inherently per-character, it must live in
  the per-character HEAD block, **not** the shared cacheable stable prefix (which
  is reused across characters and must stay name-free).

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend schema: band descriptions

- **Locations:** `web/backend/app/schemas/stat.py` (`StatBand`),
  `web/backend/app/models/stat.py` (band-column docstring only),
  `utils/tests/backend/data/` (or existing stat schema test).
- **Changes:**
  - Add `description: str = ""` to `StatBand` (optional, no validation change;
    `label` stays required). `StatDefinitionBase.description` already exists —
    leave the field, its *content* changes via the generation prompt in Phase 3.
  - Update the `bands` column comment in `models/stat.py` to note each band dict
    may carry a `description` alongside `{min,max,label}`.
- **Rationale:** the wire/DB contract must accept a band description before any
  producer (generator, editor) writes one.
- **Tests:** a schema test that a `StatBand` round-trips with a `description`,
  and that omitting it defaults to `""`.
- **Action:** `uv run pytest utils/tests/backend/data` (+ any stat schema test).
  Commit: `[Stat Band Descriptions] (1/6) Complete: StatBand carries an optional description.`

### Phase 2 — Backend render helper: current-band + {Character} substitution

- **Locations:** new `web/backend/app/services/stat_render.py`;
  `utils/tests/backend/services/test_stat_render.py`.
- **Changes:**
  - `substitute_character(text, name)` → replace `{Character}`/`{character}`.
  - `current_band(stat_def, value)` → the band dict whose `[min,max]` contains
    `value` (first match; `None` if none — mirrors FE `bandLabelFor`).
  - `render_character_stats(stat_defs, values, character_name)` → a compact
    multi-line block. Per stat present in `values`: the general description
    (substituted, if any) + `Display value/max (BandLabel): <band desc
    substituted>`. Skips gracefully when a stat has no bands/description.
- **Rationale:** isolate the resolution + templating logic so both the character
  turn agent (Phase 4) and tests use one implementation; keeps the agent lean.
- **Tests:** current-band boundary/no-match; substitution of both token cases and
  a name with no token (unchanged); full block for a multi-stat character
  (correct band chosen by value, name substituted, empty-desc band label-only).
- **Action:** `uv run pytest utils/tests/backend/services/test_stat_render.py`.
  Commit: `[Stat Band Descriptions] (2/6) Complete: stat_render resolves the current band and substitutes {Character}.`

### Phase 3 — Backend generation: richer descriptions + band descriptions

- **Locations:** `web/backend/app/agents/build_agent.py` (`_BLUEPRINT_SYSTEM`
  prompt text + JSON example; `_sanitize_bands` to carry `description`);
  `web/backend/app/agents/character_agent.py` (`_bands_text` include band
  descriptions in the stat-proposal context — minor);
  `utils/tests/backend/agents/`.
- **Changes:**
  - Rewrite the `_BLUEPRINT_SYSTEM` instruction so each stat's `description` is a
    1–2 sentence explanation using `{Character}` that says what low vs. high
    values mean; and each band gets a `description` using `{Character}`. Update
    the inline JSON example to show a `{Character}` description + band
    descriptions (mirroring the user's Stamina example).
  - `_sanitize_bands` reads and carries `row.get("description")` (stripped,
    default `""`) into the `StatBand`.
  - `_bands_text` (character_agent) appends the band description when present so
    the stat-proposal agent can cite meaning (kept short).
- **Rationale:** the generator is the primary producer the user is asking to
  improve; the sanitizer must not drop the new field.
- **Tests:** `_sanitize_bands` keeps a description and defaults it to `""`;
  a blueprint-parse test asserts a band description survives into `ProposedStat`.
- **Action:** `uv run pytest utils/tests/backend/agents`. Commit:
  `[Stat Band Descriptions] (3/6) Complete: blueprint generates {Character} stat + band descriptions; sanitizer carries them.`

### Phase 4 — Backend prompt injection: character turn agent

- **Locations:** `web/backend/app/agents/character_turn_agent.py` (`_compose`,
  the `speaker.stats` HEAD line ~L134); `utils/tests/backend/agents/`.
- **Changes:** replace the flat `state = "k=v, …"` line with a call to
  `stat_render.render_character_stats(ctx.stat_defs, speaker.stats,
  speaker.name)`; fall back to the old compact `k=v` line only if the render is
  empty (no defs). Keep it in the HEAD (identity/state) region.
- **Rationale:** this is the whole point — the character now reads, in words, what
  their current stat means, named to them, using the current band.
- **Tests:** a `_compose` test with a `ctx` carrying stat_defs + bands + a speaker
  value asserts the correct band description appears with the name substituted and
  the wrong band's text does not; a no-defs fallback test keeps the `k=v` form.
- **Action:** `uv run pytest utils/tests/backend/agents`. Commit:
  `[Stat Band Descriptions] (4/6) Complete: character turn prompt injects the current band description, named to the character.`

### Phase 5 — Frontend: types + StatsEditor band descriptions

- **Locations:** `web/frontend/lib/types.ts` (`StatBand.description?`);
  `web/frontend/features/library/editor.ts` (`blankStat`/new-band shape);
  `web/frontend/components/feature/StatsEditor.tsx`;
  `web/frontend/features/library/storylineCreator.ts` (verify pass-through);
  `web/frontend/components/feature/StatsEditor.test.tsx`.
- **Changes:**
  - `StatBand.description?: string`; new bands seed `description: ""`.
  - `StatsEditor`: add a band **description** textarea/input under each band row;
    add a hint that `{Character}` is replaced with the character's name; update the
    stat description placeholder to mention the `{Character}` placeholder and the
    1–2 sentence intent.
  - Confirm `storylineCreator.ts` maps `bands: s.bands` verbatim (description flows
    for free); adjust only if it reshapes bands.
- **Rationale:** authors must see/edit the new field and understand the
  placeholder; the create/build flow already threads bands through.
- **Tests:** editing a band description calls `onChange` with it; a new band
  includes an empty `description`.
- **Action:** `cd web/frontend && npm test -- StatsEditor` + `npm run typecheck`
  + `npm run lint`; accessibility/responsive pass on the editor (labels, focus,
  320/375/768/1024). Commit:
  `[Stat Band Descriptions] (5/6) Complete: StatsEditor edits per-band descriptions with the {Character} hint.`

### Phase 6 — Docs, full validation, merge

- **Locations:** `docs/api-contract.md` (StatBand gains `description`),
  `docs/data-flow.md` (stat render into the character prompt: current band +
  `{Character}` substitution), `docs/design-system.md` (editor band-description
  field, if design-token relevant), `docs/checklist.md` (new entry),
  `docs/structure.md` (`services/stat_render.py`).
- **Action:** full backend `uv run pytest` + frontend `npm test` +
  `typecheck`/`lint`/`next build`. Commit:
  `[Stat Band Descriptions] (6/6) Complete: docs + full-suite validation.`
  Then merge `feat/stat-band-descriptions` → `main`, resolving any drift.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Band description field | Optional `description` on `StatBand` | `web/backend/app/schemas/stat.py`, `web/frontend/lib/types.ts` |
| Render helper | Current-band resolution + `{Character}` substitution | `web/backend/app/services/stat_render.py` |
| Richer generation | Blueprint writes `{Character}` stat + band descriptions | `web/backend/app/agents/build_agent.py` |
| Prompt injection | Character turn HEAD shows current band, named | `web/backend/app/agents/character_turn_agent.py` |
| Editor UI | Per-band description inputs + placeholder hint | `web/frontend/components/feature/StatsEditor.tsx` |
| Backend tests | schema, render helper, sanitizer, compose | `utils/tests/backend/{data,services,agents}/` |
| Frontend tests | band-description editing | `web/frontend/components/feature/StatsEditor.test.tsx` |
