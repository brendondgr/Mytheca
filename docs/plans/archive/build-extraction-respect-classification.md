# Build Extraction — respect the author's classification (stop inventing entities)

## 1. Introduction

**Build the whole world** runs a multi-subject *extraction* pass over **every**
attached document and drafts a card per subject it "finds." The extraction prompt is
too eager: it invents/expands characters and settings out of lore documents that
contain no real named subject, and it mines even the documents the author explicitly
classified as a single Character or Setting. The author's report: *"it is extracting
new characters out of documents that are non-existent, by taking context and expanding
them… I have provided characters and settings. You should only do that with the items
classified as Uncategorized… it must be a NAMED character/setting, otherwise it should
not create one."*

This plan makes the build **respect the author's triage bucket** and makes extraction
**strict and named-only**:

- **Character** docs → extract **only named characters** — normally exactly one (the
  doc *is* that character), split into several only if the doc clearly names several
  distinct people. Never invent. If no explicit name is found, the whole doc still
  becomes **one** character (the classification is the author's assertion that it is
  one).
- **Setting** docs → same, for named settings.
- **Uncategorized** (`select`) docs → read carefully and produce an entity **only if a
  genuinely, explicitly NAMED** character or setting is present; a lore/history/rules/
  atmosphere doc with no named profile-worthy subject yields **nothing**.
- **Other** docs → **lore/grounding only** — never become entities; they still ground
  the world (folded into the drafting grounding).

Backend agent + orchestrator carry the policy; one new request field
(`uncategorizedDocs`) and a frontend bucket-split feed it. No change to the streaming
contract or the event types.

## 2. Gaps & Unanswered Questions

Resolved with the user:

- **Classified Character/Setting docs → one entity, split only if clearly multiple**
  (never invent; fall back to one when no explicit name is found).
- **Other bucket → lore/grounding only** (never an entity); only **Uncategorized**
  docs get the strict named-entity extraction.

Assumptions (simple gaps — proceeding):

- **Strict extraction is prompt-enforced.** The system prompt requires an *explicitly
  named*, genuinely-profiled subject; forbids inventing/inferring/expanding from lore,
  history, rules, factions, events, or terms; and requires returning empty lists for
  documents without a named profile-worthy subject. A name merely *mentioned in
  passing* is not extracted.
- **Kind-scoping.** Extraction takes a `kind` (`character` / `setting` / `both`): a
  Character-bucket doc is mined only for characters, a Setting-bucket doc only for
  settings, an Uncategorized doc for both.
- **Classified fallback.** For a Character/Setting doc that yields no named subject
  (or whose extraction fails), the whole doc becomes exactly **one** entity of that
  kind — the classification guarantees ≥1. Uncategorized docs have **no** fallback
  (0 is a valid, expected result).
- **Other docs ground, don't extract.** Their text folds into the bounded drafting
  grounding (so drafts stay consistent with the lore) but never produces a card.
- **Backend distinguishes Uncategorized from Other.** The frontend currently bundles
  both into `otherDocs`; add a separate `uncategorizedDocs` list so the backend can
  apply the two different policies.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Strict, bucket-scoped extraction (backend)

- **Locations:**
  - `web/backend/app/agents/extract_agent.py` — rewrite `_EXTRACT_SYSTEM` to be
    **strict / named-only / no-invention** (return empty for lore); add a `kind:
    Literal["character","setting","both"] = "both"` parameter that (a) injects a
    kind-specific instruction and (b) clears the off-kind list in the result.
  - `web/backend/app/agents/build_agent.py` — replace the single "mine every doc"
    extract stage with a **kind-tagged work-list**: `character_docs` → `kind="character"`,
    `setting_docs` → `kind="setting"`, `uncategorized_docs` → `kind="both"`; **exclude
    `other_docs` from extraction** and instead **fold their text into `grounding`**
    (bounded by `DOCS_CAP`). Keep the concurrent, failure-isolated, per-doc-progress
    loop. Add `_collect_roster(jobs, found_slots)` — folds results in **document
    order**, picks the kind per job, and applies the **classified fallback-to-one**
    (a Character/Setting doc that produced nothing → one entity from the whole doc);
    Uncategorized docs get **no** fallback. `_extract_one` gains a `kind` passthrough.
    `iter_build_world` + `build_world` gain an `uncategorized_docs` parameter.
  - `web/backend/app/schemas/build.py` — `BuildWorldRequest.uncategorized_docs:
    list[BuildDoc] = []` (+ update the field docstring); `has_buildable_docs` covers
    it.
  - `web/backend/app/routes/storylines.py` — pass `data.uncategorized_docs` through
    both `/build` and `/build/stream`.
- **Rationale:** the invention comes from (a) an eager prompt and (b) mining classified
  + Other docs. Scoping extraction by bucket and tightening the prompt fixes both at
  the source, while the fallback honors an explicit classification.
- **Action:** Run this phase's validation — `uv run pytest` for
  `utils/tests/backend/agents/test_extract_agent.py` (strict: lore/unnamed → empty;
  named → entity; passing-mention not extracted; `kind` scoping clears the off-kind
  list) and `utils/tests/backend/agents/test_build_agent.py` (Character doc → char
  only + fallback-to-one when unnamed; Setting doc → setting only; **Uncategorized doc
  → strict extraction, lore → nothing**; **Other doc → NO entity but grounds**; a
  clearly-multi Character doc still splits); `ruff` + `mypy` on touched files. Once
  green, commit: `[Build Classification] (1/3) Complete: Strict, bucket-scoped doc extraction (respect classification, no invention).`

### Phase 2 — Frontend sends the four buckets

- **Locations:**
  - `web/frontend/lib/api.ts` — `BuildWorldBody.uncategorizedDocs?: {name,text}[]`.
  - `web/frontend/features/library/useStorylineCreator.ts` — split the kept docs into
    **four** lists by `category`: `character` → `characterDocs`, `setting` →
    `settingDocs`, `select` → `uncategorizedDocs`, `other` → `otherDocs`; send all
    four (update the comment describing the policy).
- **Rationale:** the backend needs Uncategorized separated from Other to apply the two
  policies; the split is a pure routing change (no UI surface change).
- **Action:** Run validation — `useStorylineCreator` hook tests (an Uncategorized doc
  rides `uncategorizedDocs`; an Other doc rides `otherDocs`; character/setting
  unchanged); `tsc` + ESLint. Once green, commit:
  `[Build Classification] (2/3) Complete: Frontend routes each triage bucket to its own build list.`

### Phase 3 — Docs, validation, merge

- **Locations:** `docs/data-flow.md` (the build's per-bucket extraction policy),
  `docs/api-contract.md` (build request `uncategorizedDocs` + the bucket policy),
  `docs/documentation.md` (status), `docs/checklist.md` (done entry — supersedes the
  eager multi-entity behavior).
- **Action:** Full gate — backend `uv run pytest`, `ruff`/`mypy`; frontend `npm test`
  + `npm run typecheck` + `npm run lint` + `npm run build`. Once green, commit:
  `[Build Classification] (3/3) Complete: Docs, validation, and merge to main.` Then
  merge the worktree into `main`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Strict extraction | Named-only, no-invention prompt + `kind` scoping | `web/backend/app/agents/extract_agent.py` |
| Bucket-scoped orchestration | char→char, setting→setting, uncategorized→both, other→grounding; classified fallback-to-one; doc-order collect | `web/backend/app/agents/build_agent.py` |
| Request field | `uncategorizedDocs` on the build request + route passthrough | `web/backend/app/schemas/build.py`, `web/backend/app/routes/storylines.py` |
| Frontend routing | Split kept docs into four buckets, send all four | `web/frontend/lib/api.ts`, `web/frontend/features/library/useStorylineCreator.ts` |
| Tests | Strict/kind/fallback + per-bucket build behavior + hook routing | `utils/tests/backend/agents/test_{extract,build}_agent.py`, `web/frontend/features/library/useStorylineCreator.test.ts` |
