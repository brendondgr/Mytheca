# Plan — Seal pop-up + Storyline Statistics (with labeled bands)

## 1. Introduction

Two related editor changes to the Velora Library, both centered on the **Storyline** editor (`web/frontend/components/feature/StorylineModal.tsx`) and its backend stat seam.

**(A) Seal overhaul.** The storyline seal is currently a cramped inline picker (8 shapes, ~9 colors) living in the agentic aside. We move it into its own focused pop-up (mirroring the Character creator's `PortraitModal`): the main editor shows a compact **Seal** summary row with an **Edit** button that opens a `SealModal` offering **~2–3× more shapes**, a larger color palette, and a **custom color wheel** (`<input type="color">`). Separately, the **character accent palette grows from 8 → 12** colors (the user's stated per-character cap).

**(B) Storyline statistics.** The backend stat seam already exists end-to-end (`StatDefinition` per storyline, clamped `CharacterStat`, and a `propose_starting_stats` agent that reads the definitions) — but there is **no UI to define the universal stats** and **no concept of what a value range *means***. This plan adds, **inline under the World Primer** in `StorylineModal`, a Statistics editor where the author defines the world's universal stats (used by every character). Each stat gains **labeled bands ("tickers")** — e.g. Health `0–20` = "nearly dead", `81–100` = "very healthy" — persisted on the definition and fed into the agent so future state-extraction can name a character's condition from a number. The Character creator's existing "Propose" flow is updated to be band-aware.

The approach stays within Velora's stack: extend the FastAPI stat model/schema/service/routes (Postgres), thread the new shape through `lib/api.ts` + `lib/types.ts`, hold the editable stats on the `Draft`, persist a create/update/delete diff in `useLibraryState`, and render the editors in React/Tailwind matching the existing modal idiom.

---

## 2. Gaps & Unanswered Questions

Resolved by the user:
- **Stats location:** inline section **under "World Primer"** in `StorylineModal` (not a pop-up). *(answered)*
- **Bands/"tickers":** each stat carries labeled value bands defining what ranges mean, for future extraction. *(answered)*
- **Editing rule:** stats may be **freely added/edited/removed**; deleting a stat also prunes that stat's values from every character in the storyline. *(answered)*

Assumptions taken for simple gaps:
- **Band shape:** `{ min: int, max: int, label: str }`, stored as an ordered JSON list on the definition; bands are optional (empty list allowed) and need not tile the full range or be contiguous. Validation is light: each band requires `min ≤ max` and a non-empty label; bands are clamped/sorted for display but overlaps are not hard-rejected (authoring is iterative).
- **Range editing:** since edits are now free, `StatDefinitionUpdate` is relaxed to also accept `min/max/default/bands`; when a range narrows, existing `CharacterStat` values for that stat are **re-clamped** in the same transaction so no stored value sits out of bounds.
- **Seal shapes:** expand to ~22 single-glyph Unicode shapes (geometric + stars/marks) that render in the brand fonts; keep them dependency-free strings as today.
- **Color wheel:** native `<input type="color">` (no new dependency), surfaced alongside the swatch grid in `SealModal`; the chosen hex flows through the same `symbolColor` draft field.
- **New-storyline stats:** when creating (no id yet), stat definitions are persisted **after** the storyline `POST` returns an id, before the modal closes.

No complex gaps requiring further human intervention.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend: stat bands, full editing, delete
- **Locations:** `web/backend/app/models/stat.py` (`StatDefinition`: add nullable `bands` `JSONColumn`, default `[]`), `web/backend/app/schemas/stat.py` (new `StatBand` CamelModel `{min,max,label}`; add `bands: list[StatBand] = []` to `StatDefinitionBase`; relax `StatDefinitionUpdate` to also accept `min/max/default/bands`; validate band `min ≤ max` + non-empty label, and `min<max`/default-in-range when range fields are updated), `web/backend/app/services/stats.py` (apply range/band edits in `update_stat_definition` and **re-clamp** affected `CharacterStat` rows; new `delete_stat_definition` that removes the definition and prunes matching `CharacterStat` rows across the storyline's characters), `web/backend/app/routes/stats.py` (add `DELETE /storylines/{storyline_id}/stats/{key}` → 204), `web/backend/app/core/seed.py` (add sample `bands` to the Embergate `_STATS`, e.g. Health/Suspicion, exercising the new field).
- **Rationale:** The data layer and contract must carry bands and support free edit/delete before any UI or agent can use them. `bands` is nullable so the dev DB self-heals via the additive-column reconcile (per the documented dev-DB gotcha).
- **Tests:** extend `utils/tests/backend/api/test_stats.py` — band create/roundtrip, range-edit re-clamps a character value, delete prunes character stats + returns 404 afterward, band validation rejects bad input.
- **Action:** Run `uv run pytest utils/tests/backend/api/test_stats.py` (+ ruff/mypy). Once green, commit: `Seal & Stats (1/6) Complete: Stat definitions gain labeled bands, free range edit, and delete (with value pruning).`

### Phase 2 — Backend: band-aware stat proposal
- **Locations:** `web/backend/app/agents/character_agent.py` (`propose_starting_stats`: fold each definition's bands into `schema_lines` so the model sees what ranges mean; update `_STATS_SYSTEM` to instruct using the band meanings when choosing a starting value + rationale). No response-shape change (`StartingStatProposal` unchanged — value still clamped to `[min,max]`).
- **Rationale:** The agent process the user asked us to "change" must understand the band definitions so proposals reflect a coherent starting condition.
- **Tests:** extend `utils/tests/backend/agents/test_character_agent.py` — assert band text reaches the prompt (inspect the mocked request payload) and proposals stay clamped/complete.
- **Action:** Run `uv run pytest utils/tests/backend/agents/test_character_agent.py` (+ ruff/mypy). Once green, commit: `Seal & Stats (2/6) Complete: Starting-stat proposal is band-aware.`

### Phase 3 — Frontend: stats data layer (types, api, draft, persistence)
- **Locations:** `web/frontend/lib/types.ts` (export `StatBand` + `StatDefinition` types matching the wire shape), `web/frontend/lib/api.ts` (`listStatDefinitions`, `createStatDefinition`, `updateStatDefinition`, `deleteStatDefinition`), `web/frontend/features/library/editor.ts` (`Draft._stats?: StatDefinition[]`; keep a `_statsLoaded`/original snapshot for diffing or diff against fetched), `web/frontend/features/library/useLibraryState.ts` (on `editStoryline`, fetch `listStatDefinitions` into `draft._stats`; on `openCreateStoryline`, start `[]`; in `submitStoryline`, after the storyline is created/updated, **diff** `_stats` vs. the original and issue create/update/delete calls; new-storyline path persists stats against the returned id; independent error handling so a stat failure surfaces but doesn't lose the saved world).
- **Rationale:** The UI needs typed client calls and a load→edit→persist path before the editor component is built; diffing keeps the PUT/PATCH/DELETE surface honest.
- **Tests:** add a `useLibraryState` renderHook test (api mocked) covering edit-load + create/update/delete diff on save; extend `lib/api` coverage if a test file exists.
- **Action:** Run the relevant frontend tests + `npm run typecheck`/`lint`. Once green, commit: `Seal & Stats (3/6) Complete: Frontend stat-definition types, API client, and load/diff/persist wiring.`

### Phase 4 — Frontend: Statistics editor UI (under World Primer) + 12-color palette
- **Locations:** `web/frontend/components/feature/StorylineModal.tsx` (new **Statistics** section directly under the World Primer block: list each stat as an editable row — display name, key (slug, auto-from-name on add, locked after create), description, min/max/default numeric inputs, and a **bands editor** (add/remove `{min,max,label}` rows = the "tickers"); an "Add stat" control; per-row remove). Consider extracting the section into `web/frontend/components/feature/StatsEditor.tsx` to keep `StorylineModal` under the 800-line cap and testable in isolation. `web/frontend/lib/seed-data.ts` (`PALETTE`: add **4** colors → 12 total) — flows automatically into the Character accent picker and any palette consumers.
- **Rationale:** This is the core authoring surface for the universal stats; bands are entered here. The palette bump is a one-line data change with broad effect, validated visually.
- **A11y/responsive:** labelled number/text inputs, `role="group"` per stat, keyboard-operable add/remove buttons, no horizontal overflow at 320/375/768/1024 (rows wrap/stack on narrow widths).
- **Tests:** `StorylineModal`/`StatsEditor` test — add a stat, add a band, edit a value, remove a stat; assert the draft/state updates and that 12 accent swatches render.
- **Action:** Run frontend tests + typecheck/lint/build; a11y + responsive pass (document any deferred live-browser check per the standing shared-dir constraint). Once green, commit: `Seal & Stats (4/6) Complete: Storyline Statistics editor with labeled bands + 12-color character palette.`

### Phase 5 — Frontend: Seal pop-up (more shapes/colors + color wheel)
- **Locations:** `web/frontend/lib/seals.ts` (expand `SEAL_SYMBOLS` to ~22 glyphs; expand `SEAL_COLORS`), new `web/frontend/components/feature/SealModal.tsx` (nested `Modal`, raised `z`, mirroring `PortraitModal`: live preview chip + symbol grid + color swatch grid + a **custom color wheel** `<input type="color">` bound to `symbolColor`; "Done" closes), `web/frontend/components/feature/StorylineModal.tsx` (remove the inline seal picker from the aside; add a compact **Seal** summary row in the main column — preview glyph + current color + **Edit** button — and mount `SealModal` with local open state, like `CharacterModal` mounts `PortraitModal`).
- **Rationale:** Decouples the seal into a focused, roomier surface and removes clutter from the main editor; the color wheel gives unlimited customization the user asked for.
- **A11y/responsive:** `SealModal` reuses the focus-trapped `Modal`; symbol/color grids use `role="group"` + `aria-pressed`; the color input is labelled; trigger is a native button.
- **Tests:** update `StorylineModal` editor tests to open the seal pop-up before asserting symbol/color selection; a `SealModal` test for the wheel writing `symbolColor`.
- **Action:** Run frontend tests + typecheck/lint/build; a11y + responsive pass. Once green, commit: `Seal & Stats (5/6) Complete: Seal moved to a SealModal pop-up with expanded shapes, colors, and a custom color wheel.`

### Phase 6 — Docs, full validation, merge to main
- **Locations:** `docs/api-contract.md` (StatDefinition gains `bands`; new DELETE stat route; relaxed update), `docs/data-flow.md` (stat authoring + band-aware proposal), `docs/design-system.md` (seal shapes/colors/wheel; 12-color palette), `docs/documentation.md` (status note), `docs/checklist.md` (new "done" entry + any deferred live a11y pass), `docs/component-map.md` (`SealModal`, `StatsEditor`).
- **Rationale:** Velora requires docs updated in the same change that alters behavior; the validation gate must pass before "done".
- **Action:** Run the **full** suites — `uv run pytest` (all backend) + `npm test`/`typecheck`/`lint`/`build` (frontend). Once green, commit: `Seal & Stats (6/6) Complete: Docs updated; full validation green.` Then **merge the feature branch into `main`** (resolving any incompatibilities) per the user's request. Do not push.

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Stat bands + delete (backend) | `bands` column, relaxed update w/ re-clamp, delete + value pruning, DELETE route, seed bands | `web/backend/app/models/stat.py`, `schemas/stat.py`, `services/stats.py`, `routes/stats.py`, `core/seed.py` |
| Band-aware proposal | Bands folded into the stat-proposal prompt | `web/backend/app/agents/character_agent.py` |
| Stat API client + types | List/create/update/delete + `StatDefinition`/`StatBand` types | `web/frontend/lib/api.ts`, `web/frontend/lib/types.ts` |
| Stats persistence wiring | Load on edit, diff + create/update/delete on save | `web/frontend/features/library/useLibraryState.ts`, `features/library/editor.ts` |
| Statistics editor UI | Inline stats + bands editor under World Primer | `web/frontend/components/feature/StatsEditor.tsx`, `StorylineModal.tsx` |
| 12-color palette | 4 colors added to the character accent palette | `web/frontend/lib/seed-data.ts` |
| Seal pop-up | `SealModal` + expanded shapes/colors + color wheel; main-area Seal row | `web/frontend/components/feature/SealModal.tsx`, `lib/seals.ts`, `StorylineModal.tsx` |
| Backend tests | Band roundtrip, re-clamp, delete pruning, band-aware prompt | `utils/tests/backend/api/test_stats.py`, `utils/tests/backend/agents/test_character_agent.py` |
| Frontend tests | Stats persistence diff, stats editor, seal pop-up, 12 swatches | `web/frontend/features/library/*.test.ts(x)`, `components/feature/*.test.tsx` |
| Docs | Contract, data-flow, design-system, component-map, status, checklist | `docs/*.md` |
</content>
</invoke>
