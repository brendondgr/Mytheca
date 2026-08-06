# Plan — World Build: Multi-Entity Extraction (stop losing characters/settings)

## 1. Introduction

When an author uses **Build the whole world** on the New Storyline page, the build
turns *exactly one* character card per document triaged as `character`, and one
setting card per `setting` doc (`build_agent.iter_build_world`, fed by the
frontend's `characterDocs`/`settingDocs` in `useStorylineCreator.build`). But the
triage agent deliberately routes any document that describes **multiple**
characters or settings into the `other` bucket, and `other` docs are *never* made
into cards — they only ground drafting / feed RAG. The result the user reported:
drop a markdown file describing several characters and **all of them vanish** —
they never appear as structured character/setting cards.

This plan makes the build **extract every distinct entity from every included
document** before drafting. A new lightweight **extraction agent** scans each doc
(character / setting / other bucket alike) and returns the list of distinct
characters and settings it contains; the build then drafts **one full card per
extracted entity** (deduped by name, bounded by the existing `MAX_CHARACTERS` /
`MAX_SETTINGS` caps). A single-subject doc still yields one card (extraction
returns one); a multi-subject or mixed doc now yields one card per subject; a pure
lore/history doc yields none (and still grounds the world as before). The change
spans the FastAPI brain (`web/backend/app/agents`, `schemas/build.py`,
`routes/storylines.py`) and the Next.js creator (`features/library`, `lib/api.ts`,
`lib/types.ts`), with automated tests on both sides plus a real-LLM live walkthrough.

## 2. Gaps & Unanswered Questions

- **How to handle multi-subject docs (resolved with the user):** *Extract every
  entity from all included docs* — every kept doc (character / setting / other) is
  scanned for both characters and settings; each distinct subject becomes its own
  card. Pure lore docs that name no profile-worthy subject produce no cards.
- **Verification (resolved with the user):** automated tests **and** a live
  walkthrough driving the real configured LLM (llama.cpp, detected & reachable) with
  a genuine multi-character markdown.
- **Seed-only / blueprint-invented cast (assumption):** unchanged — when no docs are
  attached the build still invents *no* cast/settings (the blueprint's concept lists
  stay ignored). Only attached docs produce entities. Not in scope to change.
- **Dedup key (assumption):** case/whitespace-folded entity **name**; first
  occurrence wins. Cross-doc duplicates collapse to one card.
- **Per-doc cost (assumption):** one extraction LLM call per doc + one draft call per
  extracted entity, all at the existing `DEFAULT_AUTHORING_EFFORT` (Medium). Totals
  still clamped by `MAX_CHARACTERS=6` / `MAX_SETTINGS=5` so a build stays affordable.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend: entity-extraction agent

- **Locations:** new `web/backend/app/agents/extract_agent.py`; new schema rows in
  `web/backend/app/schemas/build.py` (`ExtractedEntity {name, source}`,
  `ExtractedEntities {characters, settings}`); new test
  `utils/tests/backend/agents/test_extract_agent.py`.
- **Work:** `extract_entities(db, doc_text, grounding, *, doc_name) -> ExtractedEntities`.
  System prompt (distinctive marker, e.g. *"entity-extraction assistant"*, so the
  build test's mock transport can route it) instructs the model to list **each
  distinct character and each distinct place** present in the document, returning
  `{"characters": [{"name", "source"}], "settings": [{"name", "source"}]}` where
  `source` is a focused brief for that one subject (what a downstream draft agent
  needs). Empty lists for pure lore. Reuse `_common.resolve_llm`/`gen_params`/
  `extract_json`/`docs_block`/`DEFAULT_AUTHORING_EFFORT`. Coerce/trim defensively
  (drop nameless rows, cap each `source` to `DOCS_CAP`).
- **Rationale:** the splitting capability is the heart of the fix; isolating it in
  its own agent keeps `build_agent` orchestration thin and unit-testable offline.
- **Action:** Run `uv run pytest utils/tests/backend/agents/test_extract_agent.py`
  (+ `ruff`/`mypy` on the new files). Once green, commit:
  `Multi-Entity Extraction (1/4) Complete: entity-extraction agent splits a doc into per-character/per-setting sources.`

### Phase 2 — Backend: wire extraction into the build

- **Locations:** `web/backend/app/agents/build_agent.py` (`iter_build_world`,
  `_doc_sources`, `validate_build_inputs`/`has_buildable_docs`); `schemas/build.py`
  (`BuildDoc` gains optional `category`; `BuildWorldRequest` gains `other_docs`);
  `routes/storylines.py` (pass `other_docs` through `/build` + `/build/stream`);
  `utils/tests/backend/agents/test_build_agent.py`.
- **Work:** replace the one-entity-per-doc loop with: gather all included docs
  (`character_docs + setting_docs + other_docs`); for each, call
  `extract_agent.extract_entities`; accumulate characters & settings, **dedup by
  folded name**, clamp to `MAX_CHARACTERS`/`MAX_SETTINGS`. Emit `BuildPlanEvent`
  with the extracted names as skeleton labels (after a new `stage="extract"` status
  "Reading your documents…"), then draft one card per extracted character/setting
  exactly as today (`BuildCharacterEvent`/`BuildSettingEvent` with `index/total`).
  `has_buildable_docs` now also counts `other_docs`. Update the module/function
  docstrings (cast/settings now come from **every** included doc, multi-subject
  aware). Mock transport in the test gains an `"entity-extraction assistant"` route
  returning a 2-character / 2-setting payload from one doc.
- **Rationale:** this is the behavior change the user asked for; keeping the event
  contract (`plan`/`character`/`setting`/`done`) identical means the frontend stream
  consumer needs no event-shape change.
- **Action:** Run `uv run pytest utils/tests/backend/agents/test_build_agent.py`
  (+ ruff/mypy). New tests: a single multi-character doc → multiple
  `BuildCharacterEvent`s; an `other` doc → both kinds; cross-doc dedup; cap honored;
  the existing single-subject docs still yield one card each. Commit:
  `Multi-Entity Extraction (2/4) Complete: build extracts every entity from every included doc into its own card.`

### Phase 3 — Frontend: send all included docs to the build

- **Locations:** `web/frontend/lib/types.ts` (`BuildDoc`/`BuildWorldRequest` add
  `category?`/`otherDocs`); `web/frontend/lib/api.ts` (`buildWorldStream` payload);
  `web/frontend/features/library/useStorylineCreator.ts` (`build`); tests
  `web/frontend/features/library/useStorylineCreator.test.ts(x)` +
  `web/frontend/test/api-mock` (whichever the suite uses).
- **Work:** in `build`, stop filtering to only `character`/`setting` buckets — send
  every doc with text and its category as `characterDocs`/`settingDocs`/`otherDocs`
  (or a single categorized list, matching the chosen backend shape). Keep the
  "nothing to build from" guard (seed OR any doc OR draft-grounding). No event-loop
  change (the `character`/`setting`/`plan` cases already render whatever count the
  backend emits). Update the inline comment that says "ONLY the docs categorized as
  such — one entity per doc".
- **Rationale:** the backend can only extract from docs it receives; today `other`
  docs never reach `/build/stream`.
- **Action:** Run the frontend suite (`npm test`), `npm run typecheck`, `npm run lint`.
  Add a hook test: with an `other`-bucket multi-character doc present, the build
  request carries it (in `otherDocs`/categorized list). Commit:
  `Multi-Entity Extraction (3/4) Complete: creator sends every kept document to the build for entity extraction.`

### Phase 4 — Docs, full validation, live walkthrough, merge

- **Locations:** `docs/api-contract.md` (BuildWorldRequest: `otherDocs` + extraction
  note), `docs/data-flow.md` (World-build flow: per-doc extraction → draft each),
  `docs/documentation.md` (status line), `docs/checklist.md` (this entry); the plan
  itself.
- **Work:** update docs to describe the new behavior. Run the **full** backend +
  frontend suites. **Live walkthrough:** drive `build_agent.iter_build_world` (or
  `POST /api/storylines/build/stream` via curl) against the real llama.cpp endpoint
  with a hand-written markdown containing **multiple** characters + settings, and
  confirm one card per subject is produced (record the result). If working in a
  worktree, merge to `main` and re-run validation, resolving any conflicts.
- **Action:** Run `uv run pytest` (full) + `npm test`/`typecheck`/`lint`
  (+ `next build` if the worktree allows). Once green and the live run is captured,
  commit: `Multi-Entity Extraction (4/4) Complete: docs + full validation + live multi-character walkthrough.`
  Then merge to `main`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Extraction agent | Splits a doc into per-character/per-setting sources | `web/backend/app/agents/extract_agent.py` |
| Extraction schemas | `ExtractedEntity` / `ExtractedEntities` | `web/backend/app/schemas/build.py` |
| Build wiring | Extract→draft-each, dedup, cap; `other_docs` accepted | `web/backend/app/agents/build_agent.py`, `web/backend/app/schemas/build.py`, `web/backend/app/routes/storylines.py` |
| Creator wiring | Sends every kept doc (incl. `other`) to the build | `web/frontend/features/library/useStorylineCreator.ts`, `web/frontend/lib/api.ts`, `web/frontend/lib/types.ts` |
| Backend tests | Extraction agent + multi-entity build behavior | `utils/tests/backend/agents/test_extract_agent.py`, `utils/tests/backend/agents/test_build_agent.py` |
| Frontend tests | Build sends `other`/multi-subject docs | `web/frontend/features/library/useStorylineCreator.test.ts(x)` |
| Docs | Contract + data-flow + status + checklist | `docs/api-contract.md`, `docs/data-flow.md`, `docs/documentation.md`, `docs/checklist.md` |
