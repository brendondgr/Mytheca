# Document Extraction — opt-in "Extract" check-off (stop auto-mining docs on build)

## 1. Introduction

Today, **Build the whole world** on the New Storyline page automatically mines
every triaged reference document for named characters/settings: a doc classified
as `character`/`setting`/uncategorized is always fed into the extraction pass. The
author never asked for this per file — it "just happens" whenever a doc is attached,
which is exactly the reported annoyance ("it tries to read the document and find
different characters and settings inside of it when we don't ask it to").

This plan makes extraction an **opt-in, per-document check-off**, mirroring the
existing **RAG** and **Draft** toggles end-to-end: a new persisted `includeExtract`
flag on `ContextDocument` (default **OFF**), surfaced as a third **Extract** toggle
chip in the Triage panel (per-row + batch-upload default), suggested conservatively
by the triage agent (only clear single-subject profiles), and **enforced server-side**
— the build's extraction stage skips any doc whose `extract` flag is off. With the
flag off by default, a fresh storyline no longer auto-mines anything; the author
explicitly checks **Extract** on the files they want turned into cast/settings.

The change spans FastAPI (model + Alembic migration + schemas + CRUD + triage agent +
build orchestrator) and the Next.js creator (types + creator state + Triage UI +
build request). The streaming build contract's event shapes are unchanged; only the
per-doc `BuildDoc.extract` input field is added.

---

## 2. Gaps & Unanswered Questions

Resolved with the user:

- **Scope = fully persisted flag** (not a frontend-only gate): persist
  `includeExtract` on `ContextDocument`, wire it through the schemas + the triage
  agent's suggestions, and gate the build **server-side**.
- **Default = OFF** everywhere (fresh drop, upload default, model/schema default,
  `BuildDoc.extract` default, and undefined-on-frontend treated as off) so a new
  storyline never auto-extracts.

Assumptions (simple gaps — proceeding):

- **Triage stays conservative.** The triage agent may *suggest* `includeExtract=true`
  **only** for a document that is a clear, single, explicitly-named character or
  setting profile the author would obviously want mined — never for lore, multi-subject,
  or uncategorized docs (recommend `false`). This keeps triage from re-introducing the
  runaway auto-extraction the plan removes, while honoring "wire it through the triage
  agent's suggestions."
- **Server-side gate via `BuildDoc.extract`.** The frontend keeps bucketing docs by
  triage category and sends each `BuildDoc` with its `extract` flag; `build_agent`
  builds the extraction work-list only from docs with `extract=true`. The existing
  bucket semantics (character/setting/uncategorized → mined by kind; other → grounding
  only) are unchanged — the flag is an additional, earlier gate.
- **Extract-off docs are not silently repurposed.** A character/setting/uncategorized
  doc with `extract=off` is simply omitted from extraction (as it is today for docs the
  author didn't attach). Its grounding contribution, if any, still flows through the
  existing `useDraft`/`docsOverview` path — unchanged.
- **Additive, self-healing migration.** `include_extract` is added `NOT NULL` with a
  `server_default` of `false`, so it backfills existing rows and is picked up by the
  bootstrap additive-column reconciler (which self-heals non-null columns that carry a
  server default), matching the established pattern.
- **Extraction is a build-only concern**, but persisting the flag lets a re-opened
  storyline remember the author's choice when **Build the whole world** is re-run in
  edit mode. The entity-scoped `ContextFilesPanel` does **not** get an Extract chip
  (extraction never applies to an already-scoped entity doc); its persisted value just
  defaults off.

---

## 3. Hierarchical Step-by-Step Instructions

> Work in a dedicated git worktree branched off `main` (per the concurrent-sessions
> rule), commit per phase, and merge to `main` in the final phase.

### Phase 1 — Persist `include_extract` end-to-end (backend model / schema / CRUD / migration)

- **Locations:**
  - `web/backend/app/models/context_document.py` — add
    `include_extract: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.false(), default=False)`
    beside `include_rag`; extend the "Inclusion tiers" comment to describe Extract
    (opt-in mining for named characters/settings during the world build; default off).
  - `web/backend/alembic/versions/20260706_120000_context_doc_include_extract.py` —
    new revision `revision = 'f6a7b8c9d0e1'`, `down_revision = 'e5f6a7b8c9d0'` (the
    current head, `prompt_overrides`). `upgrade()` adds
    `context_documents.include_extract BOOLEAN NOT NULL DEFAULT false` via
    `batch_alter_table` (mirrors `context_doc_entity_scope`); `downgrade()` drops it.
  - `web/backend/app/schemas/context_document.py` — `include_extract: bool = False`
    on `ContextDocumentBase` and `ContextDocumentRead`; `include_extract: bool | None`
    on `ContextDocumentUpdate`.
  - `web/backend/app/services/crud.py` — carry `include_extract=data.include_extract`
    in the private row builder used by `create_context_document` /
    `bulk_create_context_documents`, and apply it in `update_context_document`
    (same `setattr`/field-copy path as `include_draft`/`include_rag`).
- **Rationale:** the persisted column is the foundation every later layer reads/writes;
  landing it first (with a self-healing migration) keeps the DB and the ORM in lockstep
  before the API and UI depend on the field.
- **Action:** Run this phase's validation — `uv run pytest` for
  `utils/tests/backend/api/test_context_documents.py` (create/read defaults
  `includeExtract=false`; create with `true` round-trips; update toggles it) and any
  `utils/tests/backend/api/test_bootstrap*`/reconcile test that covers additive
  non-null-with-server-default columns; `ruff` + `mypy` on touched files. Once green,
  commit: `[Extraction Opt-In] (1/4) Complete: Persist includeExtract on ContextDocument (model + migration + schema + CRUD).`

### Phase 2 — Gate extraction on the flag; conservative triage suggestion (backend)

- **Locations:**
  - `web/backend/app/schemas/build.py` — add `extract: bool = False` to `BuildDoc`
    (+ field docstring: "opt-in — mine this doc for named characters/settings during
    the build; default off"). Update the `BuildWorldRequest` bucket docstring to note
    the per-doc Extract gate runs *before* the bucket-kind policy.
  - `web/backend/app/agents/build_agent.py` — in `iter_build_world`, build the
    `extract_jobs` work-list only from docs with `extract=True`
    (`[d for d in (character_docs or []) if d.extract]`, likewise setting/uncategorized)
    before `_doc_sources`. Extraction status/dedup/`_collect_roster` and the
    `other_docs → grounding` fold are unchanged. Update the module + `iter_build_world`
    docstrings to state cast/settings come only from docs the author **checked Extract**
    on.
  - `web/backend/app/routes/storylines.py` — verify `/build` + `/build/stream` pass the
    buckets straight through (they do — `BuildDoc.extract` rides along automatically);
    no code change expected, confirm during impl.
  - `web/backend/app/schemas/context_document.py` — add `include_extract: bool = False`
    to `TriageItem`.
  - `web/backend/app/agents/triage_agent.py` — add an `includeExtract` field to both
    `_TRIAGE_SYSTEM` / `_TRIAGE_ONE_SYSTEM` JSON shapes with a **conservative** rule
    (recommend `true` ONLY for a clear, single, explicitly-named character/setting
    profile; `false` for lore/multi-subject/uncategorized — default off); read it in
    `_coerce_item` (`bool(row.get("includeExtract", row.get("include_extract", False)))`);
    `_fallback` sets `include_extract=False`.
- **Rationale:** this is the behavioral core — extraction now runs only for checked
  docs, and triage can *offer* the toggle without ever forcing it. Doing it after the
  column exists means the gate and the suggestion both have a persisted home.
- **Action:** Run this phase's validation — `uv run pytest` for
  `utils/tests/backend/agents/test_build_agent.py` (an `extract=false` character/
  setting/uncategorized doc is **not** mined and yields no cast/setting; an
  `extract=true` doc is mined; the classified fallback-to-one still fires for an
  `extract=true` unnamed character doc; `other_docs` still ground, never extracted),
  `utils/tests/backend/agents/test_triage_agent.py` (coerces `includeExtract`, defaults
  `false`, honors an explicit `true`), and a `BuildDoc.extract` default assertion in the
  build-schema test; `ruff` + `mypy` on touched files. Once green, commit:
  `[Extraction Opt-In] (2/4) Complete: Server-side extraction gate on BuildDoc.extract + conservative triage suggestion.`

### Phase 3 — Frontend: Extract toggle chip, creator state, build request

- **Locations:**
  - `web/frontend/lib/readDocs.ts` — add `useExtract?: boolean` to `ReadDoc` (comment:
    undefined = OFF; gates build-time mining); widen `DocUse` to
    `"useDraft" | "useRag" | "useExtract"`.
  - `web/frontend/lib/types.ts` — add `includeExtract: boolean` to the persisted
    `ContextDocument` type.
  - `web/frontend/lib/api.ts` — add `includeExtract?: boolean` to
    `ContextDocumentInput`; add `extract?: boolean` to each `BuildWorldBody` doc entry
    (`characterDocs`/`settingDocs`/`uncategorizedDocs`/`otherDocs` item shape becomes
    `{ name: string; text: string; extract?: boolean }`).
  - `web/frontend/features/library/storylineCreator.ts` — add `useExtract?: boolean` to
    `UploadDefaults`; `toCreatorDoc` seeds `useExtract: opts.useExtract ?? doc.useExtract ?? false`;
    `fromContextDocument` maps `useExtract: doc.includeExtract`; `docToContextInput`
    sends `includeExtract: Boolean(d.useExtract)`; `applyTriage` carries
    `useExtract: t.includeExtract` (so a triage suggestion applies like Draft/RAG).
  - `web/frontend/features/library/useStorylineCreator.ts` — widen `toggleDocUse`'s
    key param to `DocUse`; in `build`, make `toBuildDoc` emit
    `{ name, text, extract: Boolean(d.useExtract) }` for all four buckets (bucketing by
    category unchanged — the backend gate does the filtering); ensure the triage
    `applyTriage` path passes `includeExtract` through (its item already carries it).
  - `web/frontend/components/feature/TriagePanel.tsx` — add
    `{ key: "useExtract", label: "Extract", title: "Mine this file for named characters/settings during Build" }`
    to `USES`; add an `uploadExtract` state (default `false`) + wire it into the
    upload-default toggle row and `uploadOpts.useExtract`. (Per-row rendering already
    maps `USES` generically, so the chip appears automatically.)
  - `web/frontend/features/library/entityDocs.ts` — round-trip the field for
    consistency: map `useExtract: d.includeExtract` on read and
    `includeExtract: f.useExtract ?? false` on `toContextInput` (entity docs default
    off; no Extract chip added to `ContextFilesPanel`).
- **Rationale:** the UI + client types are the author-facing half; with the backend
  gate already live, the chip immediately controls real behavior and the persisted
  field round-trips on save/reopen.
- **Action:** Run this phase's validation — `cd web/frontend && npm test` for
  `features/library/storylineCreator.test.ts` (`toCreatorDoc` default `useExtract=false`;
  `docToContextInput` emits `includeExtract`; `fromContextDocument` maps it; `applyTriage`
  carries it), `components/feature/TriagePanel.test.tsx` (renders the Extract chip,
  toggles per-row + upload default), `features/library/useStorylineCreator.test.ts`
  (build sends `extract` on the `BuildDoc`s; an unchecked doc rides with `extract:false`),
  and `entityDocs.test.ts` if touched; then `npm run typecheck` + `npm run lint`. Add an
  accessibility pass for the new chip (it reuses the existing `aria-pressed` toggle
  idiom + AA `--field`/`--card` tokens; reachable at 320/375/768/1024 in the same
  flex-wrap row). Once green, commit:
  `[Extraction Opt-In] (3/4) Complete: Extract toggle chip + creator state + build request carry includeExtract.`

### Phase 4 — Docs, full validation, merge

- **Locations:**
  - `docs/api-contract.md` — `ContextDocument.includeExtract` field + `BuildDoc.extract`
    input + the "extraction is opt-in per document" build policy.
  - `docs/data-flow.md` — the build's extraction stage now gated by the per-doc Extract
    flag (default off; triage suggests conservatively).
  - `docs/design-system.md` — the Triage panel's third **Extract** toggle chip.
  - `docs/component-map.md` — `TriagePanel` Extract chip note.
  - `docs/documentation.md` — status line if applicable.
  - `docs/checklist.md` — a "done" entry summarizing the feature + validation counts.
- **Action:** Full gate — backend `uv run pytest` (+ `ruff`/`mypy` on touched files);
  frontend `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`. Record a
  live-browser deferral note if the standing worktree shared-dir/CORS constraint blocks
  a clean `preview_start` (verify via the green component suites instead), consistent
  with prior authoring entries. Once green, commit:
  `[Extraction Opt-In] (4/4) Complete: Docs, validation, and merge to main.` Then merge
  the worktree into `main`, resolving any conflicts.

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Persisted flag | `include_extract` column (NOT NULL, server-default false) + self-healing migration | `web/backend/app/models/context_document.py`, `web/backend/alembic/versions/20260706_120000_context_doc_include_extract.py` |
| Schema wiring | `includeExtract` on Base/Read/Update + `TriageItem` | `web/backend/app/schemas/context_document.py` |
| CRUD persistence | create/bulk/update carry `include_extract` | `web/backend/app/services/crud.py` |
| Build gate | `BuildDoc.extract` + `iter_build_world` mines only `extract=true` docs | `web/backend/app/schemas/build.py`, `web/backend/app/agents/build_agent.py` |
| Conservative triage | `includeExtract` in the triage prompt + `_coerce_item`/`_fallback` (default off) | `web/backend/app/agents/triage_agent.py` |
| Frontend types | `useExtract` (ReadDoc/DocUse), `includeExtract` (ContextDocument/ContextDocumentInput), `extract` on BuildWorldBody docs | `web/frontend/lib/readDocs.ts`, `web/frontend/lib/types.ts`, `web/frontend/lib/api.ts` |
| Creator state | default-off seed, persistence round-trip, triage carry, build request | `web/frontend/features/library/storylineCreator.ts`, `useStorylineCreator.ts`, `entityDocs.ts` |
| Extract UI chip | third toggle chip (per-row + upload default) in Triage | `web/frontend/components/feature/TriagePanel.tsx` |
| Backend tests | context-doc round-trip, build gate on/off, triage coercion, BuildDoc default | `utils/tests/backend/api/test_context_documents.py`, `utils/tests/backend/agents/test_build_agent.py`, `.../test_triage_agent.py`, `.../test_build*` |
| Frontend tests | creator mappers, Triage chip, build request flag | `web/frontend/features/library/storylineCreator.test.ts`, `useStorylineCreator.test.ts`, `web/frontend/components/feature/TriagePanel.test.tsx` |
| Docs | api-contract, data-flow, design-system, component-map, documentation, checklist | `docs/*.md` |
