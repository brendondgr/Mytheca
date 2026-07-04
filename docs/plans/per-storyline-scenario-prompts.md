# Per-Storyline / Per-Scenario Writing Prompts + Options Prompts Tab

## 1. Introduction

Velora's turn-loop "writing" agents (Character, Narrator, Director, Planner) each carry their
system prompt as a hard-coded module-level constant (`character_turn_agent._OUTPUT_CONTRACT`,
`narrator_agent._SYSTEM`/`_SYSTEM_LONG`, `director_agent._SYSTEM`/`_RERANK_SYSTEM`/`_BRANCH_SYSTEM`,
`planner_agent._SYSTEM`). There is no way for an author to influence the tone, phrasing, or
story-progression behaviour of a scene without editing Python. This plan makes those prompts
**overridable at three layers** — a global default (editable in Options), a per-storyline override,
and a per-scenario override — resolved as `default → global → storyline → scenario`.

The approach: introduce a central **prompt registry** in the backend (one source of truth for each
writable prompt's key + default text + display metadata), thread a resolved `prompts` map through the
existing `TurnContext` so every agent reads its prompt from context (falling back to its registry
default), persist global overrides in the existing namespaced `AppSetting` store, and persist
storyline/scenario overrides as a new `prompt_overrides` JSON column on each model. On the frontend,
one reusable `PromptOverridesEditor` (sub-tabbed per agent) powers three surfaces: an Options ›
**Prompts** tab (global defaults), a **gear button next to the Storyline selector** (per-storyline),
and the scenario editor (per-scenario).

## 2. Gaps & Unanswered Questions

- **Override scope (resolved with user):** storyline-level, overridable per-scenario. Chain is
  `registry default → global (Options) → storyline.prompt_overrides → scenario.prompt_overrides`,
  last non-empty wins per key.
- **Prompt coverage (resolved with user):** the four core writing agents only — Character, Narrator,
  Director, Planner. Reflection/Intent and the authoring agents are **out of scope** (the registry is
  built to be extensible, so they can be added later).
- **Assumption — empty string = "no override".** A blank textarea for a prompt means "fall through to
  the layer below," so clearing a field is how you reset to the inherited/default value. Each editor
  row also shows the effective default as placeholder + a "Reset" affordance.
- **Assumption — no per-user scoping.** Global overrides are app-wide, matching the existing
  `AppSetting` store (no user column today).
- **Assumption — migration is additive + reconciler-safe.** `prompt_overrides` is a **nullable** JSON
  column (code treats `NULL` as `{}`), so it self-heals through `bootstrap._reconcile_additive_columns`
  on an already-migrated DB (see checklist "DB drift" note) and needs no server-default backfill.
- **Assumption — the character `_OUTPUT_CONTRACT` is editable but flagged.** It contains the strict
  `<speaker:>`/`<type:>`/`<thinking>` parsing contract; the UI will warn that editing it can break
  emission parsing. We do **not** attempt to validate custom contract text.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Prompt registry + layered resolution (backend, no behaviour change)

- **Locations:** new `web/backend/app/agents/prompt_registry.py`; edits to
  `character_turn_agent.py`, `narrator_agent.py`, `director_agent.py`, `planner_agent.py` to import
  their default text from the registry (single source of truth); new
  `utils/tests/backend/agents/test_prompt_registry.py`.
- **Details:** define a `PromptSpec` (fields: `key`, `agent`/group, `label`, `description`, `default`)
  and a `PROMPT_REGISTRY` ordered list covering exactly seven keys —
  `character.output_contract`, `narrator.system`, `narrator.system_long`, `director.who_is_up`,
  `director.rerank`, `director.branch`, `planner.system`. Move each agent's current constant text into
  the registry and have the agent module reference `registry.default("<key>")` so no wording changes.
  Add `resolve_prompts(*layers: Mapping[str, str]) -> dict[str, str]` that starts from registry
  defaults and applies each override layer in order, ignoring blank/unknown keys.
- **Rationale:** every later phase (context threading, settings endpoint, all three UIs) needs one
  canonical list of prompt keys + defaults; establishing it first with zero behaviour change keeps the
  refactor safe.
- **Action:** Run `uv run pytest utils/tests/backend/agents` (registry completeness, resolution
  layering, blank/unknown-key handling) + the existing agent tests to prove no wording drift. Once
  green, commit: `[Per-Story Prompts] (1/7) Complete: Central prompt registry + layered resolver.`

### Phase 2 — `prompt_overrides` on Storyline + Scenario (models, schemas, crud, migration)

- **Locations:** `web/backend/app/models/storyline.py`, `models/scenario.py`;
  `schemas/storyline.py`, `schemas/scenario.py`; `services/crud.py` (create/update wiring);
  new Alembic revision under `web/backend/alembic/versions/` (chained after the current head);
  tests under `utils/tests/backend/data/`.
- **Details:** add nullable `prompt_overrides: Mapped[dict | None]` (JSON) to both models; expose
  `promptOverrides: dict[str, str]` (default `{}`) on the read/input schemas via the existing
  `CamelModel`; wire create + update in `crud` (update already generic in places — confirm both
  entities round-trip). Migration adds the column to `storylines` and `scenarios` (nullable, no
  server default). Code normalises `None → {}` on read.
- **Rationale:** persistence must exist before the assembler can read storyline/scenario overrides and
  before the frontend can PATCH them via the existing `updateStoryline`/`updateScenario` endpoints
  (no new storyline/scenario routes needed).
- **Action:** Run `uv run pytest utils/tests/backend/data` (roundtrip + default-empty for both
  entities) and confirm `alembic upgrade head` applies cleanly on a scratch DB. Once green, commit:
  `[Per-Story Prompts] (2/7) Complete: prompt_overrides column on Storyline + Scenario (+migration).`

### Phase 3 — Thread resolved prompts through the turn loop

- **Locations:** `web/backend/app/services/settings_store.py` (new `prompts` namespace:
  `PROMPTS_KEY`, `get_prompts_overrides`, `update_prompts_overrides`);
  `services/assembler.py` (`TurnContext.prompts: dict[str, str]` + resolution call);
  the four agents read `ctx.prompts[key]` (fallback to registry default);
  tests under `utils/tests/backend/services/` + `agents/`.
- **Details:** `settings_store` stores global overrides as a flat `{key: text}` blob under the
  `"prompts"` key (mirrors `llm`/`library`/`comfy`). `assembler.assemble_context` calls
  `resolve_prompts(defaults, global_overrides, storyline.prompt_overrides or {}, scenario.prompt_overrides or {})`
  and stashes the result on `TurnContext.prompts`. Update `character_turn_agent`, `narrator_agent`,
  `director_agent`, `planner_agent` to pull their system text from `ctx.prompts.get(key, default)` —
  narrator selects `narrator.system_long` vs `narrator.system` by its existing `long` flag; director
  picks per method. No call-signature changes beyond reading `ctx`/passing the map where an agent
  method doesn't already receive context.
- **Rationale:** this is the phase that makes overrides actually take effect; isolating it lets us test
  the full precedence chain end-to-end.
- **Action:** Run `uv run pytest utils/tests/backend/agents utils/tests/backend/services` — assert a
  storyline override reaches each of the four agents' system message, a scenario override beats a
  storyline override, a global override beats the default, and an empty map yields the registry
  default. Once green, commit:
  `[Per-Story Prompts] (3/7) Complete: Resolved prompts flow through TurnContext into all four writing agents.`

### Phase 4 — Options endpoint: global prompts catalog + overrides

- **Locations:** `web/backend/app/schemas/settings.py` (`PromptSpecRead`, `PromptsConfigRead`
  `{catalog: [...], overrides: {...}}`, `PromptsConfigUpdate` `{overrides: {...}}`; add `prompts` to
  `SettingsRead`); `services/settings_store.py` (`get_prompts` returning catalog+overrides,
  `update_prompts`); `routes/options.py` (`GET /options` includes `prompts`; new
  `PATCH /options/prompts`); tests under `utils/tests/backend/api/`.
- **Details:** the catalog is derived from `PROMPT_REGISTRY` (key, agent, label, description, default);
  overrides come from the `prompts` settings blob. `PATCH /options/prompts` merges the posted overrides
  (empty-string value deletes a key → reverts to default). The catalog is what all three frontend
  surfaces consume to render fields + placeholders.
- **Rationale:** the frontend needs one place to fetch the list of editable prompts with their defaults;
  putting the catalog on the settings payload avoids duplicating default text in TS.
- **Action:** Run `uv run pytest utils/tests/backend/api` (GET returns catalog+overrides; PATCH
  sets/clears an override; unknown key rejected/ignored). Once green, commit:
  `[Per-Story Prompts] (4/7) Complete: /options prompts catalog + PATCH /options/prompts.`

### Phase 5 — Frontend: API types, shared editor, Options › Prompts tab

- **Locations:** `web/frontend/lib/api.ts` (`PromptSpec`, `PromptsConfig`, `PromptsConfigUpdate`;
  add `prompts` to `AppSettings`; `updatePromptsConfig`; add `promptOverrides` to `Storyline`/
  `Scenario` types + inputs in `lib/types.ts`); `features/options/useOptionsSettings.ts` (`savePrompts`);
  new `components/feature/PromptOverridesEditor.tsx`; new `features/options/tabs/PromptsTab.tsx`;
  `features/options/OptionsView.tsx` (register the tab); co-located `.test.tsx` files.
- **Details:** `PromptOverridesEditor` takes `{ catalog, overrides, onSave, busy?, warnContractKey? }`
  and renders **upper sub-tabs grouped by agent** (Character · Narrator · Director · Planner); each row
  = label + description + textarea (value = override, placeholder = default) + Reset button; a Save
  action emits the changed override map. It is reused verbatim by the storyline modal and scenario
  editor in Phase 6. `PromptsTab` wires it to global overrides via `opts.savePrompts`. Register
  `{ key: "prompts", label: "Prompts", sub: "writing agents" }` in `OptionsView` TABS + panel switch.
- **Rationale:** building the shared editor + the simplest consumer (global tab) first lets Phase 6
  reuse a proven component for the two harder-wired surfaces.
- **Action:** Run `cd web/frontend && npm test -- PromptOverridesEditor PromptsTab OptionsView` +
  `npm run typecheck`; accessibility/responsive pass on the tab (keyboard sub-tab nav, focus, labels,
  320/375/768/1024). Once green, commit:
  `[Per-Story Prompts] (5/7) Complete: Shared PromptOverridesEditor + Options Prompts tab (sub-tabbed).`

### Phase 6 — Frontend: storyline gear modal + per-scenario override

- **Locations:** `components/feature/StorylineMenu.tsx` (gear icon-button per row, alongside
  Edit/Delete); new `components/feature/StorylinePromptsModal.tsx`; `features/library/useLibraryState.ts`
  + `features/library/LibraryView.tsx` (modal state + wiring; fetch catalog once via `getSettings`);
  the scenario editor surface (confirm exact file — `components/feature/ScenarioForm.tsx` /
  `EntityModal.tsx`) gains a collapsible "Writing prompt overrides" section using the same editor,
  saved via `updateScenario`; co-located tests.
- **Details:** the gear opens `StorylinePromptsModal`, which reads `storyline.promptOverrides` + the
  catalog and saves via `updateStoryline({ promptOverrides })`. The scenario editor embeds
  `PromptOverridesEditor` scoped to that scenario, saving via `updateScenario({ promptOverrides })`.
  Both reuse the catalog fetched from `/options`.
- **Rationale:** these are the two author-facing surfaces the user asked for (gear next to Storyline
  selector + per-scenario overwrite); they depend on the shared editor from Phase 5.
- **Action:** Run `cd web/frontend && npm test -- StorylineMenu StorylinePromptsModal ScenarioForm` +
  `npm run typecheck`; accessibility/responsive pass (gear is a labeled IconButton; modal focus trap;
  320/375/768/1024). Once green, commit:
  `[Per-Story Prompts] (6/7) Complete: Storyline gear prompts modal + per-scenario override editor.`

### Phase 7 — Docs, full validation, merge to main

- **Locations:** `docs/api-contract.md`, `docs/data-flow.md`, `docs/design-system.md`,
  `docs/component-map.md`, `docs/structure.md`, `docs/documentation.md`, `docs/checklist.md`
  (new entry); this plan.
- **Details:** document the prompt registry, the resolution chain, the `prompts` settings namespace +
  `PATCH /options/prompts`, the `promptOverrides` fields on Storyline/Scenario, and the three UI
  surfaces. Record any deferred live-in-browser a11y pass (standing worktree shared-dir/CORS +
  configured-LLM constraint) in the checklist.
- **Rationale:** docs are the source of truth and must land with the behaviour change; the merge
  consolidates the feature onto `main`.
- **Action:** Full gate — backend `uv run pytest`, frontend `npm test`, `npm run typecheck`,
  `npm run lint`, `next build`. Once green, commit:
  `[Per-Story Prompts] (7/7) Complete: docs + validation.` Then merge the worktree branch into `main`,
  resolving any conflicts, and re-run the gate post-merge.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Prompt registry | Canonical keys + default text + metadata for the 4 writing agents; layered resolver | `web/backend/app/agents/prompt_registry.py` |
| Agent refactor | Agents read defaults from the registry, prompts from `ctx.prompts` | `web/backend/app/agents/{character_turn,narrator,director,planner}_agent.py` |
| Override columns | `prompt_overrides` JSON on Storyline + Scenario (+ migration, schemas, crud) | `web/backend/app/models/{storyline,scenario}.py`, `schemas/`, `services/crud.py`, `alembic/versions/` |
| Prompts settings namespace | Global overrides store + catalog + PATCH endpoint | `web/backend/app/services/settings_store.py`, `schemas/settings.py`, `routes/options.py` |
| Context threading | `TurnContext.prompts` resolved in the assembler | `web/backend/app/services/assembler.py` |
| Shared editor | Sub-tabbed prompt-override editor reused by 3 surfaces | `web/frontend/components/feature/PromptOverridesEditor.tsx` |
| Options Prompts tab | Global defaults editor | `web/frontend/features/options/tabs/PromptsTab.tsx`, `OptionsView.tsx`, `useOptionsSettings.ts` |
| Storyline gear modal | Per-storyline override editor next to the selector | `web/frontend/components/feature/StorylinePromptsModal.tsx`, `StorylineMenu.tsx`, `features/library/*` |
| Per-scenario override | Override editor in the scenario editor | scenario editor component + `lib/api.ts` `updateScenario` |
| API types | Prompt + override types & client fns | `web/frontend/lib/api.ts`, `lib/types.ts` |
| Backend tests | Registry, resolution, models, endpoint, agent threading | `utils/tests/backend/{agents,data,services,api}/` |
| Frontend tests | Editor, tab, modal, menu, scenario editor | co-located `*.test.tsx` |
| Docs | Contract, data-flow, design-system, component-map, structure, checklist | `docs/*.md` |
