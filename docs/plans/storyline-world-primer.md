# Mytheca — Storyline World Primer + Agentic Creation (no RAG)

## 1. Introduction

This plan implements the **agent process of building a storyline** and the
frontend to match it, drawn from `Documents/Plans/1.storyline-context-model.md`.
The single most important new artifact is the **World Primer** — an
agent-facing, several-paragraph world-context prose block, generated at creation
time from the one-sentence seed + premise (+ an optional overview of dropped
reference files), then **editable by the author** and stored on the storyline.
Alongside it we wire the existing-but-inert **"Draft with Mytheca"** creation
seam so a one-sentence seed can draft the storyline's metadata fields.

Scope is deliberately bounded: **the RAG system (Part 2 / Part 4 of the source
doc) is NOT built here** — no chunking, embeddings, BM25, RRF, retrieval, or
lore graph, and **dropped reference files are not persisted or indexed.** They
are read client-side only to *ground a single generation call* and then
discarded. Architecturally this follows Mytheca's existing layering: a new
`world_primer` column on `Storyline` (mirroring the `premise`/seal precedent), a
backend authoring agent over the already-built LLM proxy + settings store, two
thin authoring routes, and the Next.js `StorylineModal` extended to draft, edit,
and approve the primer.

## 2. Gaps & Unanswered Questions

- **Two agent operations, not one (assumption).** "Building the storyline" via
  the agent covers both (a) drafting the human-facing **metadata** (title /
  genre / tagline / premise) from a one-sentence seed — the "Draft with Mytheca"
  seam already in the UI — and (b) generating the agent-facing **World Primer**
  from seed + premise. Both ship here; they are complementary.
- **Dropped files = non-persistent grounding only (assumption).** The source doc
  lists drag-and-drop reference files feeding an "overview pass." Persisting /
  indexing them is RAG and is explicitly deferred. Here, dropped `.txt`/`.md`
  files are read in the browser, concatenated + length-capped, and passed as an
  optional `docsOverview` string to the generation call. No DB row, no chunking,
  no embeddings. Full document persistence + retrieval is a later RAG plan.
- **Live LLM dependency (assumption / known constraint).** Real generation needs
  a model configured in **Options**. When none is configured the endpoints
  return a clear `400 bad_request` ("Configure a model in Options first."). All
  backend tests use an `httpx.MockTransport` (no network), matching
  `utils/tests/backend/api/test_llm.py`. End-to-end live generation in the
  browser preview is only possible if the running environment has a reachable
  model; if not, that step is validated structurally + noted as deferred.
- **Dev-DB migration (known gotcha).** There is no Alembic yet; idempotent
  `create_all` adds missing *tables* but does not ALTER existing ones. The
  persistent Postgres dev DB needs a manual
  `ALTER TABLE storylines ADD COLUMN IF NOT EXISTS world_primer TEXT;`. Tests run
  on fresh in-memory SQLite and are unaffected.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — World Primer data layer (backend)

Add the storage for the primer, mirroring the existing `premise` column exactly.

- **Locations:**
  - `web/backend/app/models/storyline.py` — add `world_primer: Mapped[str | None]`
    (`Text`, nullable) with a short comment distinguishing it from `premise`
    (human-facing) vs. `world_primer` (agent-facing runtime context).
  - `web/backend/app/schemas/storyline.py` — add `world_primer: str | None = None`
    to `StorylineBase` (so `StorylineCreate` inherits it), `StorylineUpdate`, and
    `StorylineRead`.
  - `web/backend/app/services/crud.py` — pass `world_primer=data.world_primer` in
    `create_storyline` (`update_storyline` already applies it via `model_dump`).
  - `web/backend/app/core/seed.py` — give the Embergate seed storyline a short
    sample `world_primer` so a fresh DB demonstrates the field.
  - `utils/tests/backend/api/test_storylines.py` + `data/test_schemas.py` /
    `data/test_models.py` — extend for: default `None`, create-with-primer
    roundtrip, and `PATCH` update of `worldPrimer`.
- **Rationale:** Every later phase (generation endpoints, frontend edit/approve,
  runtime injection) needs a column to write to; doing it first keeps the rest
  additive. The `premise` and seal columns set the exact precedent.
- **Docs:** `docs/api-contract.md` (storyline read/write shape gains
  `worldPrimer`), `docs/structure.md` (storyline model field note),
  `docs/data-flow.md` if the storyline shape is enumerated there.
- **Action:** Run validation — `uv run pytest` (backend `data/` + `api/`), `ruff`
  + `mypy`. Once green, apply the dev-DB ALTER note. Commit:
  `[Storyline World Primer] (1/4) Complete: world_primer column + schema/CRUD/seed/tests.`

### Phase 2 — Storyline authoring agent + generation endpoints (backend)

The **agent process**: generate metadata + the World Primer over the configured
LLM, reusing the existing proxy + settings store.

- **Locations:**
  - `web/backend/app/services/llm.py` — add a generic
    `chat_complete(base_url, api_key, model, messages, params) -> str` that posts
    to `/chat/completions` and returns the assistant message text, reusing
    `_normalize` / `_headers` / `_send` / `_ensure_ok`. (The existing `test_chat`
    becomes a thin caller or is left as-is.)
  - `web/backend/app/agents/storyline_agent.py` (new; the `agents/` package is
    currently empty) — two functions:
    - `draft_storyline(db, seed, docs_overview=None) -> StorylineDraftResponse`:
      builds a system+user prompt instructing strict JSON output `{title, genre,
      tagline, premise}`, calls `chat_complete`, and robustly extracts/validates
      the JSON (tolerant of code fences / surrounding prose).
    - `generate_world_primer(db, premise, seed=None, docs_overview=None) -> str`:
      builds the Part-3 primer prompt (front-load always-true facts, name the
      constant proper nouns, the load-bearing rules, and a closing
      retrieval-pointer line) and returns the prose.
    - Both resolve `base_url`/`api_key` via `settings_store.resolve_llm_credentials`
      and the stored `model`; if `model` or `base_url` is missing, raise
      `APIError(400, "bad_request", "Configure a model in Options first.")`.
  - `web/backend/app/schemas/storyline.py` (or a new `schemas/authoring.py`) —
    `StorylineDraftRequest{seed, docsOverview?}`,
    `StorylineDraftResponse{title, genre, tagline, premise}`,
    `WorldPrimerRequest{premise, seed?, docsOverview?}`,
    `WorldPrimerResponse{worldPrimer}` (camelCase via `CamelModel`).
  - `web/backend/app/routes/storylines.py` — `POST /storylines/draft` →
    `draft_storyline`; `POST /storylines/primer` → `generate_world_primer`. These
    fixed sub-paths do not collide with `GET/PATCH/DELETE /storylines/{id}`.
  - `utils/tests/backend/agents/test_storyline_agent.py` (+ optional
    `api/test_authoring.py`) — `MockTransport` returns canned JSON / prose;
    assert: draft parsing (incl. fenced JSON), primer text returned, malformed
    model output → clean error, and unconfigured-LLM → 400.
- **Rationale:** Centralizing generation in `agents/` over the existing proxy
  keeps it provider-agnostic and testable without network, and gives the
  frontend two clean endpoints to call.
- **Docs:** `docs/api-contract.md` (new **Authoring** endpoints + shapes),
  `docs/data-flow.md` (creation-time generation flow), `docs/architecture.md` if
  the agent layer is enumerated.
- **Action:** Run validation — `uv run pytest` (backend `agents/` + `api/`),
  `ruff` + `mypy`. Once green, commit:
  `[Storyline World Primer] (2/4) Complete: authoring agent + draft/primer endpoints + mock-backed tests.`

### Phase 3 — Frontend: World Primer field + agentic Draft-with-Mytheca wiring

Make the `StorylineModal` draft, edit, and approve — turning the inert seams live.

- **Locations:**
  - `web/frontend/lib/types.ts` — add `worldPrimer?: string` to `Storyline`.
  - `web/frontend/lib/api.ts` — add `draftStoryline(seed, docsOverview?)` →
    `POST /storylines/draft` and `generateWorldPrimer({premise, seed?,
    docsOverview?})` → `POST /storylines/primer`, with response interfaces
    (`StorylineDraftResult`, `WorldPrimerResult`). `StorylineInput` already
    carries `worldPrimer` via the `Partial<…Storyline>` type.
  - `web/frontend/features/library/editor.ts` — add `worldPrimer` to `Draft` and
    to `STORYLINE_DRAFT`.
  - `web/frontend/features/library/useLibraryState.ts` —
    `editStoryline` prefills `worldPrimer`; `submitStoryline` sends it;
    add `draftStoryline()` (reads the seed from `draft._prompt`, calls the API,
    fills title/genre/tagline/premise, toggles `generating`, surfaces errors) and
    `generatePrimer()` (uses current premise + seed, fills `draft.worldPrimer`).
    Expose both + a `generatingPrimer` flag from the hook.
  - `web/frontend/components/feature/StorylineModal.tsx` —
    (a) bind the "Draft with Mytheca" seed `TextArea` to `draft._prompt`, enable
    the button → `lib.draftStoryline()` with a spinner/disabled state, drop the
    "Coming soon"; (b) add an editable **World Primer** `TextArea` to the form
    column with a **"Generate primer"** action (uses seed + premise) and a
    helper line explaining it is the agent-facing runtime context; show
    generating + error states.
  - `web/frontend/components/feature/StorylineModal.test.tsx` (new) +
    `features/library/LibraryView.editors.test.tsx` — mock `@/lib/api`; assert
    draft fills fields, primer generation fills the primer field, the primer
    persists through create/edit submit, and error states render.
- **Rationale:** The data column (Phase 1) and the agent (Phase 2) are inert
  without an authoring surface; this is the "update the frontend to match it"
  half of the request.
- **Action:** Run validation — `npm test` (Vitest), `npm run typecheck`, `npm run
  lint`, `npm run build`; **a11y + responsive pass** at 320/375/768/1024
  (keyboard reachability of the new controls, visible focus, the modal stays
  scrollable and non-overflowing, live status for "Generating…"). Once green,
  commit: `[Storyline World Primer] (3/4) Complete: primer field + live Draft-with-Mytheca wiring + tests + a11y pass.`

### Phase 4 — Context-file grounding (non-persistent) + finalize

Honor the source doc's "overview pass over dropped docs" **without** RAG, then
square the docs and merge.

- **Locations:**
  - `web/frontend/components/feature/StorylineModal.tsx` (+ a small
    `web/frontend/lib/readDocs.ts` helper) — make the context-files drop zone
    accept `.txt`/`.md` via drag-drop and a file input, read each with
    `File.text()`, concatenate + length-cap (e.g. ~8k chars) into a
    `docsOverview` string held in local modal/draft state, and show dropped-file
    chips with a remove control. Pass `docsOverview` into `draftStoryline` /
    `generatePrimer`. Make explicit in copy that files only **ground this
    generation** and are not stored yet.
  - `web/frontend/lib/readDocs.test.ts` — unit-test the read/concatenate/cap
    helper; extend the modal test to assert a dropped file's text reaches the API
    call.
  - `docs/checklist.md` — record this work + the explicit deferrals (document
    **persistence, chunking, embeddings, BM25/RRF retrieval, automatic/agentic
    RAG, derived lore graph**, and the standing **Alembic** follow-up).
  - `docs/documentation.md` (status: World Primer now generated/edited at
    creation), `docs/component-map.md` / `docs/routes.md` if affected,
    `docs/data-flow.md` (note files are read-and-discarded for grounding).
- **Rationale:** Completes the creation flow's authoring inputs while keeping a
  clean seam for the future RAG corpus; finishing the docs satisfies the
  Validation Gate's "definition of done."
- **Action:** Run validation — `npm test` + `npm run typecheck` + `npm run lint`
  + `npm run build`, and `uv run pytest` to confirm nothing regressed; a11y +
  responsive re-check of the drop zone. Once green, commit:
  `[Storyline World Primer] (4/4) Complete: non-persistent context-file grounding + docs/checklist finalized.`
  Then **merge the feature branch into `main`** (`--no-ff`, matching the repo's
  merge-commit history) and **do not push**.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| `world_primer` column | Agent-facing runtime context stored on the storyline | `web/backend/app/models/storyline.py` |
| Storyline schemas | `worldPrimer` on Base/Update/Read + authoring request/response | `web/backend/app/schemas/storyline.py` |
| CRUD + seed wiring | Persist `world_primer`; sample primer on the Embergate seed | `web/backend/app/services/crud.py`, `web/backend/app/core/seed.py` |
| `chat_complete` helper | Generic OpenAI-compatible completion returning text | `web/backend/app/services/llm.py` |
| Storyline authoring agent | `draft_storyline` + `generate_world_primer` over the configured LLM | `web/backend/app/agents/storyline_agent.py` |
| Authoring routes | `POST /storylines/draft`, `POST /storylines/primer` | `web/backend/app/routes/storylines.py` |
| Backend tests | Agent + endpoint tests via `httpx.MockTransport` (no network) | `utils/tests/backend/agents/test_storyline_agent.py` |
| API client methods | `draftStoryline`, `generateWorldPrimer` + types | `web/frontend/lib/api.ts` |
| Editor/state wiring | `worldPrimer` draft field, draft + primer actions | `web/frontend/features/library/{editor.ts,useLibraryState.ts}` |
| Modal authoring UI | Live Draft-with-Mytheca, editable World Primer, file grounding | `web/frontend/components/feature/StorylineModal.tsx` |
| Doc-read helper | Client-side `.txt`/`.md` read + concatenate + cap | `web/frontend/lib/readDocs.ts` |
| Frontend tests | Modal + state + helper tests (api mocked) | `web/frontend/components/feature/StorylineModal.test.tsx`, `web/frontend/lib/readDocs.test.ts` |
| Docs | api-contract, data-flow, structure, documentation, checklist updates | `docs/` |

## 5. Explicitly Deferred (the RAG system — later plan)

Document persistence, structure-aware chunking, dense (`fastembed`/`nomic`) +
BM25 hybrid, RRF fusion, automatic & agentic retrieval at runtime, `start` vs.
`dynamic` inclusion tiers, contextual-retrieval prefixes, reranking, and the
derived lore graph / `query_kg`. The World Primer's **runtime injection into
conversations** also waits for the story-player↔backend wiring (the player is
still on in-memory seed). This plan delivers creation-time authoring only.
