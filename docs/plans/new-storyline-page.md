# Plan — New Storyline Page (agentic, triage-driven world build)

## 1. Introduction

Today a storyline is created in a pop-up (`StorylineModal`): standard fields on the
left, a detached **context-files** column (drop `.txt`/`.md`) on the right with
per-file **Draft / RAG / KG** toggles, an agentic *Draft with Mytheca* seed, and a
*Generate primer* action. Files ground a single generation and are then thrown
away (no persistence; RAG/KG are dead seams). Creation only ever produces the
storyline shell — characters, settings, stats, and images are authored later, one
modal at a time.

This plan replaces that pop-up with a **dedicated full-page surface** for both
creating and editing a storyline, and turns the context-files area into a real
**Triage → Build** pipeline. Triage runs an agent over the dropped documents and
sorts them into **Characters / Settings / Other** (a doc holding *multiple*
characters or settings lands in *Other*), each tagged for inclusion in **Draft**
(world-setting documents) and/or **RAG** (most everything else) — the **KG**
category is removed. Triaged documents are **persisted to Postgres** as a real
context-document corpus (a durable RAG seam; chunking/embeddings/retrieval stay
deferred). A prominent **Build the whole world** action drafts *everything* —
title, genre, tagline, premise, World Primer, statistics, a cast of full
characters, and settings — grounded entirely in the provided context (so the
author no longer has to *describe* the world by hand when context exists). The
author **reviews** the proposed world, then **commits**, which persists every
entity and (only when ComfyUI is configured) renders character portraits and
setting scene-art. A live **context-budget** meter estimates the tokens the World
Primer + draft-included documents will spend per scene, keeping the always-injected
context bounded. When no storylines exist, this page becomes the app's default.

Architecture fit: a new `context_documents` table + CRUD/routes (FastAPI), two new
creation-time agents (`triage_agent`, `build_agent`) reusing the existing
`agents/_common` LLM plumbing and the configured `/options` model, a frontend data
path in `lib/api.ts` + a `useStorylineCreator` hook, the new route(s) under
`app/storylines/`, and a client-orchestrated **commit** that reuses the already-tested
CRUD + per-entity image endpoints.

## 2. Gaps & Unanswered Questions

Resolved with the user before planning:

- **RAG storage → Persist to Postgres (durable seam).** Triaged docs get a real
  table + CRUD; retrieval (chunking/embeddings/hybrid search) remains deferred.
- **Build scope → End-to-end, review then commit.** The orchestrator drafts the
  full world as *text* (incl. portrait/scene-art *prompts*); the author reviews;
  commit persists everything and renders images **only if ComfyUI is configured**
  (opt-in toggle, best-effort per entity).
- **Edit flow → Move both create and edit to the page.** `StorylineModal` is
  retired; `StorylineMenu`/`LibraryView` navigate to the page instead.

Assumptions (simple gaps, proceeding):

- **Routes:** create = `/storylines/new`, edit = `/storylines/[id]/edit`. The
  literal `storylines/` segment resolves before the dynamic root `[storylineId]`
  (Next.js static-first; confirmed by the existing clean build), so there is no
  collision with `/{storylineId}`.
- **Images at commit, not preview.** Drafting yields image *prompts* (cheap LLM
  text); GPU rendering happens after approval, per entity, best-effort — mirroring
  the existing character/setting flow where prompts and render are distinct steps.
- **Token estimate** uses the standard `ceil(chars/4)` heuristic (no tokenizer
  dependency); the budget meter is advisory with a soft cap mirroring
  `DOCS_CHAR_CAP`.
- **Commit is client-orchestrated** over existing endpoints (createStoryline →
  stats → characters [+portrait] → settings [+scene-art] → bulk context-docs),
  giving per-entity progress and best-effort image failures without a new
  transactional backend endpoint.
- **No auth/owner** column yet (consistent with the rest of the app).
- **Cast/setting count:** the orchestrator proposes a sensible number from the
  context (cap ~6 characters / ~5 settings) to bound cost; the author can prune in
  review.

## 3. Hierarchical Step-by-Step Instructions

Work happens on a feature branch `feat/new-storyline-page` (off `main`, in the
shared working dir to avoid a second dev-server clashing on `.next`). Commit per
phase; merge to `main` locally at the end (no push).

---

### Phase 1 — Context-document corpus (data layer)

- **Locations:**
  - `web/backend/app/models/context_document.py` — new `ContextDocument` model:
    `id` (prefixed `cd_` via `new_id`), `storyline_id` FK, `name`, `content` (Text),
    `category` (`character|setting|other`), `include_draft` (bool), `include_rag`
    (bool), `source` (default `"upload"`), `char_count` (int), `position` (int),
    `created_at`. Add the `context_documents` relationship to
    `models/storyline.py` (`cascade="all, delete-orphan"`); register in
    `models/__init__.py`.
  - `web/backend/app/schemas/context_document.py` — `ContextDocumentBase/Create/Update/Read`
    (camelCase: `storylineId`, `includeDraft`, `includeRag`, `charCount`) + a
    `ContextDocumentBulkCreate` (`docs: list[Create]`) for one-shot persistence on
    commit. `category` validated to the three-value set.
  - `web/backend/app/services/crud.py` — `list_context_documents`,
    `create_context_document`, `bulk_create_context_documents`,
    `update_context_document`, `delete_context_document` (id-gen via existing
    `new_id`, not the hex helper).
  - `web/backend/app/routes/context_documents.py` — `GET/POST
    /storylines/{id}/context-docs`, `POST /storylines/{id}/context-docs/bulk`,
    `PATCH /context-docs/{docId}`, `DELETE /context-docs/{docId}`; register the
    router in `app/main.py`.
  - `utils/tests/backend/data/test_models.py` (+/or new `test_context_documents.py`)
    and `utils/tests/backend/api/test_context_documents.py` — model roundtrip,
    cascade delete with the storyline, category validation, bulk create, list
    ordering by `position`.
- **Rationale:** Persistence must exist before Triage can store anything or the
  build can attach a corpus. A brand-new table is created by `create_all` (no
  ALTER/reconcile needed), so it self-provisions on the dev DB.
- **Docs:** `docs/structure.md` (new model under `models/`), `docs/api-contract.md`
  (new **Context documents** group + shape), `docs/data-flow.md` (the corpus as a
  durable seam; retrieval still deferred).
- **Action:** Run `uv run pytest utils/tests/backend` (ruff + mypy clean). Once
  green, commit: `[New Storyline Page] (1/7) Complete: context_documents table + CRUD/routes (durable RAG-corpus seam).`

---

### Phase 2 — Triage agent + endpoint

- **Locations:**
  - `web/backend/app/agents/triage_agent.py` — `triage_documents(db, docs,
    storyline_id=None)` where `docs: list[{name, text}]`. One LLM call (configured
    model via `_common.resolve_llm`/`gen_params`) classifies each doc → `{name,
    category: character|setting|other, includeDraft, includeRag, rationale}`.
    System prompt encodes the rules: a doc describing **one** character → `character`;
    **one** setting → `setting`; **multiple/mixed** characters or settings, or a
    general world doc → `other`; **Draft** ⇐ world-setting/lore documents;
    **RAG** ⇐ most documents (default on). Tolerant JSON parse via
    `_common.extract_json`; per-doc fallback (`other` / RAG-on) when the model omits
    one. Bound total input with `_common.DOCS_CAP`.
  - `web/backend/app/schemas/context_document.py` (extend) — `TriageRequest`
    (`docs: list[{name,text}]`, `storylineId?`), `TriageItem`, `TriageResponse`.
  - `web/backend/app/routes/storylines.py` — `POST /storylines/triage` (fixed
    sub-path, like `/draft`).
  - `utils/tests/backend/agents/test_triage_agent.py` — offline `httpx.MockTransport`:
    single-character doc → `character`; multi-character doc → `other`; world-lore doc
    → Draft+RAG; malformed reply → graceful fallback.
- **Rationale:** Triage is the heart of the request and must produce the
  category/inclusion data the corpus and build consume. It reuses the settled
  agent plumbing, so only the prompt + parse are new.
- **Docs:** `docs/api-contract.md` (Triage shape under Authoring),
  `docs/data-flow.md` (Triage flow: dropped text → classification → persisted docs).
- **Action:** Run `uv run pytest utils/tests/backend/agents utils/tests/backend/api`
  (ruff + mypy clean). Once green, commit: `[New Storyline Page] (2/7) Complete: triage_agent + POST /storylines/triage (Characters/Settings/Other · Draft/RAG).`

---

### Phase 3 — World-build orchestrator agent + endpoint

- **Locations:**
  - `web/backend/app/agents/build_agent.py` — `build_world(db, seed, docs_overview,
    storyline_id=None)` returning a **ProposedWorld** (text only). Orchestrates,
    over the configured model: (1) storyline metadata (reuse
    `storyline_agent.draft_storyline`), (2) World Primer
    (`generate_world_primer`), (3) a **statistics** proposal (a small new prompt:
    propose 3–6 universal `StatDefinition`s with bands, suited to the genre),
    (4) a **cast** of N characters and (5) M settings — each a full draft plus its
    portrait/scene-art **prompts** (reuse `character_agent`/`setting_agent` draft +
    prompt helpers). Requires **seed OR docs_overview** (empty-both → 400) so the
    author can build from files alone. Applies the **context budget cap**
    (truncate `docs_overview` to the shared cap) and bounds counts (≤6 chars / ≤5
    settings). Starting stats per character are proposed against the *proposed* stat
    schema in-process (no DB rows yet).
  - `web/backend/app/schemas/storyline.py` (or a new `schemas/build.py`) —
    `BuildWorldRequest` (`seed?`, `docsOverview?`, `storylineId?`, `maxCharacters?`,
    `maxSettings?`) and `ProposedWorld`/`ProposedCharacter`/`ProposedSetting`
    (camelCase; characters carry `portraitPositive/Negative` + `startingStats`;
    settings carry `sceneArtPositive/Negative`).
  - `web/backend/app/routes/storylines.py` — `POST /storylines/build`.
  - `utils/tests/backend/agents/test_build_agent.py` — offline mocked transport
    returning canned drafts; assert the assembled `ProposedWorld` shape, the
    seed-or-docs guard, the count caps, and the budget truncation.
- **Rationale:** Centralizing the multi-step generation server-side keeps the
  client to a single call and lets the orchestrator decide cast/setting counts and
  enforce the budget. Returning a *proposal* (not persisting) is what enables the
  review-then-commit UX.
- **Docs:** `docs/api-contract.md` (Build shape), `docs/data-flow.md` (Build
  Everything flow: context → proposed world → review → commit).
- **Action:** Run `uv run pytest utils/tests/backend` (ruff + mypy clean). Once
  green, commit: `[New Storyline Page] (3/7) Complete: build_agent + POST /storylines/build (drafts the whole world for review).`

---

### Phase 4 — Frontend data path (api client, types, budget helper, hook)

- **Locations:**
  - `web/frontend/lib/readDocs.ts` — **remove `useKg`** from `ReadDoc`/`DocUse`
    (keep `useDraft`/`useRag`); keep `docsForDraft`/`concatDocs`.
  - `web/frontend/lib/contextBudget.ts` (new) — `estimateTokens(text)` (`ceil/4`),
    `budgetFor({ worldPrimer, premise, draftDocs })`, a soft-cap constant, and a
    `BudgetLevel` (`ok|warn|over`). Unit tests `lib/contextBudget.test.ts`.
  - `web/frontend/lib/types.ts` — `ContextDocument`, `TriageItem`,
    `ProposedWorld`/`ProposedCharacter`/`ProposedSetting`.
  - `web/frontend/lib/api.ts` — `listContextDocs`, `bulkCreateContextDocs`,
    `deleteContextDoc` (+ update); `triageDocuments(docs, storylineId?)`;
    `buildWorld(body)`. Extend `lib/api-mock` + `lib/api.test.ts`.
  - `web/frontend/features/library/storylineCreator.ts` (new) — creator Draft type,
    blank/edit defaults, validation, and the **commit plan** builder (the ordered
    list of CRUD/image steps from a `ProposedWorld`).
  - `web/frontend/features/library/useStorylineCreator.ts` (new) — page state hook:
    fields, `docFiles`, triage state (`triaging`, results), `proposedWorld`
    (build/preview), commit progress, image toggle, budget; loads existing
    storyline + stats + context-docs in edit mode. renderHook tests
    `useStorylineCreator.test.ts` (mock `lib/api`): triage populates categories;
    build populates the proposal; commit walks the plan.
  - **`ContextFilesPanel`** (`components/feature/ContextFilesPanel.tsx`) — drop the
    **KG** toggle (Draft/RAG only) so `CharacterModal`/`SettingModal` stay valid.
- **Rationale:** A tested, non-visual data path de-risks the page. Removing KG here
  keeps the two surviving modals (character/setting) consistent with the new model.
- **Docs:** none beyond code (UI docs land with Phase 5/7).
- **Action:** Run `npm test` + `npm run typecheck` + `npm run lint` (frontend) for
  the affected files. Once green, commit: `[New Storyline Page] (4/7) Complete: api client + types + context-budget + useStorylineCreator (KG toggle removed).`

---

### Phase 5 — The creator page UI + routing + empty-state default

- **Locations:**
  - `web/frontend/features/library/StorylineCreatorView.tsx` (new) — the full-page
    surface used by both routes. **Left:** the standard fields (Title + Genre,
    Tagline, Premise, World Primer + *Generate primer*, **Statistics** via the
    existing `StatsEditor`) and the **Seal** row → `SealModal`. **Right:** a
    **context column** — drop zone, the **Triage** button under the file list,
    triaged results **grouped Characters / Settings / Other** each with **Draft /
    RAG** toggles, and a live **context-budget meter** (`lib/contextBudget`).
    **Top/agentic:** a visually prominent **Build the whole world** panel
    (seed field marked *optional when context is provided* + a *Generate images
    (ComfyUI)* toggle, enabled only when configured) making it obvious the world can
    be built agentically from the start but **requires context** (files or text).
    A **review** panel renders the `ProposedWorld` (editable/prunable) with a
    **Create world** commit button + per-entity progress.
  - `web/frontend/app/storylines/new/page.tsx` (create) and
    `web/frontend/app/storylines/[id]/edit/page.tsx` (edit) — thin server wrappers
    rendering `StorylineCreatorView` with `metadata.title`.
  - `web/frontend/components/feature/StorylineMenu.tsx` — *New Storyline* and the
    per-row *Edit* now **navigate** (`/storylines/new`, `/storylines/{id}/edit`)
    instead of opening the modal.
  - `web/frontend/features/library/LibraryView.tsx` + `useLibraryState.ts` — remove
    the `<StorylineModal>` mount and the modal's open/edit handlers; on load with
    **zero** storylines, `router.replace("/storylines/new")` (empty-state default).
  - **Delete** `web/frontend/components/feature/StorylineModal.tsx` and its test;
    update `LibraryView.editors.test.tsx`/`StorylineMenu.test.tsx` to the navigation
    behavior. New `StorylineCreatorView.test.tsx` (render, field edit, triage
    grouping, build→review, budget meter).
  - Smaller pieces split out to stay under file-length limits:
    `components/feature/TriagePanel.tsx`, `components/feature/ContextBudgetMeter.tsx`,
    `components/feature/ProposedWorldReview.tsx`.
- **Rationale:** This is the user-visible heart of the request and the empty-state
  entry point. Building it after the data path means every control is wired to a
  tested API/hook.
- **Docs:** `docs/routes.md` (new `/storylines/new` + `/storylines/[id]/edit`),
  `docs/component-map.md` (new components; `StorylineModal` removed).
- **Action:** Run `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`.
  Perform an **accessibility + responsive pass** (keyboard, visible focus, contrast,
  320/375/768/1024; `role`/labels on Triage groups, toggles, budget meter, review).
  If the shared dev server blocks a live preview, verify structurally + via build and
  record the deferral in `docs/checklist.md`. Once green, commit:
  `[New Storyline Page] (5/7) Complete: dedicated create/edit page + triage UI + budget meter; StorylineModal retired; empty-state default.`

---

### Phase 6 — Commit: persist world + images + budget enforcement

- **Locations:**
  - `web/frontend/features/library/useStorylineCreator.ts` + `storylineCreator.ts`
    — implement the **commit sequence** over existing endpoints:
    `createStoryline` (core + seal) → for each proposed stat `createStatDefinition`
    → for each character `createCharacter` then, when images on + ComfyUI
    configured, `generatePortrait` (from the proposed prompts) + `updateCharacter`
    portrait, then `setCharacterStats` → for each setting `createSetting` then
    optional `generateSceneArt` + `updateSetting` image → `bulkCreateContextDocs`
    (the triaged corpus) → navigate to `/{newId}`. Per-entity **best-effort** image
    failures don't abort the build; progress + a per-entity error list surface in
    the review panel. Edit mode diffs/persists fields + stats + the corpus.
  - Enforce the **budget cap** on what's sent to `buildWorld`/drafting
    (truncate draft docs to the shared cap; surface `over` state in the meter).
  - Detect ComfyUI via `getSettings()` `comfy.baseUrl`; disable the images toggle +
    explain when unset.
  - Tests: extend `useStorylineCreator.test.ts` — commit walks the full plan
    (mock api), images skipped when unconfigured, image failure is non-fatal,
    context-docs persisted with categories/flags.
- **Rationale:** Commit is deliberately client-orchestrated to reuse the already-tested
  CRUD + image endpoints and to give honest per-entity progress; isolating it in its
  own phase keeps the big UI phase reviewable.
- **Docs:** `docs/data-flow.md` (commit sequence + image gating).
- **Action:** Run `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`;
  backend `uv run pytest` if any endpoint touched. Live-verify the create flow if a
  dev server is free (build a small world end-to-end; confirm persistence on reload),
  else document the deferral. Once green, commit:
  `[New Storyline Page] (6/7) Complete: review→commit persists world + stats + corpus + opt-in images.`

---

### Phase 7 — Docs sweep, full validation, merge

- **Locations:** `docs/documentation.md` (status paragraph),
  `docs/checklist.md` (new "New Storyline Page" entry: scope, decisions, deferrals),
  re-check `docs/routes.md`/`docs/component-map.md`/`docs/api-contract.md`/
  `docs/data-flow.md`/`docs/structure.md` for drift. Verify no orphan references to
  `StorylineModal`.
- **Rationale:** `docs/` is the source of truth; the change must be reflected before
  it's "done".
- **Action:** Run the **full** suites — `uv run pytest` (ruff + mypy) and
  `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`. Once all
  green, commit: `[New Storyline Page] (7/7) Complete: docs sweep + full validation.`
  Then `git checkout main && git merge --no-ff feat/new-storyline-page`, resolving any
  drift, and a final merge commit. **No push.**

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Context-document model | Persisted triaged corpus (category + Draft/RAG flags) | `web/backend/app/models/context_document.py` |
| Context-document schemas | Create/Update/Read/Bulk + Triage shapes | `web/backend/app/schemas/context_document.py` |
| Context-document CRUD + routes | List/create/bulk/update/delete | `web/backend/app/services/crud.py`, `web/backend/app/routes/context_documents.py` |
| Triage agent + endpoint | Classify docs → Characters/Settings/Other · Draft/RAG | `web/backend/app/agents/triage_agent.py`, `web/backend/app/routes/storylines.py` |
| Build orchestrator + endpoint | Draft the whole world (text + image prompts) for review | `web/backend/app/agents/build_agent.py`, `web/backend/app/schemas/...`, `web/backend/app/routes/storylines.py` |
| API client + types | context-docs CRUD, triage, build; KG removed | `web/frontend/lib/api.ts`, `web/frontend/lib/types.ts`, `web/frontend/lib/readDocs.ts` |
| Context-budget helper | Token estimate + soft cap + level | `web/frontend/lib/contextBudget.ts` |
| Creator state hook | Fields, triage, build, commit, budget | `web/frontend/features/library/useStorylineCreator.ts`, `storylineCreator.ts` |
| Creator page + routes | Full-page create/edit; empty-state default | `web/frontend/features/library/StorylineCreatorView.tsx`, `web/frontend/app/storylines/new/page.tsx`, `web/frontend/app/storylines/[id]/edit/page.tsx` |
| Triage / budget / review UI | Grouped triage, budget meter, proposed-world review | `web/frontend/components/feature/{TriagePanel,ContextBudgetMeter,ProposedWorldReview}.tsx` |
| StorylineModal retired | Menu/Library navigate to the page | `web/frontend/components/feature/StorylineMenu.tsx`, `web/frontend/features/library/LibraryView.tsx`, `useLibraryState.ts` |
| Backend tests | Model/CRUD, triage, build agents | `utils/tests/backend/{data,api,agents}/...` |
| Frontend tests | budget, api, hook, page | `web/frontend/lib/*.test.ts`, `web/frontend/features/library/useStorylineCreator.test.ts`, `StorylineCreatorView.test.tsx` |
| Docs | Routes, components, contract, data-flow, structure, status, checklist | `docs/*.md` |
