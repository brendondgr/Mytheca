# Plan — Persist Portrait & Image Prompts (Character + Setting Editors)

## 1. Introduction

In the Character and Setting edit menus, an author can generate a portrait / establishing
image via the ComfyUI pipeline. The author can also generate and hand-edit the **positive**
and **negative** ComfyUI prompts that drive that render. Today only the resulting `/media/...`
image URL is persisted — the prompts are held in editor-only draft state (`_portraitPositive`/
`_portraitNegative` for characters, `_sceneArtPositive`/`_sceneArtNegative` for settings) and
are **discarded on save**. Re-opening the entity loses them, so the author cannot tweak-and-
re-render from where they left off.

The **Scenario** entity already solves this exact problem correctly: it has `image`,
`scene_art_positive`, `scene_art_negative` columns end-to-end (model → schema → CRUD → frontend
type → API → edit-hydration → submit). This plan replicates that proven pattern for Character
portraits and Setting images. The generation routes already exist and already return the
prompts — the only gap is **storage**: two nullable columns per entity plus the wiring to load
them on edit and send them on save. No new endpoints, no agent changes, no UI layout changes.

Column naming (mirrors each entity's existing draft fields and avoids churn):
- **Character:** `portrait_positive`, `portrait_negative` (wire: `portraitPositive`, `portraitNegative`).
- **Setting:** `scene_art_positive`, `scene_art_negative` (wire: `sceneArtPositive`, `sceneArtNegative`) — matches the existing `_sceneArtPositive`/`_sceneArtNegative` draft keys and the shared `SceneArt*` schemas.

All columns are nullable `String`, so the additive reconciler (`core/bootstrap._reconcile_additive_columns`) self-heals them on dev startup; Alembic migrations are added for the Postgres path.

## 2. Gaps & Unanswered Questions

- **Column names (assumption):** use `portrait_positive`/`portrait_negative` for Character and
  `scene_art_positive`/`scene_art_negative` for Setting (matches the frontend draft keys already
  in `editor.ts` and the shared SceneArt schemas). No human input needed.
- **Live image generation (assumption):** end-to-end image rendering needs a running ComfyUI
  server, which is not assumed available in this environment. Validation therefore covers the
  **persistence path** (pytest CRUD round-trips, vitest submit/edit-hydration, typecheck/build).
  The generate→edit→save→reopen flow is verified structurally + by tests, not by a live render.
- **Migration squashing (assumption):** one Alembic migration per entity (two files), each using
  `batch_alter_table` like the Scenario reference migration. No human input needed.
- **Worktree (assumption):** implement on an isolated worktree/branch to avoid disturbing the
  user's running dev server (port 3346) and the unrelated uncommitted `MultiSelect.tsx` change;
  merge to `main` at the end. No human input needed.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend: Character portrait prompts

- **Locations:**
  - `web/backend/app/models/character.py` — add nullable `portrait_positive` / `portrait_negative` `Mapped[str | None]` columns next to `portrait`.
  - `web/backend/app/schemas/character.py` — add `portrait_positive` / `portrait_negative` (default `None`) to `CharacterBase` (→ flows into `CharacterCreate`), `CharacterUpdate`, and `CharacterRead`.
  - `web/backend/app/services/crud.py` — in `create_character`, pass `portrait_positive=data.portrait_positive` and `portrait_negative=data.portrait_negative` to the `Character(...)` constructor. (`update_character` already applies them via the generic `model_dump(exclude_unset=True)` patch loop.)
  - `web/backend/alembic/versions/<ts>_character_portrait_prompt_columns.py` — new migration mirroring `20260628_121750_scenario_scene_art_columns.py`: `batch_alter_table('characters')` adding the two columns; `down_revision` set to the current head; downgrade drops them.
  - `utils/tests/backend/...` (character CRUD/API test module) — extend with a round-trip asserting the two prompt fields persist on create + update and default to `None`.
- **Rationale:** Storage must exist and be exposed through the schema before the frontend can send or receive the prompts. `create_character` assigns fields explicitly, so it must be touched; `update_character` does not.
- **Action:** Run `uv run pytest` for the affected backend character tests (ruff/mypy recommended). Once green, commit: `Portrait/Image Prompt Persistence (1/5) Complete: Character portrait_positive/negative columns, schemas, CRUD, migration + tests.`

### Phase 2 — Backend: Setting image prompts

- **Locations:**
  - `web/backend/app/models/setting.py` — add nullable `scene_art_positive` / `scene_art_negative` `Mapped[str | None]` columns next to `image`.
  - `web/backend/app/schemas/setting.py` — add `scene_art_positive` / `scene_art_negative` (default `None`) to `SettingBase` (→ `SettingCreate`), `SettingUpdate`, and `SettingRead`.
  - `web/backend/app/services/crud.py` — in `create_setting`, pass `scene_art_positive=data.scene_art_positive` and `scene_art_negative=data.scene_art_negative` to the `Setting(...)` constructor. (`update_setting` patch loop already covers it.)
  - `web/backend/alembic/versions/<ts>_setting_scene_art_prompt_columns.py` — new migration adding the two columns to `settings`, `down_revision` = the Phase 1 migration (linear chain), downgrade drops them.
  - `utils/tests/backend/...` (setting CRUD/API test module) — round-trip asserting persistence + null default.
- **Rationale:** Same storage gap on Setting; chain the migration after Phase 1's so the Alembic head stays linear.
- **Action:** Run `uv run pytest` for the affected backend setting tests. Once green, commit: `Portrait/Image Prompt Persistence (2/5) Complete: Setting scene_art_positive/negative columns, schemas, CRUD, migration + tests.`

### Phase 3 — Frontend: Character portrait prompt persistence

- **Locations:**
  - `web/frontend/lib/types.ts` — add `portraitPositive?: string | null` / `portraitNegative?: string | null` to the `Character` interface (so `CharacterInput` carries them).
  - `web/frontend/features/library/editor.ts` — add `_portraitPositive: ""`, `_portraitNegative: ""` to the `character` entry of `DEFAULT_DRAFT` (the `Draft` type already declares both keys).
  - `web/frontend/features/library/useLibraryState.ts` —
    - `editCharacter(...)`: hydrate `_portraitPositive: c.portraitPositive ?? ""`, `_portraitNegative: c.portraitNegative ?? ""` into the draft (mirrors `editScenario`).
    - character `submit` body: add `portraitPositive: d._portraitPositive?.trim() || null`, `portraitNegative: d._portraitNegative?.trim() || null`.
  - `utils/tests/frontend/...` (or co-located `useLibraryState`/library tests) — assert the character submit body includes the two prompt fields and that `editCharacter` hydrates them from a persisted character.
- **Rationale:** The generate handlers already write the prompts into `_portraitPositive`/`_portraitNegative`; this closes the loop so save persists them and edit restores them.
- **Action:** Run the relevant Vitest suites + `npm run typecheck`; web/UI change is data-only (no new layout/interactive surface), so the a11y/responsive surface is unchanged — note that in the commit. Once green, commit: `Portrait/Image Prompt Persistence (3/5) Complete: Character portrait prompts persist on save + rehydrate on edit + tests.`

### Phase 4 — Frontend: Setting image prompt persistence

- **Locations:**
  - `web/frontend/lib/types.ts` — add `sceneArtPositive?: string | null` / `sceneArtNegative?: string | null` to the `Setting` interface.
  - `web/frontend/features/library/editor.ts` — add `_sceneArtPositive: ""`, `_sceneArtNegative: ""` to the `setting` entry of `DEFAULT_DRAFT`.
  - `web/frontend/features/library/useLibraryState.ts` —
    - `editSetting(...)`: hydrate `_sceneArtPositive: s.sceneArtPositive ?? ""`, `_sceneArtNegative: s.sceneArtNegative ?? ""`.
    - setting `submit` body: add `sceneArtPositive: d._sceneArtPositive?.trim() || null`, `sceneArtNegative: d._sceneArtNegative?.trim() || null`.
  - `utils/tests/frontend/...` — assert the setting submit body includes the two prompt fields and `editSetting` hydrates them.
- **Rationale:** Identical closure for Setting; the SettingModal already binds the SceneArt prompts to the `_sceneArt*` draft keys.
- **Action:** Run the relevant Vitest suites + `npm run typecheck`. Data-only UI change (unchanged a11y/responsive surface — note in commit). Once green, commit: `Portrait/Image Prompt Persistence (4/5) Complete: Setting image prompts persist on save + rehydrate on edit + tests.`

### Phase 5 — Docs, full validation, merge

- **Locations:**
  - `docs/api-contract.md` — add the two new fields to the Character and Setting read/write shapes.
  - `docs/data-flow.md` — note the portrait/scene-art prompt fields now persist (parity with Scenario).
  - `docs/documentation.md` (Current Status) + `docs/checklist.md` — record the fix.
  - `docs/plans/portrait-image-prompt-persistence.md` — this file (mark done).
- **Rationale:** Docs must change in the same body of work per the global rules; this also runs the full gate before merge.
- **Action:** Run the **full** `uv run pytest` and the **full** frontend gate (`npm test`, `npm run typecheck`, `npm run lint`, `npm run build`). Once green, commit: `Portrait/Image Prompt Persistence (5/5) Complete: docs + full validation.` Then merge the branch into `main`, resolving any conflicts, and re-run the gate on `main`. Do not push or open a PR unless asked.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Character columns | `portrait_positive` / `portrait_negative` nullable String | `web/backend/app/models/character.py` |
| Character schemas | Prompt fields on Base/Create/Update/Read | `web/backend/app/schemas/character.py` |
| Character CRUD | `create_character` assigns the two fields | `web/backend/app/services/crud.py` |
| Character migration | Alembic `batch_alter_table('characters')` add/drop | `web/backend/alembic/versions/<ts>_character_portrait_prompt_columns.py` |
| Setting columns | `scene_art_positive` / `scene_art_negative` nullable String | `web/backend/app/models/setting.py` |
| Setting schemas | Prompt fields on Base/Create/Update/Read | `web/backend/app/schemas/setting.py` |
| Setting CRUD | `create_setting` assigns the two fields | `web/backend/app/services/crud.py` |
| Setting migration | Alembic `batch_alter_table('settings')` add/drop | `web/backend/alembic/versions/<ts>_setting_scene_art_prompt_columns.py` |
| Character FE type/wiring | Type fields + default draft + edit hydration + submit body | `web/frontend/lib/types.ts`, `web/frontend/features/library/editor.ts`, `web/frontend/features/library/useLibraryState.ts` |
| Setting FE type/wiring | Type fields + default draft + edit hydration + submit body | `web/frontend/lib/types.ts`, `web/frontend/features/library/editor.ts`, `web/frontend/features/library/useLibraryState.ts` |
| Backend tests | CRUD round-trip: persist + null default (character + setting) | `utils/tests/backend/...` |
| Frontend tests | Submit body includes prompts; edit hydrates prompts | `utils/tests/frontend/...` (or co-located) |
| Docs | Contract / data-flow / status / checklist updates | `docs/api-contract.md`, `docs/data-flow.md`, `docs/documentation.md`, `docs/checklist.md` |
