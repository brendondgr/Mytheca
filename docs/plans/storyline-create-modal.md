# Storyline Creation Modal

## 1. Introduction

Today the header storyline switcher's **"＋ New Storyline"** action calls `useLibraryState.createStoryline()`, which immediately POSTs an "Untitled Storyline" with default genre/tagline and switches to it — an empty world with nothing authored. This plan replaces that one-shot create with a **pop-up creation modal** (mirroring the existing `EntityModal` used for characters/settings/scenarios) where the author writes the storyline before it is created: a **title**, **genre**, a one-line **tagline**, and a new **multi-paragraph premise/description** of what the world is and what it's about.

The modal is also the forward-looking home for two seams the user wants visible now but wired later: a **drag-and-drop "context files" zone** (drop reference docs to ground the world) and an **agentic "Draft with Velora" panel** (describe the world in a sentence and let the brain draft the rest), matching the two-column manual/agentic layout `EntityModal` already uses. Both ship in this plan as **visible but non-functional** seams.

Scope spans both layers: a small additive backend change (a nullable `premise` column on `Storyline`, exposed through the existing `/storylines` CRUD contract), then the Next.js modal, state wiring, and the future seams. Work lands on a dedicated branch, isolated from the in-progress Options-Menu Phase 2 changes currently in the tree.

## 2. Gaps & Unanswered Questions

Resolved with the user:
- **Fields:** keep `title` / `genre` / `tagline`; **add** a multi-paragraph `premise` (full world description). _Confirmed._
- **Context files + agentic build:** build them now as **visible, non-functional seams**; wire later. _Confirmed._
- **Branch:** isolate this work on its own branch, separate from the uncommitted Options-Menu Phase 2 WIP. _Confirmed — the WIP is stashed and restored on `feat/options-menu`; this work branches off `main`._

Assumptions (simple gaps, proceeding):
- `premise` is a nullable `Text` column — additive, so the existing idempotent `create_all` suffices and no Alembic migration is introduced (consistent with `docs/checklist.md`). The `tagline` stays as the short switcher descriptor; `premise` is the long body.
- The agentic seam is **non-functional** (no fake client-side draft like the entity modals' seed-pool stub) — it's a labeled "coming soon" panel, since there is no storyline seed pool and no model call yet.
- `StorylineInput` / `StorylineSummary` in `lib/api.ts` derive from the `Storyline` type via `Omit`/`Partial`, so adding `premise?` to the type flows through the API client with no signature change.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend: add the `premise` field to Storyline

- **Locations:**
  - `web/backend/app/models/storyline.py` — add `premise: Mapped[str | None]` (`Text`, nullable).
  - `web/backend/app/schemas/storyline.py` — add `premise: str | None = None` to `StorylineBase` (→ `StorylineCreate`), `StorylineUpdate`, and `StorylineRead`.
  - `web/backend/app/services/crud.py` — `create_storyline()` passes `premise=data.premise`; `update_storyline()` already round-trips via `model_dump(exclude_unset=True)` (no change needed, verify).
  - `web/backend/app/services/seed.py` (Embergate seed) — give the seeded storyline a short multi-paragraph `premise` so the field is non-empty in dev.
  - Tests: `utils/tests/backend/api/test_storylines.py` (create with `premise` echoes back; PATCH updates it; omitting it on create yields `null`), `utils/tests/backend/data/test_schemas.py` / `test_models.py` (schema/model field present).
- **Rationale:** The frontend can't persist a world description until the contract and storage carry it. Doing the additive column first keeps every later frontend phase against a real, stable API.
- **Action:** Run `uv run pytest` (backend), `uv run ruff check .` + `uv run mypy web/backend` for hygiene. Update `docs/api-contract.md` (Storyline shape) and `docs/structure.md` (`storylines` columns) in the same commit. Once green, commit: `Storyline Create Modal (1/3) Complete: Added nullable premise field to Storyline (model, schema, CRUD, seed) + tests.`

### Phase 2 — Frontend: the manual creation modal (end-to-end functional)

- **Locations:**
  - `web/frontend/lib/types.ts` — add `premise?: string` to `Storyline` (flows into `StorylineInput`/`StorylineSummary` automatically).
  - `web/frontend/features/library/editor.ts` — extend `Draft` with `tagline?` and `premise?`; widen `ModalState["type"]` to `EntityType | "begin" | "storyline"`; add a `STORYLINE_DRAFT` default and a storyline branch in validation (require non-empty `title`). Keep the `EntityType`-keyed `Record`s (`WIDTH`, `EDITOR_META`, `DEFAULT_DRAFTS`, `PROMPT_*`) untouched so the three entity modals are unaffected.
  - `web/frontend/features/library/useLibraryState.ts` — replace the immediate `createStoryline()` with `openCreateStoryline()` (seeds the storyline draft + opens the modal) and a `submitStoryline()` (awaits `api.createStoryline`, then splices/activates the new storyline using the existing `emptyStoryline` + `resetForStoryline` flow). Export both; keep the old behavior reachable only through the modal's submit.
  - `web/frontend/components/feature/StorylineModal.tsx` — **new**. Built on `components/ui/Modal.tsx` like `EntityModal` (header/eyebrow, divider, footer with Cancel + Create). Manual form fields: Title (`Input`), Genre (`Input`), Tagline (`Input`), **Premise** (multi-row `TextArea`). Returns `null` unless `lib.modal.type === "storyline"`.
  - `web/frontend/components/feature/StorylineMenu.tsx` — `onCreate` now opens the modal (no behavior change to the prop name; `LibraryView` passes `lib.openCreateStoryline`).
  - `web/frontend/features/library/LibraryView.tsx` — render `<StorylineModal lib={lib} />` alongside `<EntityModal />`; pass `onCreate={lib.openCreateStoryline}` to `StorylineMenu`.
  - Test: `web/frontend/components/feature/StorylineModal.test.tsx` — opens on action, validates required title, submits via mocked `api.createStoryline`, closes on cancel/Esc.
- **Rationale:** This is the user-visible fix — "New Storyline" becomes a write-first pop-up that persists a real premise. Shipping the manual path fully before the seams keeps a green, demoable feature at each commit.
- **Action:** Run `npm run typecheck`, `npm run lint`, `npm test` (Vitest). Web/UI a11y + responsive pass: keyboard (modal focus-trap, Esc, Tab order), visible focus, label/`aria` on every field, contrast (AA), layout at **320 / 375 / 768 / 1024** (verify no overflow; mobile single-column). Update `docs/component-map.md` (new `StorylineModal`). Once green, commit: `Storyline Create Modal (2/3) Complete: New Storyline opens a write-first modal (title/genre/tagline/premise) that persists.`

### Phase 3 — Frontend: future seams (context files + agentic draft)

- **Locations:**
  - `web/frontend/components/feature/StorylineModal.tsx` — adopt the `EntityModal` two-column responsive shape: manual form left, an `<aside>` right rail on `md+` (tab-switched on mobile via the same `✎ By hand / ❖ Agentically` toggle pattern + `lib.setMode`). Add:
    - **Context files drop zone** — a dashed drop area ("Drag context files here to ground the world — coming soon") that is visibly disabled: `aria-disabled`, no drop handler wired, helper copy marking it non-functional.
    - **Agentic panel** — prompt `TextArea` + "❖ Draft with Velora" button rendered disabled/"coming soon" (no fake generate, no model call), mirroring the `EntityModal` agentic rail styling.
  - `web/frontend/components/feature/StorylineModal.test.tsx` — extend: the drop zone and agentic controls render and are non-interactive (disabled/`aria-disabled`); the mobile toggle switches columns.
- **Rationale:** Establishing the final layout now means the later wiring (file ingest + agentic draft-into-fields) is a fill-in, not a redesign, and the user sees the intended direction immediately.
- **Action:** Run `npm run typecheck`, `npm run lint`, `npm test`. Repeat the a11y + responsive pass (toggle keyboard-operable, disabled seams correctly announced, 320/375/768/1024). Note the deferred wiring in `docs/checklist.md`. Once green, commit: `Storyline Create Modal (3/3) Complete: Added visible non-functional context-files drop zone + agentic draft seam to the storyline modal.`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| `premise` column | Nullable long-text world description on Storyline | `web/backend/app/models/storyline.py` |
| Storyline schemas | `premise` on Create/Update/Read | `web/backend/app/schemas/storyline.py` |
| CRUD + seed | Persist `premise`; seed Embergate with one | `web/backend/app/services/crud.py`, `web/backend/app/services/seed.py` |
| Backend tests | premise create/patch/null-default coverage | `utils/tests/backend/api/test_storylines.py`, `utils/tests/backend/data/test_schemas.py` |
| Storyline type + draft | `premise?` on type; storyline modal state/draft/validation | `web/frontend/lib/types.ts`, `web/frontend/features/library/editor.ts` |
| State wiring | `openCreateStoryline` + `submitStoryline` | `web/frontend/features/library/useLibraryState.ts` |
| Storyline modal | Write-first pop-up: title/genre/tagline/premise + future seams | `web/frontend/components/feature/StorylineModal.tsx` |
| Menu + view wiring | Open modal from switcher; render modal | `web/frontend/components/feature/StorylineMenu.tsx`, `web/frontend/features/library/LibraryView.tsx` |
| Frontend tests | Modal open/validate/submit/cancel + seams render | `web/frontend/components/feature/StorylineModal.test.tsx` |
| Docs | Contract, structure, component map, checklist updates | `docs/api-contract.md`, `docs/structure.md`, `docs/component-map.md`, `docs/checklist.md` |
