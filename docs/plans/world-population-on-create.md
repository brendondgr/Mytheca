# World Population on Create — cast + settings actually land in the new world

## 1. Introduction

Creating a new storyline today persists a world container and nothing else. The
create page's assistant (`agents/storyline_edit/creation.py`) is scope-limited to six
storyline fields (title / genre / tagline / premise / World Primer / statistics), and
`commitWorld` (`web/frontend/features/library/storylineCreator.ts`) writes the storyline,
its stat definitions, and the triaged context corpus — no `Character` and no `Setting`
row is ever written. The "build the whole world" agent that used to mine the uploaded
docs for a cast was retired on 2026-07-10 when the conversational scoped agent replaced
it, and steps 3 and 4 of the intended authoring flow (character generation, setting
generation) were never re-implemented. The redirect therefore lands the author in a world
whose Characters and Settings columns are genuinely empty — the Library display path is
correct, there is simply nothing to display.

This plan restores those two steps as a first-class, streamed **population** phase.
"Create World" opens a confirmation that asks what to build (cast + settings, and
optionally artwork — artwork off by default because each render is a ComfyUI job). On
confirm, the backend proposes a roster from the persisted premise / World Primer / Draft
docs, drafts each character and setting with the existing `character_agent.draft_character`
and `setting_agent.draft_setting`, persists each one through `services.crud`, and streams
per-entity progress as NDJSON. The author then lands in a populated world. Because the
recurring failure mode here is "generated content never reaches the UI", every phase adds
a test that asserts the *whole chain* — generation → persistence → list endpoint → rendered
column — not just its own layer.

## 2. Gaps & Unanswered Questions

Resolved with the author before planning:

- **Trigger** — automatic on Create World, but gated by a confirmation that asks whether
  to build characters + settings and whether to include images.
- **Artwork** — best-effort and **off by default**; only offered when ComfyUI is
  configured, and a failed render never fails the entity.

Assumptions taken without asking:

- **Roster size** is bounded (default 5 characters, 3 settings, hard cap 8 / 6) so a run
  is finite and the local reasoning model's budget stays sane.
- **Population is create-mode only.** Edit mode keeps today's behavior; a re-run control
  for existing worlds is out of scope and goes to `docs/checklist.md`.
- **Per-entity failures are non-fatal.** One bad draft yields an `error` frame and the run
  continues; the world is never rolled back, and `commitWorld` still returns the id so the
  author is never stranded on a page whose world already exists.
- **Grounding** is the persisted storyline (`world_context`) + the Draft-selected doc text
  the client already sends as `docsOverview` + `rag_block` retrieval, exactly as the
  single-entity draft endpoints do.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Roster agent

- **Locations:** new `web/backend/app/agents/roster_agent.py`; new
  `web/backend/app/schemas/world_populate.py` (`RosterEntry`, `RosterProposal`, the
  populate request + NDJSON frame models); `utils/tests/backend/agents/test_roster_agent.py`.
- **Work:** `propose_roster(db, *, storyline_id, docs_overview, max_characters,
  max_settings, conn=None)` asks the configured LLM for a coherent cast + place list —
  each entry a `name` plus a one-line `seed` for the existing draft agents. Reuses
  `_common.world_context` / `docs_block` / `rag_block` / `extract_json` / `resolve_llm_or`.
  Caps and de-duplicates entries by name; a malformed payload raises the standard
  `APIError`.
- **Rationale:** the roster is the only genuinely new generation step; the per-entity
  drafting already exists and must not be duplicated.
- **Validation & commit:** `uv run pytest utils/tests/backend/agents`. Commit:
  `[World Population] (1/6) Complete: Roster agent proposes a bounded cast + settings list from the world's own context.`

### Phase 2 — Population service

- **Locations:** new `web/backend/app/services/world_populate.py`;
  `utils/tests/backend/services/test_world_populate.py`.
- **Work:** `populate_world(db, storyline_id, *, docs_overview, max_characters,
  max_settings, with_artwork)` is a generator yielding typed frames: `status` (stage +
  index/total + name), `character` / `setting` (the persisted entity's id + name),
  `error` (one item failed, run continues), `done` (counts). It drafts via
  `character_agent.draft_character` / `setting_agent.draft_setting`, persists via
  `crud.create_character` / `crud.create_setting`, and — only when `with_artwork` and a
  ComfyUI base URL is configured — renders portrait / scene art best-effort through the
  existing `portraits` / `scene_art` services, swallowing render failures into an `error`
  frame while keeping the entity.
- **Rationale:** keeping orchestration in a service (not the route) makes the persistence
  guarantee unit-testable without HTTP.
- **Validation & commit:** `uv run pytest utils/tests/backend/services`. Commit:
  `[World Population] (2/6) Complete: Population service drafts and persists the roster with best-effort artwork.`

### Phase 3 — Route + contract

- **Locations:** `web/backend/app/routes/storylines.py` (new
  `POST /storylines/{id}/populate/stream`, declared below the fixed sub-paths, wrapped in
  the existing `with_keepalive` NDJSON helper); `docs/api-contract.md`;
  new `utils/tests/backend/api/test_storyline_populate.py`.
- **Work:** pre-flight 404 (unknown storyline) / 400 (unconfigured LLM) before the stream
  opens; frames serialize camelCase like every other stream. The API test is the
  **regression guard**: drive the endpoint with a stubbed LLM, then assert
  `GET /storylines/{id}/characters` and `…/settings` return the generated entities *and*
  that `GET /storylines/{id}` reports matching `characterCount` / `settingCount`.
- **Rationale:** the class of bug being fixed is "generated but not visible", so the
  assertion has to run through the same read endpoints the Library uses.
- **Validation & commit:** `uv run pytest utils/tests/backend`. Commit:
  `[World Population] (3/6) Complete: Streaming populate endpoint with an end-to-end persistence guard.`

### Phase 4 — Frontend client + commit sequence

- **Locations:** `web/frontend/lib/types.ts` (frame + option types), `web/frontend/lib/api.ts`
  (`populateWorldStream`), `web/frontend/features/library/storylineCreator.ts`
  (`commitWorld` gains a `populate` option and runs the stream after the corpus is saved),
  `web/frontend/features/library/useStorylineCreator.ts` (populate options state + progress),
  `web/frontend/test/api-mock.ts`; tests in `storylineCreator.test.ts` +
  `useStorylineCreator.test.ts`.
- **Work:** after the storyline, stats and docs are persisted, `commitWorld` consumes the
  populate stream and reports `Building the cast — 2 / 5: Marin`-style progress. A populate
  failure is surfaced but still returns the storyline id.
- **Rationale:** population must run against the *persisted* world (it needs the id and the
  saved corpus), so it belongs at the end of the commit sequence.
- **Validation & commit:** `cd web/frontend && npm test -- features/library && npm run typecheck`.
  Commit: `[World Population] (4/6) Complete: Create World runs the population stream and reports live progress.`

### Phase 5 — Confirmation UI + the population-visible guard

- **Locations:** new `web/frontend/components/feature/BuildWorldModal.tsx` (+ co-located
  test), `web/frontend/features/library/StorylineCreatorView.tsx` (Create World opens the
  modal), `docs/component-map.md`; new
  `web/frontend/features/library/LibraryView.population.test.tsx`.
- **Work:** the modal asks "Build the cast and settings for this world?" with a
  characters+settings toggle (on), an artwork toggle (off, disabled with an explanation when
  ComfyUI is unconfigured), and Skip / Build actions. Keyboard-operable, labelled, focus-
  trapped via the existing `Modal` primitive. `LibraryView.population.test.tsx` renders the
  Library for a freshly-created world whose API returns generated characters + settings and
  asserts both columns show them — the UI end of the same chain.
- **Rationale:** the author asked to be asked; and the last link (columns actually render)
  needs its own permanent test.
- **Validation & commit:** `npm test`, `npm run typecheck && npm run lint`, plus a keyboard /
  focus / contrast / 320-375-768-1024 pass on the modal. Commit:
  `[World Population] (5/6) Complete: Create World asks what to build, and the Library renders the populated cast + settings.`

### Phase 6 — Docs, full gate, merge

- **Locations:** `docs/api-contract.md`, `docs/data-flow.md`, `docs/documentation.md`,
  `docs/architecture.md`, `docs/component-map.md`, `docs/checklist.md`, `CLAUDE.md`
  (agent + service tables).
- **Work:** document the populate endpoint and the create→populate→redirect path; record the
  deferred re-run-for-existing-worlds control in the checklist.
- **Validation & commit:** `uv run pytest` + `npm test` + `npm run typecheck && npm run lint`.
  Commit: `[World Population] (6/6) Complete: Documented the population phase and closed the gate.`
  Then merge into `main`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Roster agent | Proposes a bounded cast + settings roster from the world's own context | `web/backend/app/agents/roster_agent.py` |
| Populate schemas | Request + NDJSON frame models | `web/backend/app/schemas/world_populate.py` |
| Population service | Draft → persist → best-effort artwork, streamed | `web/backend/app/services/world_populate.py` |
| Populate route | `POST /storylines/{id}/populate/stream` | `web/backend/app/routes/storylines.py` |
| API client | `populateWorldStream` + mirrored types | `web/frontend/lib/api.ts`, `web/frontend/lib/types.ts` |
| Commit sequence | `commitWorld` runs population after the corpus | `web/frontend/features/library/storylineCreator.ts` |
| Confirmation modal | Asks what to build before creating | `web/frontend/components/feature/BuildWorldModal.tsx` |
| Agent tests | Roster parsing, caps, malformed payloads | `utils/tests/backend/agents/test_roster_agent.py` |
| Service tests | Persistence, non-fatal item failures, artwork gating | `utils/tests/backend/services/test_world_populate.py` |
| API regression guard | Populate → list endpoints → counts | `utils/tests/backend/api/test_storyline_populate.py` |
| Frontend tests | Commit sequence, hook state, modal, populated Library | `web/frontend/features/library/*.test.ts(x)`, `web/frontend/components/feature/BuildWorldModal.test.tsx` |
