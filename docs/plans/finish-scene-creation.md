# Plan — Finish Scene Creation (Cast/Setting dropdowns + agentic Scenario Creator)

**Branch:** `feat/finish-scene-creation` (worktree: `.claude/worktrees/finish-scene-creation`)
**Status:** Done — all 6 phases complete; 266 backend + 171 frontend tests green; merged to `main`.
**Scope:** The scenario editor only (`EntityModal` + `ScenarioForm`) + a new backend Scenario Creator agent. No graph, no player, no migration (no new columns).

---

## 1. Introduction

Scene Creation is structurally in place but two pieces are unfinished. First, the
scenario editor's **Cast** and **Setting** inputs are flat `ToggleChip` grids; we
want a compact, side-by-side pair — **Cast as a multi-select dropdown**, **Setting
as a single-select dropdown** — built on a new reusable `MultiSelect` UI primitive.
Second, **"Draft with Velora" for scenarios is a client-only fake**: `useLibraryState.
generate()` runs an 850 ms `setTimeout`, picks a random `AI_SCENARIOS` entry, and
rolls dice for cast/setting. There is no `scenario_agent.py` and no `/scenarios/draft`
endpoint, unlike characters and settings which both have real agents. We replace the
stub with a real **agentic Scenario Creator** that selects a *valid* cast and setting
grounded in the active world.

The approach mirrors Velora's existing agent pattern exactly: a FastAPI agent
(`scenario_agent.draft_scenario`) reuses `_common.world_context()` / `_common.docs_block()`
for grounding, hands the model a numbered **roster** of the storyline's real characters
and settings, asks for **names** back, and resolves names → IDs in Python — dropping any
that don't match. The frontend gets a new `MultiSelect`, a `draftScenario()` API call,
and a hook handler that merges the drafted fields (including the resolved `cast` +
`settingId`) into the editor draft. No schema migration: every drafted field already has
a home on the existing `Scenario` shape.

---

## 2. Gaps & Unanswered Questions (assumptions taken)

- **The agent drafts cast + setting (not just prose).** The plan's whole motivation is
  that the stub "doesn't choose characters/scenes correctly." So `ScenarioDraftResponse`
  includes `castIds: list[str]` and `settingId: str`, resolved name→id server-side.
  *(A scout suggested scenarios are "cast-agnostic" — that is incorrect for this work; the
  plan explicitly requires the agent to choose a valid cast + setting.)*
- **Roster cap.** Bound the roster to a sane recency-ordered max (assume **40** characters
  and **40** settings — `list_*` already orders by `position, name`; take the first N) to
  keep the prompt bounded, mirroring `DOCS_CAP` discipline. Generous enough for any real
  world; refine later if one outgrows it.
- **Name resolution.** Case/whitespace-folded exact match. On collision or no match, drop
  (cast) / fall back to `""` (setting). Numbered-index fallback is documented as a future
  option but names are the default for readability.
- **Reasoning effort.** Default `DEFAULT_AUTHORING_EFFORT` (Medium), same as the other
  drafts.
- **`docsOverview` wiring.** The scenario modal has no `ContextFilesPanel` today; first cut
  grounds on **seed + world roster** only. The agent + API still *accept* `docsOverview`
  for parity/future wiring, but the hook passes `undefined`.
- **Branches.** `ScenarioForm` doesn't edit branches; the agent does not propose them.

No complex gaps require human intervention.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — `MultiSelect` UI primitive (frontend)

- **Locations:** `web/frontend/components/ui/MultiSelect.tsx` (new),
  `web/frontend/components/ui/MultiSelect.test.tsx` (new).
- **Build:** a button trigger that opens a popover `listbox`. A `multiple` prop switches
  between checkbox-style multi-select (Cast) and single-choice replacement (Setting).
  - **Props:** `options: { id; label; mono?; color?; portrait?; seal?: boolean }[]`,
    `selected: string[]`, `onChange(next: string[])`, `multiple?: boolean`,
    `placeholder?`, `label?`, `emptyText?`, `className?`, `disabled?`.
  - **Trigger display:** Cast → selected entries as small chips (reuse `Monogram` for the
    avatar/`mono`/`color`); Setting → chosen name with the `◆` seal. Empty → muted
    `placeholder`.
  - **Option rows:** each carries its affordance — `Monogram mono/color` for characters,
    `◆` for settings — and a selected check (`✓`) like `StorylineMenu`. `role="option"`
    with `aria-selected`; container `role="listbox"` + `aria-multiselectable` when
    `multiple`.
  - **Behavior parity** with `StorylineMenu`/`CreateMenu`: outside-click + `Esc` close
    (the `useEffect` mousedown/keydown pattern), roving focus over options
    (`ArrowUp`/`ArrowDown`/`Home`/`End`), `Enter`/`Space` toggles, focus returns to the
    trigger on close, visible `:focus-visible`. Trigger gets `aria-haspopup="listbox"`,
    `aria-expanded`, `aria-controls`.
- **Rationale:** The UI kit has no multi-select; both dropdowns in Phase 2 depend on it, so
  it is built and tested first as an isolated primitive.
- **Tests:** open/close (click + `Esc` + outside-click), select/deselect in `multiple`
  mode, single-choice replacement in single mode, keyboard navigation (arrow + Home/End +
  Enter), selected-state rendering (chips for multi, name for single), empty placeholder.
- **Action:** Run `npm test` (MultiSelect), `npm run typecheck`, `npm run lint`. Once green,
  commit: `[Finish Scene Creation] (1/6) Complete: Reusable accessible MultiSelect UI primitive.`

### Phase 2 — Swap `ScenarioForm` to the dropdowns (frontend)

- **Locations:** `web/frontend/components/feature/ScenarioForm.tsx`,
  `web/frontend/components/feature/ScenarioForm.test.tsx` (new if absent).
- **Build:** replace the two `ToggleChip` grids with a side-by-side
  `grid grid-cols-1 sm:grid-cols-2 gap-3` (the responsive pattern Genre/Tone use):
  - **Cast** → `<MultiSelect multiple>` over `characters` mapped to options
    (`{id, label: name, mono, color, portrait}`), `selected={draft.cast ?? []}`,
    `onChange` wired through a set-all setter (`setDraft("cast", next)`) so array
    semantics are unchanged. Keep `toggleCast` available but `onChange` replaces the array
    wholesale.
  - **Setting** → `<MultiSelect>` (single) over `settings` mapped to
    `{id, label: name, seal: true}`, `selected={draft.settingId ? [draft.settingId] : []}`,
    `onChange={(next) => setDraft("settingId", next[0] ?? "")}` (replace, never append).
  - **Empty states:** "No characters yet — add one first" / "No settings yet" via
    `emptyText`, since a brand-new storyline has an empty roster.
- **Rationale:** This is the visible UX change; it depends on Phase 1 and is independent of
  the backend agent.
- **Tests:** form renders both dropdowns; opening Cast and selecting a character pushes its
  id into `draft.cast` (via `setDraft`); selecting a setting sets `draft.settingId` and
  replaces (never appends) the prior choice; empty rosters render the empty text.
- **Action:** Run `npm test` (ScenarioForm), typecheck, lint, and a **a11y/responsive pass**
  for the dropdowns at 320/375/768/1024 (keyboard, focus, contrast) — defer the live
  in-browser pass per the standing shared-dev-server constraint and record it in
  `docs/checklist.md` if the server is busy. Once green, commit:
  `[Finish Scene Creation] (2/6) Complete: ScenarioForm uses side-by-side Cast multi-select + Setting single-select dropdowns.`

### Phase 3 — Scenario draft schemas + agent (backend)

- **Locations:** `web/backend/app/schemas/scenario.py` (extend),
  `web/backend/app/agents/scenario_agent.py` (new).
- **Schemas:** add `ScenarioDraftRequest(CamelModel)` (`seed: str`,
  `docs_overview: str | None = None`, `storyline_id: str | None = None`) and
  `ScenarioDraftResponse(CamelModel)` (`title`, `genre`, `tone`, `goal`, `opening` — all
  `str = ""` — plus `cast_ids: list[str] = Field(default_factory=list)` and
  `setting_id: str = ""`). CamelModel auto-aliases to `castIds`/`settingId` on the wire,
  matching the other `*DraftResponse` shapes.
- **Agent `draft_scenario(db, seed, docs_overview=None, storyline_id=None, *, reasoning=DEFAULT_AUTHORING_EFFORT)`:**
  1. Require a seed (blank → `APIError(400, "bad_request", <house-voice message>)`);
     `resolve_llm(db)`.
  2. Build the **roster**: `crud.list_characters(db, storyline_id)` +
     `crud.list_settings(db, storyline_id)` (only when `storyline_id`), capped
     (`_ROSTER_CAP = 40` each). Render numbered one-line entries — character:
     `name — role · traits`; setting: `name — type · desc` — into a `roster_block`.
  3. `_DRAFT_SYSTEM`: JSON-only output with exactly
     `title/genre/tone/goal/opening/cast/setting`, where `cast` is an array of character
     **names drawn only from the roster** and `setting` is **one** setting name from the
     roster. No prose, no fences.
  4. `user = f"Scene seed: {seed}{world_context(db, storyline_id)}{roster_block}{docs_block(docs_overview)}"`.
  5. `extract_json(llm.chat_complete(...))`; resolve each returned cast name → id via a
     normalized (case/whitespace-folded) lookup built from the roster; `cast_ids` =
     hits only (drop misses, dedupe). Resolve `setting` → its `setting_id`, or `""`.
  6. Return `ScenarioDraftResponse(...)`.
  - Reuse `_common` helpers throughout (`resolve_llm`, `world_context`, `docs_block`,
    `extract_json`, `gen_params`); no new grounding code.
- **Rationale:** The agent is the core deliverable; it depends on nothing new and unblocks
  the route (Phase 4) and the wiring (Phase 5).
- **Tests:** covered in Phase 4 (route-level, mirroring `test_character_agent.py`).
- **Action:** Run `uv run pytest` (existing agent suite stays green); `ruff` + `mypy`
  clean. Commit happens at the end of Phase 4 (agent + route + tests land together), or
  optionally split: `[Finish Scene Creation] (3/6) Complete: ScenarioDraftRequest/Response schemas + scenario_agent.draft_scenario with roster grounding and name→id resolution.`

### Phase 4 — Scenario draft route + tests (backend)

- **Locations:** `web/backend/app/routes/scenarios.py` (extend),
  `utils/tests/backend/agents/test_scenario_agent.py` (new).
- **Route:** `@router.post("/scenarios/draft", response_model=ScenarioDraftResponse)` →
  `scenario_agent.draft_scenario(db, data.seed, data.docs_overview, data.storyline_id)`.
  **Declared before any `/scenarios/{scenario_id}` route** (fixed sub-path ordering, like
  `/characters/draft` above `/characters/{id}`), or the dynamic route shadows it.
- **Tests** (mirror `test_character_agent.py`: `httpx.MockTransport`, no network,
  `_configure_llm`, `_completion`):
  - seed required → `400 bad_request`;
  - LLM unconfigured → `400 bad_request`;
  - the active world's name reaches the prompt (grounding — `"Embergate"` in body);
  - the roster reaches the prompt (a marker seed character/setting **name** appears in body);
  - returned cast names resolve to the right ids (response `castIds` are real ids);
  - an unknown cast name is **dropped**, not invented;
  - an unknown setting name resolves to `""`.
  - Use a fixture storyline with at least two known characters + one setting (reuse the
    seed `Embergate` storyline like the character-agent tests do).
- **Rationale:** Locks the contract and guarantees the resolve-and-drop grounding holds.
- **Action:** Run `uv run pytest utils/tests/backend/agents/test_scenario_agent.py` (+ full
  suite); `ruff` + `mypy` clean. Once green, commit:
  `[Finish Scene Creation] (4/6) Complete: POST /scenarios/draft route (above /{id}) + offline-mocked agent/route tests.`

### Phase 5 — Frontend wiring (api + hook + modal)

- **Locations:** `web/frontend/lib/api.ts`,
  `web/frontend/features/library/useLibraryState.ts`,
  `web/frontend/components/feature/EntityModal.tsx`,
  `web/frontend/test/api-mock.ts`,
  `web/frontend/features/library/useLibraryState.scenario.test.ts` (new).
- **api.ts:** add `ScenarioDraftResult` (`title`, `genre`, `tone`, `goal`, `opening`,
  `castIds: string[]`, `settingId: string`) + `draftScenario(seed, storylineId?, docsOverview?)`
  → `post<ScenarioDraftResult>("/scenarios/draft", { seed, docsOverview, storylineId })`,
  beside `draftCharacter`/`draftSetting`.
- **api-mock.ts:** add a `draftScenario` mock returning canned fields incl. `castIds` +
  `settingId` drawn from the seed roster.
- **useLibraryState:** add `draftScenario()` mirroring `draftSetting()` — guard
  `modal.type === "scenario"`, require trimmed `_prompt`, set `generating`,
  `await api.draftScenario(seed, activeStorylineId || undefined)`, merge returned
  `title/genre/tone/goal/opening` (`|| prev`) **plus** `cast: d.castIds`,
  `settingId: d.settingId`, set `_ai: true`, switch modal to manual mode; `setError` on
  failure; `finally setGenerating(false)`. Retire the scenario branch of `generate()`
  (leave `generate()` only if other types still use it; scenarios no longer do).
- **EntityModal:** point the scenario rail's **"❖ Draft with Velora"** button at
  `lib.draftScenario` (it's scenario-only already).
- **Rationale:** Connects the new endpoint to the UI; depends on Phases 1–4.
- **Tests:** the hook's `draftScenario` populates the draft (title + cast + settingId +
  `_ai`) from the mocked API; assert `api.draftScenario` was called; the modal button
  invokes `lib.draftScenario`.
- **Action:** Run `npm test` (hook + modal), typecheck, lint, `npm run build`. Once green,
  commit: `[Finish Scene Creation] (5/6) Complete: draftScenario API + hook + modal wiring; scenario draft is now a real backend call.`

### Phase 6 — Docs + validation + merge

- **Locations:** `docs/component-map.md`, `docs/api-contract.md`, `docs/data-flow.md`,
  `docs/documentation.md`, `docs/checklist.md`.
- **Docs:** `component-map` (`ScenarioForm` now uses dropdowns; new `MultiSelect`;
  `EntityModal` scenario draft now live, not stubbed); `api-contract`
  (`POST /scenarios/draft` request/response shapes + the roster-grounding/name→id note);
  `data-flow` (scenario authoring flow); `documentation` status; a `docs/checklist.md`
  entry (with any deferred a11y pass recorded).
- **Validation gate:** Backend `uv run pytest` green + `ruff` + `mypy` clean; Frontend
  Vitest + `tsc --noEmit` + ESLint + `next build` green; web/UI a11y + responsive pass for
  `MultiSelect` at 320/375/768/1024 (defer live preview per the standing 3346 constraint,
  recorded in checklist).
- **Merge:** merge `feat/finish-scene-creation` into `main`, resolving any conflicts.
- **Action:** Full gate green, then commit:
  `[Finish Scene Creation] (6/6) Complete: Docs + validation gate; merged to main.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| `MultiSelect` | Accessible multi/single dropdown primitive | `web/frontend/components/ui/MultiSelect.tsx` |
| `MultiSelect` tests | Open/close, select, keyboard, render | `web/frontend/components/ui/MultiSelect.test.tsx` |
| `ScenarioForm` dropdowns | Cast multi + Setting single, side-by-side grid | `web/frontend/components/feature/ScenarioForm.tsx` |
| `ScenarioForm` tests | Renders dropdowns; selection semantics | `web/frontend/components/feature/ScenarioForm.test.tsx` |
| Scenario draft schemas | `ScenarioDraftRequest` / `ScenarioDraftResponse` | `web/backend/app/schemas/scenario.py` |
| Scenario agent | `draft_scenario` (roster grounding + name→id resolution) | `web/backend/app/agents/scenario_agent.py` |
| Scenario draft route | `POST /scenarios/draft` above `/scenarios/{id}` | `web/backend/app/routes/scenarios.py` |
| Agent/route tests | Offline-mocked draft tests (mirror character agent) | `utils/tests/backend/agents/test_scenario_agent.py` |
| API client | `ScenarioDraftResult` + `draftScenario` | `web/frontend/lib/api.ts` |
| Hook handler | `draftScenario()`; retired scenario `generate()` branch | `web/frontend/features/library/useLibraryState.ts` |
| Modal wiring | Scenario rail button → `lib.draftScenario` | `web/frontend/components/feature/EntityModal.tsx` |
| Hook test | `draftScenario` populates draft from mocked API | `web/frontend/features/library/useLibraryState.scenario.test.ts` |
| Docs | component-map, api-contract, data-flow, documentation, checklist | `docs/*` |

---

## 5. Definition of Done

- Cast is a multi-select dropdown and Setting a single-select dropdown, side-by-side,
  collapsing to one column on mobile.
- "Draft with Velora" on a scenario calls the backend; the drafted cast + setting are
  **always** real members of the active storyline (no invented or dangling references).
- New backend + frontend tests green; full validation gate passed (or deferrals recorded).
- Docs updated in the same change; merged to `main`.

---

## 6. Out of Scope / Deferred

- Multi-setting scenarios (setting stays singular — no schema change).
- `docsOverview`/`ContextFilesPanel` grounding for scenario drafts (agent accepts it; UI
  doesn't wire it yet — first cut grounds on seed + world roster).
- Drafting branches.
- Roster cap strategy beyond a simple bounded list.

---

## 7. Risks & Notes

- **Route ordering:** `/scenarios/draft` must precede `/scenarios/{scenario_id}` or the
  dynamic segment shadows it (confirmed pattern from the characters router).
- **Name collisions** in the roster → resolve-and-drop keeps output safe; numbered-index
  fallback documented if a world holds duplicate names.
- **No DB migration:** no columns added; the standing Alembic follow-up is untouched.
- **Soft references preserved:** `resolveScenario`'s graceful fallback for a missing
  `setting_id`/cast id stays intact; the agent makes a bad reference far less likely by
  construction.

---

## Revision Log

| Version | Date | Change |
| --- | --- | --- |
| v1.0 | 2026-06-28 | Formal Velora plan derived from the source brief, grounded in the actual codebase (agent + frontend patterns mapped). |
