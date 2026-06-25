# Velora — Agentic Setting Creator + Setting-node prep

## 1. Introduction

The **Character** and **Storyline** creators are fully agentic: a one-sentence
seed is sent to the configured LLM (via `agents/_common.py`), the draft is folded
back into editable fields, dropped reference files ground a single generation, and
the Character creator additionally renders a ComfyUI image. The **Setting** creator
is the laggard — it still lives inside the generic `EntityModal` and its "agentic"
button is a *client-only stub* (`useLibraryState.generate()` → `pickUnused(AI_SETTINGS)`),
with the Setting entity holding only `name` / `type` / `desc`.

This plan brings the Setting creator to parity with the other two **and** enriches
the Setting entity to carry the **Setting Node** metadata defined in
`Documents/Plans/4.story-graph-structure-prep.md` §4.1 — *base description*,
*current state*, and the (initially empty) *event timeline* — plus an optional
establishing image mirroring the Character portrait. The approach mirrors the
already-shipped Character Creator: add nullable columns (self-healed by the
preflight reconcile), a real `setting_agent`, a dedicated `SettingModal`
(extracted out of `EntityModal`, exactly as `CharacterModal` was), and the wire
plumbing in `lib/api.ts` + `useLibraryState`. **This is the prep phase: §1 node
*properties* only — no edges, no Event/Faction nodes, no Neo4j.** The event
timeline is added as an empty, play-accrued *seam* (a column + a read-only UI note),
documenting the §4.4 convergence point without building the graph — exactly how
the Character prep added base-identity material it "will later connect."

## 2. Gaps & Unanswered Questions

- **Which §4.1 buckets are *authored* vs. *accrued*?** (Assumption) Base description
  and current state are authored at creation (the agent drafts them); the event
  timeline is **play-accrued** and therefore ships **empty** with only the column +
  a read-only seam note. This matches §2 Step 2 ("…with its description and
  (initially empty) timeline in metadata") and the read-live/write-async boundary
  (§6) — no async writer exists yet, so nothing populates it.
- **Edges (from / present_at / controls / occurred_at / connected_to)?** (Assumption)
  Out of scope — they are graph structure (§4.3), explicitly deferred like the
  Character graph. We store node properties only.
- **Setting establishing image — in scope?** (Assumption) Yes, for true parity with
  the Character creator's portrait. It reuses the proven ComfyUI pipeline, is
  opt-in, and lands behind a `SceneArtModal` pop-up (the portrait analog). Offline
  tests keep validation green without a running ComfyUI.
- **Setting stats?** (Assumption) No — §3/§4 scope stats to the *Character* node
  ("how strong is Mei?"); a place has no stat block. The stat `appliesTo` seam is
  left untouched.
- **Type vocabulary for the agent.** (Assumption) The agent is told to pick from
  the canonical `SETTING_TYPES` list (mirrored in the agent module); the value is
  stored verbatim so a non-canonical label still persists (the chips just won't
  highlight).

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend data layer (Setting node metadata)

- **Locations:** `web/backend/app/models/setting.py` (new nullable columns
  `atmosphere`, `features`, `current_state` → `Text`; `image` → `String`;
  `timeline` → `JSONColumn`, nullable, default `list`), `web/backend/app/schemas/setting.py`
  (`SettingBase`/`Create`/`Update`/`Read` gain the fields; `timeline` typed as a
  list of entries, camelCase `currentState`), `web/backend/app/services/crud.py`
  (`create_setting`/`update_setting` carry the new fields), `web/backend/app/core/seed.py`
  (enrich the 5 Embergate settings with `atmosphere`/`features`/`current_state`;
  `timeline` stays `[]`), `utils/tests/backend/api/test_settings.py` (roundtrip +
  null-default assertions, mirroring `test_characters.py`).
- **Rationale:** edges can only connect nodes that already exist (§2); the node's
  metadata must land before the agent or UI can fill it. Nullable columns self-heal
  on the persistent dev DB via `bootstrap._reconcile_additive_columns`.
- **Action:** Run `uv run pytest utils/tests/backend/api/test_settings.py` (+ full
  backend suite), ruff + mypy. Once green, commit: `[Setting Creator] (1/5) Complete: Setting node metadata columns (atmosphere/features/current state/image/timeline) + seed + schemas.`

### Phase 2 — Backend setting agent + authoring routes

- **Locations:** `web/backend/app/agents/setting_agent.py` — `draft_setting(db, seed,
  docs_overview, storyline_id)` (seed → `name`/`type`/`desc`/`atmosphere`/`features`/
  `currentState`, grounded in the world primer/genre + dropped docs, reusing
  `_common.resolve_llm`/`docs_block`/`gen_params`/`extract_json` and a `_world_context`
  helper like `character_agent`) and `generate_scene_art_prompts(db, …)` (place
  description → watercolor **establishing-shot** positive/negative prompts, no
  people). `web/backend/app/services/media.py` — extract `to_webp()` + `save_webp()`
  from `portraits.py` (refactor `portraits.generate_portrait` onto it; behavior
  unchanged) and add `web/backend/app/services/scene_art.py` `generate_scene_art(...)`
  (landscape default, writes to `/media/scenes/…`). `web/backend/app/core/config.py`
  — add `scenes_dir` property. `web/backend/app/schemas/setting.py` — `SettingDraftRequest/Response`,
  `SceneArtPromptRequest/Response`, `SceneArtGenerateRequest/Response`. `web/backend/app/routes/settings.py`
  — `POST /settings/draft`, `POST /settings/scene-art-prompts`, `POST /settings/scene-art`
  declared **before** the `/settings/{id}` routes (route-ordering, like `characters.py`).
  Mount `/media/scenes` is already covered by the existing `/media` StaticFiles mount.
  `utils/tests/backend/agents/test_setting_agent.py` (offline `httpx.MockTransport`,
  mirroring `test_character_agent.py`).
- **Rationale:** this is the "agentic" core — a real model call replacing the
  client-only stub. Shared helpers keep the three authoring agents from drifting;
  the media refactor keeps WebP conversion DRY (one source of truth).
- **Action:** Run `uv run pytest utils/tests/backend/` (agents + api + portraits),
  ruff + mypy. Once green, commit: `[Setting Creator] (2/5) Complete: setting_agent (draft + scene-art prompts), scene-art render service, authoring routes.`

### Phase 3 — Frontend data path (types, API client, state)

- **Locations:** `web/frontend/lib/types.ts` — `Setting` gains `atmosphere?`,
  `features?`, `currentState?`, `image?`, `timeline?: SettingTimelineEntry[]` (+ a
  `SettingTimelineEntry` type matching §4.1's `{ summary, origin, participants, kind,
  visibility }`). `web/frontend/features/library/editor.ts` — `Draft` gains
  `atmosphere?`/`features?`/`currentState?`/`image?`/`timeline?` + editor-internal
  `_sceneArtPositive?`/`_sceneArtNegative?`; `DEFAULT_DRAFTS.setting` extended.
  `web/frontend/lib/api.ts` — `draftSetting`, `generateSceneArtPrompts`,
  `generateSceneArt` + result types (`SettingDraftResult`, `SceneArtPromptResult`,
  `SceneArtResult`). `web/frontend/features/library/useLibraryState.ts` — real
  `draftSetting()` (replacing the stub for settings), `generateSceneArtPrompts()`,
  `generateSceneArt()` (independent spinners, reusing the existing
  `generating`/`generatingPrompts`/`generatingPortrait` flags), `editSetting()`
  prefill of the new fields, and the `submit()` setting branch sending them.
  `web/frontend/test/api-mock.ts` — add the three new mocks + extend
  `createSetting`/`updateSetting` pass-through.
- **Rationale:** the modal (Phase 4) is presentational; the data path must exist
  first so the UI binds to real handlers, and the api-mock keeps the Library tests
  meaningful and offline.
- **Action:** Run `npm run typecheck` + the affected hook/route tests
  (`useLibraryState.*`, `api.test.ts`). Once green, commit: `[Setting Creator] (3/5) Complete: Setting types/Draft fields, api client (draft + scene art), useLibraryState handlers + api-mock.`

### Phase 4 — Frontend UI (SettingModal + SceneArtModal; extract from EntityModal)

- **Locations:** `web/frontend/components/feature/SettingModal.tsx` (new — mirrors
  `CharacterModal`: header with name + type chips, by-hand form for `desc` /
  `atmosphere` / `features` / `currentState`, agentic **Draft with Velora** panel,
  a **Scene art** compact preview + "Edit image" trigger, a read-only **Event
  timeline** seam section, the shared `ContextFilesPanel`, sticky footer actions).
  `web/frontend/components/feature/SceneArtModal.tsx` (new — the `PortraitModal`
  analog, landscape preview + editable prompts + generate). `web/frontend/components/feature/EntityModal.tsx`
  — drop `setting` (becomes **scenario-only**, mirroring the prior character
  extraction; update guard, `WIDTH`, comments). `web/frontend/features/library/LibraryView.tsx`
  — mount `<SettingModal lib={lib} />`. `web/frontend/components/feature/SettingCard.tsx`
  — show `image` as the card banner when present (monogram-style fallback to the
  existing striped "setting plate"). `web/frontend/features/library/SettingModal.test.tsx`
  (new — draft-from-seed, scene-art pop-up, doc-grounding, mirroring
  `CharacterModal.test.tsx`); confirm `LibraryView.editors.test.tsx`'s setting paths
  still pass (the "Add a Setting" entry now opens `SettingModal`).
- **Rationale:** a dedicated modal is the established pattern for a rich agentic
  creator; `EntityModal` shrinks to scenario-only just as it did when
  `CharacterModal` was extracted, keeping each modal focused.
- **Action:** Run `npm test` (full Vitest) + `npm run typecheck` + `npm run lint` +
  `npm run build`; structural a11y/responsive reasoning at 320/375/768/1024 (reusing
  the focus-trapped `Modal`, labelled inputs, `role=group` chips) — note the standing
  shared-dir live-preview constraint in the checklist. Once green, commit:
  `[Setting Creator] (4/5) Complete: SettingModal + SceneArtModal, EntityModal → scenario-only, card image, tests.`

### Phase 5 — Documentation + checklist + final validation

- **Locations:** `docs/api-contract.md` (Settings shape + new **Setting authoring**
  endpoint group + Setting Authoring Shapes; Media line mentions `/media/scenes`),
  `docs/data-flow.md` (setting authoring flow), `docs/documentation.md` (status:
  agentic Setting Creator + Setting-node prep landed), `docs/structure.md`
  (`agents/` now lists `setting_agent`; `services/` gains `media`/`scene_art`;
  `media/scenes/`), `docs/component-map.md` (`SettingModal`/`SceneArtModal`),
  `docs/checklist.md` (new completed entry + any deferred items).
- **Rationale:** Velora's definition of done requires docs to track behavior in the
  same change; `docs/` is the single source of truth.
- **Action:** Re-run the full backend + frontend suites once more for a clean
  end-to-end gate. Once green, commit: `[Setting Creator] (5/5) Complete: docs + checklist updated; full validation green.`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Setting node columns | `atmosphere`, `features`, `current_state`, `image`, `timeline` (nullable; self-heal) | `web/backend/app/models/setting.py` |
| Setting schemas | Base/Create/Update/Read + authoring request/response shapes | `web/backend/app/schemas/setting.py` |
| Seed enrichment | Embergate settings gain atmosphere/features/current state | `web/backend/app/core/seed.py` |
| Setting agent | `draft_setting` + `generate_scene_art_prompts` | `web/backend/app/agents/setting_agent.py` |
| Media helpers | Shared `to_webp`/`save_webp`; scene-art render | `web/backend/app/services/media.py`, `web/backend/app/services/scene_art.py` |
| Authoring routes | `POST /settings/draft`, `/settings/scene-art-prompts`, `/settings/scene-art` | `web/backend/app/routes/settings.py` |
| Setting types + Draft | New entity/draft fields + `SettingTimelineEntry` | `web/frontend/lib/types.ts`, `web/frontend/features/library/editor.ts` |
| API client | `draftSetting`, `generateSceneArtPrompts`, `generateSceneArt` | `web/frontend/lib/api.ts` |
| State handlers | Real setting draft + scene-art handlers; prefill/submit | `web/frontend/features/library/useLibraryState.ts` |
| SettingModal | Agentic Setting Creator modal | `web/frontend/components/feature/SettingModal.tsx` |
| SceneArtModal | Scene-art editor pop-up (portrait analog) | `web/frontend/components/feature/SceneArtModal.tsx` |
| Card image | Establishing image on the setting card | `web/frontend/components/feature/SettingCard.tsx` |
| Backend tests | Setting agent (offline) + CRUD roundtrip | `utils/tests/backend/agents/test_setting_agent.py`, `utils/tests/backend/api/test_settings.py` |
| Frontend tests | SettingModal agentic creator | `web/frontend/features/library/SettingModal.test.tsx` |
| Docs | api-contract, data-flow, documentation, structure, component-map, checklist | `docs/` |
