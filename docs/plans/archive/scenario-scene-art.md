# Scenario Scene Art

## 1. Introduction

Scenarios are the "live truth object" for each scene in Mytheca, but unlike Characters (which carry a portrait) and Settings (which carry an establishing image), they have no visual art. This plan adds a full scene-art pipeline to Scenarios that mirrors the pattern already proven for Settings: the author can generate a watercolor establishing image — grounded in the scenario's title, genre, tone, goal, opening prose, and the referenced setting — using the existing ComfyUI workflow. The resulting WebP is persisted on the server and linked back to the scenario row.

The work spans five phases: a data-layer expansion of the `Scenario` model (new nullable `image`, `scene_art_positive`, and `scene_art_negative` columns); a new agent function + backend routes for prompt generation and image rendering; a frontend data-path update (types, API client, `useLibraryState` handlers, submit wiring); a UI integration that adds a compact scene-art preview and an `SceneArtModal` pop-up inside `EntityModal`; and a final docs + validation pass that confirms green suites and records the change across all affected docs. Every phase ends with a local commit and no push.

---

## 2. Gaps & Unanswered Questions

- **Prompt subject for scenarios (simple gap):** Setting scene-art is an "establishing shot of the LOCATION ITSELF — no people." For a scenario, the prompt should convey the *scene moment* — the setting's space as it appears *in this specific scenario* (time of day, tension level, tone). The system prompt will adapt the setting's approach with scenario-specific cues (tone, genre, goal summary) while keeping "no people as the subject" so the style stays consistent. Assumed: this is the right framing.
- **`scene_art_positive` / `scene_art_negative` persistence (simple gap):** The Setting stores prompts only in the `Draft` (editor-internal `_sceneArtPositive` / `_sceneArtNegative`) and saves only the rendered `image` URL to the DB. For parity and future reuse, this plan **also persists the prompts** to the new `scene_art_positive` / `scene_art_negative` columns so they survive a modal close/re-open and can be pre-filled when editing. The submit body will include them.
- **`ScenarioCard` art display (simple gap):** `SettingCard` shows a scene-art banner when `image` is set. `ScenarioCard` will receive the same treatment — an optional banner image at the top of the card (below the header row) when `image` is non-null. No layout breaking change; the card grows a few pixels when art is present, consistent with `SettingCard`.
- **Orphaned-media cleanup (simple gap):** `services/media_cleanup.py` currently tracks `Character.portrait` and `Setting.image`. `Scenario.image` should be added so rendered WebPs from deleted scenarios are reclaimed by the cleanup tool.
- **Alembic vs. additive-reconcile (simple gap):** The three new columns are nullable, so the existing additive reconciler (`bootstrap._reconcile_additive_columns`) will self-heal them on first run with no manual `ALTER`. No Alembic migration is needed.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Data Layer

**Goal:** Add the three new nullable columns to `Scenario` and expose them through all schema layers; update `media_cleanup` to track scenario images.

#### Step 1.1 — Extend the `Scenario` ORM model
- **Location:** `web/backend/app/models/scenario.py`
- **Changes:** add three `Mapped[str | None]` columns with `mapped_column(String, nullable=True, default=None)`:
  - `image` — relative `/media/scenes/…` URL of the rendered WebP.
  - `scene_art_positive` — positive ComfyUI prompt (editable, persisted).
  - `scene_art_negative` — negative ComfyUI prompt (editable, persisted).
- **Rationale:** These must exist in the ORM before the schemas, routes, or tests can reference them; nullable + default=None means the additive reconciler handles the live DB.

#### Step 1.2 — Update Pydantic schemas
- **Location:** `web/backend/app/schemas/scenario.py`
- **Changes:**
  - `ScenarioBase`: add `image: str | None = None`, `scene_art_positive: str | None = None`, `scene_art_negative: str | None = None`.
  - `ScenarioUpdate`: add the same three optional fields (`str | None = None`).
  - `ScenarioRead`: add `image: str | None = None`, `scene_art_positive: str | None = None`, `scene_art_negative: str | None = None`.
  - Add scene-art authoring schemas at the bottom of the file (reuse the same shape as `setting.py` but name them `ScenarioSceneArtPromptRequest`, `ScenarioSceneArtGenerateRequest`; re-export `SceneArtPromptResponse` and `SceneArtGenerateResponse` from `setting.py` for the response types — or simply import them in `routes/scenarios.py` directly).
- **Rationale:** Schema changes must precede route / service changes so the Pydantic models validate correctly.

#### Step 1.3 — Update `ScenarioSceneArtPromptRequest` schema (scenario-specific fields)
- **Location:** bottom section of `web/backend/app/schemas/scenario.py`
- The request body fields will be:
  - `title: str = ""`
  - `genre: str | None = None`
  - `tone: str | None = None`
  - `goal: str | None = None`
  - `opening: str | None = None`
  - `setting_name: str | None = None` — frontend passes the resolved setting name so the prompt can name the place.
  - `setting_desc: str | None = None` — short setting description for richer context.
  - `notes: str | None = None`
- **Rationale:** Different from the setting's `SceneArtPromptRequest` because the context fields are scenario-specific.

#### Step 1.4 — Update `media_cleanup.py`
- **Location:** `web/backend/app/services/media_cleanup.py`
- **Change:** in `scan_orphans`, add a query for `Scenario.image` alongside the existing `Setting.image` query; add any non-null values to the referenced set so in-use scenario images are never deleted.
- **Rationale:** Without this, any scenario-associated WebP would appear as an orphan and be eligible for deletion.

#### Step 1.5 — Update CRUD in `services/crud.py`
- **Location:** `web/backend/app/services/crud.py`
- **Change:** ensure `create_scenario` and `update_scenario` pass through the three new fields from the create/update schemas to the ORM model. (They should be automatically handled if the schema fields match the model columns and the CRUD uses `data.model_dump(exclude_unset=True)` — verify this is the pattern; if not, add explicit field assignment.)
- **Rationale:** The CRUD layer must not silently drop the new fields.

#### Step 1.6 — Write backend tests (Phase 1)
- **Location:** `utils/tests/backend/api/test_scenarios.py` (new file or add to existing scenario tests)
- **Tests:**
  1. `test_scenario_image_default_null` — create a scenario; confirm `image` / `scene_art_positive` / `scene_art_negative` are `null` in the read response.
  2. `test_scenario_image_roundtrip` — PATCH a scenario with `image="/media/scenes/x.webp"`, `sceneArtPositive="a, b, c"`, `sceneArtNegative="d, e"`; re-read and confirm values survive.
  3. Extend or add the `media_cleanup` test to confirm a scenario-linked image is reported as referenced (not orphaned).

**Action:** Run `uv run pytest utils/tests/backend/` (all backend tests) + `uv run ruff check .` + `uv run mypy web/backend`. Once green, commit:
> `[Scenario Scene Art] (1/5) Complete: Data layer — Scenario image/prompts columns, schema update, media-cleanup integration, roundtrip tests.`

---

### Phase 2 — Agent + Routes

**Goal:** Add the scene-art prompt-generation function to `scenario_agent.py` and expose two new POST routes on the scenarios router.

#### Step 2.1 — Add `generate_scene_art_prompts` to `scenario_agent.py`
- **Location:** `web/backend/app/agents/scenario_agent.py`
- **New function signature:**
  ```python
  def generate_scene_art_prompts(
      db: Session,
      *,
      title: str = "",
      genre: str | None = None,
      tone: str | None = None,
      goal: str | None = None,
      opening: str | None = None,
      setting_name: str | None = None,
      setting_desc: str | None = None,
      notes: str | None = None,
      reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT,
  ) -> SceneArtPromptResponse:
  ```
- **System prompt (`_SCENE_ART_SYSTEM`):** adapt the setting agent's scene-art system prompt for scenario context. Key differences:
  - The image should depict the **specific setting as it appears in this scenario** — the same location, but shaped by the scenario's tone, time of day, and tension level (pulled from `tone` and `goal`).
  - Maintain "NO people as the subject" so the style is consistent with setting art.
  - Positive prompt guidance: lead with the setting name + scenario tone/genre, then the place's salient features, the scenario's atmosphere (derived from `tone` + `opening` cues), then watercolor style tags.
  - Negative prompt guidance: same as setting (people, portrait, photorealistic, 3D, text, watermark, blurry, lowres).
- **User message:** concatenate available fields into a concise scene description block; skip null/empty fields.
- **Response:** return `SceneArtPromptResponse` (imported from `app.schemas.setting` — same shape, no duplication).
- **Rationale:** Reuses the existing `_common.resolve_llm`, `extract_json`, `gen_params`, and `SceneArtPromptResponse` patterns; keeps the agent consistent with the setting/character agents.

#### Step 2.2 — Add routes to `routes/scenarios.py`
- **Location:** `web/backend/app/routes/scenarios.py`
- **New routes** (declared immediately after `POST /scenarios/draft` and **before** `GET /scenarios/{scenario_id}` to avoid path shadowing):
  ```
  POST /scenarios/scene-art-prompts  → SceneArtPromptResponse
  POST /scenarios/scene-art          → SceneArtGenerateResponse
  ```
- `/scenarios/scene-art-prompts` calls `scenario_agent.generate_scene_art_prompts(db, **data.model_dump())`.
- `/scenarios/scene-art` reuses `scene_art.generate_scene_art(db, data.positive, data.negative, ...)` exactly as the setting route does — no new service code needed.
- Import `ScenarioSceneArtPromptRequest` from `app.schemas.scenario`; import `SceneArtGenerateRequest`, `SceneArtGenerateResponse`, `SceneArtPromptResponse` from `app.schemas.setting`.
- **Rationale:** Placing these before the `{scenario_id}` dynamic segment prevents "scene-art-prompts" and "scene-art" being captured as scenario ids.

#### Step 2.3 — Write backend tests (Phase 2)
- **Location:** `utils/tests/backend/api/test_scenario_agent.py` (new file)
- **Tests (all offline-mocked via `httpx.MockTransport` — no real LLM/ComfyUI):**
  1. `test_scene_art_prompts_no_description` — call with all empty fields; expect `400 bad_request`.
  2. `test_scene_art_prompts_llm_unconfigured` — no LLM settings; expect `400 llm_unconfigured`.
  3. `test_scene_art_prompts_returns_positive_negative` — mock LLM returns `{"positive": "p", "negative": "n"}`; confirm response fields.
  4. `test_scene_art_prompts_title_reaches_prompt` — mock `llm.chat_complete` captures messages; assert the title and tone appear in the user message.
  5. `test_scenario_scene_art_route_needs_positive` — POST `/scenarios/scene-art` with empty `positive`; expect `400`.

**Action:** Run `uv run pytest utils/tests/backend/` + ruff + mypy. Once green, commit:
> `[Scenario Scene Art] (2/5) Complete: Agent function + scene-art-prompts + scene-art routes, 5 offline tests.`

---

### Phase 3 — Frontend Data Path

**Goal:** Propagate the new fields through the frontend type system, API client, and state hook.

#### Step 3.1 — Update `lib/types.ts`
- **Location:** `web/frontend/lib/types.ts`
- **Changes to `Scenario` interface:**
  - Add `image?: string | null` — relative `/media/…` URL of the rendered WebP.
  - Add `sceneArtPositive?: string | null` — persisted positive prompt.
  - Add `sceneArtNegative?: string | null` — persisted negative prompt.
- **Rationale:** The TypeScript type must match the extended `ScenarioRead` wire shape before the API client or hook can reference the fields.

#### Step 3.2 — Update `lib/api.ts`
- **Location:** `web/frontend/lib/api.ts`
- **Add two new exported functions:**

  ```ts
  // Scenario scene-art prompts
  export const generateScenarioSceneArtPrompts = (body: {
    title?: string;
    genre?: string;
    tone?: string;
    goal?: string;
    opening?: string;
    settingName?: string;
    settingDesc?: string;
    notes?: string;
  }) => post<SceneArtPromptResult>("/scenarios/scene-art-prompts", body);

  // Scenario scene-art render
  export const generateScenarioSceneArt = (body: {
    positive: string;
    negative?: string;
    baseUrl?: string;
    workflow?: string;
    width?: number;
    height?: number;
    steps?: number;
    cfg?: number;
  }) => post<SceneArtResult>("/scenarios/scene-art", body);
  ```
- Re-use the existing `SceneArtPromptResult` and `SceneArtResult` interfaces — they are already the right shape (`{ positive, negative }` / `{ image }`).
- **Rationale:** New API-client functions must exist before the hook or UI can call them.

#### Step 3.3 — Update `features/library/editor.ts`
- **Location:** `web/frontend/features/library/editor.ts`
- **Changes:**
  - The `Draft` interface already has `image?: string | null` (shared with Setting). No new field needed for image.
  - `_sceneArtPositive` and `_sceneArtNegative` already exist in `Draft` (shared with Setting).
  - Update `DEFAULT_DRAFTS.scenario` to add `image: null` (so the scenario draft's image starts cleared).
- **Rationale:** The editor draft's scene-art fields are already defined for the Setting path and can be shared; we only need to ensure the scenario default initialises them.

#### Step 3.4 — Update `features/library/useLibraryState.ts`
- **Location:** `web/frontend/features/library/useLibraryState.ts`
- **New handlers (modeled exactly on the setting counterparts but guarding `modal.type !== "scenario"`):**

  ```ts
  async function generateScenarioSceneArtPrompts() { … }
  async function generateScenarioSceneArt() { … }
  ```

  - `generateScenarioSceneArtPrompts`: uses `draft.title`, `draft.genre`, `draft.tone`, `draft.goal`, `draft.opening`, plus the resolved setting's `name`/`desc` (look up `settings.find(s => s.id === draft.settingId)`); calls `api.generateScenarioSceneArtPrompts`; sets `_sceneArtPositive` + `_sceneArtNegative` on draft.
  - `generateScenarioSceneArt`: reads `draft._sceneArtPositive`; calls `api.generateScenarioSceneArt`; sets `draft.image`.
  - Both use `setGeneratingPrompts` / `setGeneratingPortrait` (shared spinners, just as the Setting path does).

- **Update `submit()` scenario branch:**
  - Add `image: d.image || null` to the scenario PATCH/create body.
  - Add `sceneArtPositive: d._sceneArtPositive?.trim() || null` and `sceneArtNegative: d._sceneArtNegative?.trim() || null` to persist the edited prompts.

- **Update `editSetting`-analog for `editScenario` prefill (the existing path in `openModal` / `openEdit`):**
  - When opening a scenario for edit, pre-fill `image`, `_sceneArtPositive` (from `scenario.sceneArtPositive`), and `_sceneArtNegative` (from `scenario.sceneArtNegative`) in `setDraftState`.
  - **Location:** find the scenario branch in the `openEdit` / `openModal` block around line 520–540 of `useLibraryState.ts`.

- **Expose the new handlers** at the bottom of `useLibraryState`'s return object alongside `generateSceneArtPrompts` / `generateSceneArt`.

#### Step 3.5 — Extend the API mock and write hook tests
- **Location:** `web/frontend/lib/api.test.ts` (or `api-mock` if one exists) and `web/frontend/features/library/useLibraryState.test.ts` (or equivalent hook test file)
- **Tests:**
  1. `generateScenarioSceneArtPrompts` calls `POST /scenarios/scene-art-prompts` with the right body.
  2. `generateScenarioSceneArt` calls `POST /scenarios/scene-art` and returns `{ image }`.
  3. `useLibraryState.generateScenarioSceneArtPrompts` sets `_sceneArtPositive`/`_sceneArtNegative` on draft.
  4. `useLibraryState.submit()` for a scenario includes `image`, `sceneArtPositive`, `sceneArtNegative` in the body.

**Action:** Run `npm test` (Vitest, from `web/frontend/`) + `npm run typecheck` + `npm run lint`. Once green, commit:
> `[Scenario Scene Art] (3/5) Complete: Frontend data path — types, api.ts, useLibraryState handlers, submit wiring, hook tests.`

---

### Phase 4 — UI

**Goal:** Surface scene-art generation in `EntityModal` (scenario modal) and show the rendered image on `ScenarioCard`.

#### Step 4.1 — Add scene-art section to `EntityModal` (agentic aside)
- **Location:** `web/frontend/components/feature/EntityModal.tsx`
- **Changes:**
  - Import `useState` (to track `sceneArtOpen`) and `SceneArtModal` + `mediaUrl`.
  - Add `const [sceneArtOpen, setSceneArtOpen] = useState(false)` **before** the early `if (!m || m.type !== "scenario") return null` guard (rules-of-hooks).
  - In the agentic aside column, **above** the "Draft with Mytheca" section, insert a scene-art panel mirroring `SettingModal`'s aside section:
    - A `FieldLabel` "Scene art".
    - A compact `aspect-[16/9]` preview box: shows the rendered `<img>` when `imageUrl` is set, otherwise the empty-state `◇` / "No scene art yet" placeholder.
    - An "✎ Edit image" `Button` that sets `sceneArtOpen(true)`.
    - A divider `<div>` between this and the Draft with Mytheca section.
  - Compute helpers (before the return):
    - `const imageUrl = d.image ? mediaUrl(d.image) : null`
    - `const hasDescription = Boolean((d.title || d.goal || d.opening || "").toString().trim())`
    - `const canRenderSceneArt = Boolean((d._sceneArtPositive ?? "").trim())`
  - Render `<SceneArtModal>` at the bottom (before closing the outer modal), wired to `lib.generateScenarioSceneArtPrompts` / `lib.generateScenarioSceneArt`.
  - **No change** to the By-hand `ScenarioForm` column — scene art is an agentic/aside concern only (consistent with `SettingModal`).
  - **Width:** Expand the modal `WIDTH` constant from `"sm:w-[600px] md:w-[960px]"` to `"sm:w-[520px] md:w-[920px] lg:w-[1120px]"` so the wider agentic aside has room for the 16:9 preview — matching `SettingModal`'s width.

#### Step 4.2 — Show scene art on `ScenarioCard`
- **Location:** `web/frontend/components/feature/ScenarioCard.tsx`
- **Changes:**
  - Accept `image?: string | null` as a prop (or read from the `scenario` prop if the card already receives the full `Scenario` object — verify in the file).
  - When `image` is non-null, render a `<div className="aspect-[16/9] w-full overflow-hidden">` with an `<img>` at the top of the card body (below the header row, above the genre/tone/goal content), similar to how `SettingCard` shows its establishing banner.
  - Use `mediaUrl(image)` from `@/lib/api` for the full URL.
  - Keep the card compact when `image` is null (no space reserved for absent art).

#### Step 4.3 — Verify the compact thumbnail in the modal header area (matching SettingModal)
- The `SettingModal` shows a tiny `48px × 85px` scene-art thumbnail beside the modal title when an image exists. Optionally add the same to `EntityModal`'s scenario title header row for consistency — a compact right-aligned thumbnail when `imageUrl` is set.
- This is a nice-to-have: include it if it fits cleanly in the existing title row; skip if it complicates the layout.

#### Step 4.4 — Write frontend UI tests
- **Location:** `web/frontend/components/feature/EntityModal.test.tsx` (new file) or extend the existing `ScenarioForm.test.tsx`
- **Tests (Vitest + RTL, mocked `useLibraryState`):**
  1. `EntityModal` renders with a scenario modal state and the form is visible.
  2. The "Edit image" button opens the `SceneArtModal` pop-up (`sceneArtOpen = true`).
  3. The scene-art preview shows a placeholder when `draft.image` is null.
  4. The scene-art preview renders an `<img>` when `draft.image` is set.
- **Location:** `web/frontend/components/feature/ScenarioCard.test.tsx` (add to or create)
  5. `ScenarioCard` renders without an image banner when `image` is null/undefined.
  6. `ScenarioCard` renders the banner `<img>` when `image` is a `/media/scenes/...` URL.

**Action:** Run `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`. Web/UI changes additionally require the accessibility + responsive checklist:
- `EntityModal` scenario: keyboard operability (By-hand / Agentically toggle + form fields + "Edit image" button reachable via Tab/Enter/Space); focus returns to the "Edit image" trigger when `SceneArtModal` closes; `SceneArtModal` is focus-trapped.
- 320 / 375 / 768 / 1024 px — no horizontal overflow; the agentic aside collapses on mobile (hidden below the toggle); the scene-art preview is `aspect-[16/9]` (scales by width, never overflows).
- `<img>` alt text for rendered images; placeholder has `aria-hidden`.
- `ScenarioCard` image banner: `alt` attribute describing the scenario; no overflow at any breakpoint.
- Record any deferred a11y items in `docs/checklist.md`.

Once green, commit:
> `[Scenario Scene Art] (4/5) Complete: UI — EntityModal scene-art section + SceneArtModal wiring, ScenarioCard banner, 6 new tests.`

---

### Phase 5 — Docs + Validation + Commit

**Goal:** Update all affected documentation and confirm the full test suites are green.

#### Step 5.1 — Update `docs/api-contract.md`
- Add `image`, `sceneArtPositive`, `sceneArtNegative` to the `ScenarioRead` shape table.
- Add two new authoring endpoints under the Scenario section:
  - `POST /scenarios/scene-art-prompts` — request: `ScenarioSceneArtPromptRequest`; response: `SceneArtPromptResponse`.
  - `POST /scenarios/scene-art` — request: `SceneArtGenerateRequest`; response: `SceneArtGenerateResponse`.

#### Step 5.2 — Update `docs/data-flow.md`
- Add a **Scenario Authoring Flow** subsection (or extend the existing one) describing the scene-art pipeline: `EntityModal → generateScenarioSceneArtPrompts → POST /scenarios/scene-art-prompts → scenario_agent.generate_scene_art_prompts → LLM → SceneArtPromptResponse`; and `generateScenarioSceneArt → POST /scenarios/scene-art → scene_art.generate_scene_art → ComfyUI → WebP → /media/scenes/…`.

#### Step 5.3 — Update `docs/documentation.md`
- In the Current Status paragraph, add a sentence noting that Scenarios now carry an optional scene-art image (positive/negative prompts + rendered WebP) alongside the existing Setting establishing image.

#### Step 5.4 — Update `docs/checklist.md`
- Add a new completed-phase entry under **Follow-up Work** (matching the format of the Setting Creator entry).
- Record the deferred in-browser a11y/responsive pass (same standing constraint — shared dev server).

#### Step 5.5 — Run full validation
- **Backend:** `uv run pytest` (all tests, including the 5 new scenario-scene-art tests). Run `uv run ruff check .` + `uv run mypy web/backend`.
- **Frontend:** `npm test` (all Vitest tests, including 6 new UI tests + 4 new hook/api tests). Run `npm run typecheck` + `npm run lint` + `npm run build`.

**Action:** Once all suites are green, commit:
> `[Scenario Scene Art] (5/5) Complete: Docs + validation gate; ready to merge.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| `Scenario` model columns | `image`, `scene_art_positive`, `scene_art_negative` (nullable String) | `web/backend/app/models/scenario.py` |
| Schema extensions | `ScenarioBase/Update/Read` gain three new fields; `ScenarioSceneArtPromptRequest` added | `web/backend/app/schemas/scenario.py` |
| `media_cleanup` update | `Scenario.image` tracked alongside `Setting.image` | `web/backend/app/services/media_cleanup.py` |
| Agent function | `generate_scene_art_prompts` in the scenario agent | `web/backend/app/agents/scenario_agent.py` |
| Backend routes | `POST /scenarios/scene-art-prompts` + `POST /scenarios/scene-art` | `web/backend/app/routes/scenarios.py` |
| `Scenario` TS type | `image`, `sceneArtPositive`, `sceneArtNegative` optional fields | `web/frontend/lib/types.ts` |
| API client functions | `generateScenarioSceneArtPrompts`, `generateScenarioSceneArt` | `web/frontend/lib/api.ts` |
| `useLibraryState` handlers | `generateScenarioSceneArtPrompts`, `generateScenarioSceneArt`, updated submit + prefill | `web/frontend/features/library/useLibraryState.ts` |
| `EntityModal` scene-art UI | Agentic aside section: scene-art preview + "Edit image" + `SceneArtModal` | `web/frontend/components/feature/EntityModal.tsx` |
| `ScenarioCard` banner | Optional 16:9 art banner when `image` is set | `web/frontend/components/feature/ScenarioCard.tsx` |
| Backend tests | Data-layer roundtrip + media-cleanup + agent + route tests | `utils/tests/backend/api/test_scenarios.py`, `utils/tests/backend/api/test_scenario_agent.py` |
| Frontend tests | Hook/api tests + UI tests for EntityModal + ScenarioCard | `web/frontend/features/library/useLibraryState.test.ts`, `web/frontend/components/feature/EntityModal.test.tsx`, `web/frontend/components/feature/ScenarioCard.test.tsx` (or equivalent) |
| Docs | api-contract, data-flow, documentation status, checklist | `docs/api-contract.md`, `docs/data-flow.md`, `docs/documentation.md`, `docs/checklist.md` |
