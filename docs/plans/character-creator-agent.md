# Velora — Agentic Character Creator (prep phase)

## 1. Introduction

This plan adds an **agentic Character Creator** that mirrors the existing
storyline authoring flow (`storyline_agent.py` + `StorylineModal.tsx`) but for
**characters**. Given a one-sentence seed and/or dropped reference documents, a
new `character_agent` drafts the character's *own* descriptive substance —
**background, personality sheet, physical appearance** (plus the existing
role/traits/speech/goal/secret) — proposes **starting statistics** keyed to the
storyline's stat schema, and, when the operator opts in, generates a **watercolor
profile portrait** through the already-proven ComfyUI pipeline. The portrait is
saved as **WebP** and shown as the character's avatar (monogram fallback).

This is explicitly the **preparation phase for the character knowledge graph
described in `Documents/Plans/3.character-graph-structure-prep.md` — but it builds
NONE of the graph.** Per §1 of that document, everything produced here is a
**node property** (base identity: appearance/backstory/personality/voice + a
starting stat block), never an edge, node-type, secret-node, or Neo4j structure.
No `acquired_trait`, no relationship edges, no propagation. The deliverable is the
*agentic process* that fills a character's authored, base-identity layer so the
graph work later has rich, structured material to connect.

Architecture fit: a new `app/agents/character_agent.py` reuses the
`services/llm.chat_complete` primitive and the settings store exactly as
`storyline_agent` does; new fixed-path routes hang off the existing character
router; a new `app/services/portraits.py` wraps `services/comfyui.generate` and
converts PNG→WebP; the frontend gets a dedicated `CharacterModal.tsx` (mirroring
`StorylineModal.tsx`) wired through `useLibraryState` and `lib/api.ts`.

## 2. Gaps & Unanswered Questions

Resolved with the user before planning:

- **Portrait scope → Generate + persist as avatar, but encode WebP (not PNG).**
  The agent writes positive/negative prompts; the backend runs ComfyUI, converts
  the result to WebP, saves it under a served media directory, stores the path on
  the character, and the UI renders it with a monogram fallback.
- **Starting stats → Propose only, with explicit Save / Redo.** The agent
  proposes starting values (keyed to the storyline's existing stat definitions and
  within their ranges); they are shown in the draft for review. Nothing is written
  until the user clicks **Save** (applies via the existing
  `PUT /characters/{id}/stats`); **Redo** re-proposes.

Assumptions taken (simple gaps):

- **New base-identity fields are stored as nullable columns on `Character`**
  (`appearance`, `background`, `personality`, `portrait`). They are additive +
  nullable, so the preflight's `_reconcile_additive_columns` self-heals the
  persistent dev DB (no manual `ALTER`, consistent with the `world_primer`
  precedent). The short `traits` line is kept as-is; `personality` is the fuller
  sheet.
- **Portrait files** live under a new gitignored media dir
  (`MEDIA_DIR`, default `<repo>/media/portraits/`), served by a FastAPI
  `StaticFiles` mount at `/media`. The character stores a relative URL
  (`/media/portraits/<uuid>.webp`); the frontend prefixes it with the API origin.
- **Portrait generation is character-id-agnostic** (`POST /characters/portrait`):
  it generates + saves a WebP and returns its URL, which the draft carries into the
  normal create/update payload. This works during *creation* (no id yet) and edit
  alike. Orphaned files from cancelled drafts are acceptable in this prep phase
  (cleanup is a noted follow-up).
- **Watercolor style** matches the configured ComfyUI workflow (`ZiT-Workflow.json`,
  Z-Image-Turbo, ~4-step watercolor). The agent's positive prompt is short
  comma-separated phrases leading with subject identity (species/race, age,
  gender, signature features, attire, expression) plus watercolor-portrait style
  tags; the negative prompt lists artifacts to avoid. Style is **watercolor
  portrait** (the live pipeline), not photoreal.
- **No new LLM/agent infra.** Reuse `chat_complete`, the `_gen_params` ≥8192-token
  floor (reasoning-model budget — see memory), the 300 s generation timeout, and
  the `settings_store` credential resolution. Portrait calls reuse `comfyui`.

No remaining questions require human intervention.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend data layer: base-identity + portrait fields on `Character`

- **Locations:** `web/backend/app/models/character.py` (add nullable
  `appearance`, `background`, `personality`, `portrait` columns);
  `web/backend/app/schemas/character.py` (add the four fields to
  `CharacterBase`/`Create`/`Update`/`Read`, all defaulting empty/None);
  `web/backend/app/services/crud.py` (`create_character`/`update_character` pass
  the new fields through — they already loop generically for update; create needs
  explicit assignment); seed (`web/backend/app/services/seed.py` or wherever
  Embergate is seeded) — give one sample character populated values;
  `utils/tests/backend/data/` + `utils/tests/backend/api/` (roundtrip + default
  + PATCH of the new fields). Docs: `docs/api-contract.md` (Character shape gains
  `appearance`/`background`/`personality`/`portrait`), `docs/structure.md`
  (`characters` columns note), `docs/documentation.md` (status line).
- **Rationale:** The agent and UI need somewhere to *store* the richer base
  identity before either can produce it. Doing the schema first keeps every later
  phase persisting into real columns. Nullable + additive so the dev DB self-heals.
- **Action:** Run `uv run pytest` (data + api), ruff/mypy. Once green, commit:
  `Character Creator (1/6) Complete: base-identity + portrait columns on Character.`

### Phase 2 — Backend agent: `character_agent.py` (draft · portrait prompts · starting stats)

- **Locations:** `web/backend/app/agents/character_agent.py` (new) with
  `draft_character(db, seed, docs_overview, storyline_id=None)` →
  `CharacterDraftResponse`; `generate_portrait_prompts(db, character_fields)` →
  `PortraitPromptResponse{positive, negative}`; `propose_starting_stats(db,
  storyline_id, character_fields)` → `StartingStatsResponse{proposals:[{key,
  displayName, value, min, max, rationale}]}`. Reuse the `storyline_agent` helpers
  pattern (`_resolve`, `_gen_params` ≥8192 floor, `_docs_block`, `_extract_json`)
  — extract the shared JSON/tolerance/`_resolve` helpers into the new module or a
  tiny `agents/_common.py` if it avoids duplication. Schemas in
  `web/backend/app/schemas/character.py`: `CharacterDraftRequest{seed,
  docsOverview, storylineId?}`, `CharacterDraftResponse` (name/role/traits/speech/
  goal/secret/appearance/background/personality/color), `PortraitPromptRequest`
  (the character fields + optional species/notes), `PortraitPromptResponse`,
  `StartingStatsRequest{storylineId, ...character fields}`, `StartingStatsResponse`.
  Routes in `web/backend/app/routes/characters.py`: `POST /characters/draft`,
  `POST /characters/portrait-prompts`, `POST /characters/starting-stats` —
  declared **before** the `/characters/{character_id}` routes (mirror the storyline
  `/draft`,`/primer` ordering). `propose_starting_stats` reads the storyline's
  `StatDefinition`s (via `stat_service.list_stat_definitions`) and only proposes
  those keys, clamped to each `[min,max]`; returns empty when the storyline defines
  no stats. Tests: `utils/tests/backend/agents/test_character_agent.py` mirroring
  `test_storyline_agent.py` (httpx `MockTransport`, `_configure_llm`, fenced-JSON
  parse, empty-config 400, stats keyed to seeded definitions). Docs:
  `docs/api-contract.md` (Authoring endpoints), `docs/data-flow.md` (character
  authoring flow).
- **Rationale:** This is the heart of the feature — the agentic production of base
  identity, portrait prompts, and starting stats. It depends on Phase 1's fields
  existing (so the draft response shape matches storage) and must be exercised
  offline before any UI calls it.
- **Action:** Run `uv run pytest` (agents + api), ruff/mypy. Once green, commit:
  `Character Creator (2/6) Complete: character_agent draft + portrait prompts + starting-stat proposals.`

### Phase 3 — Backend portrait generation + WebP persistence + serving

- **Locations:** add dep `pillow` (`uv add pillow`; record in
  `docs/architecture.md` + `docs/workflow.md`). `web/backend/app/core/config.py`:
  `media_dir: Path` (env `MEDIA_DIR`, default `<REPO_ROOT>/media`) + `portraits_dir`
  property. `.env.example` + `docs/deployment.md`: document `MEDIA_DIR`.
  `web/backend/app/main.py`: ensure the dir exists and `app.mount("/media",
  StaticFiles(directory=...), name="media")` (root mount, not under `/api`).
  `web/backend/app/services/portraits.py` (new): `generate_portrait(db, positive,
  negative, *, base_url?, workflow?, width?, height?, steps?, cfg?)` → resolve
  comfy config via `settings_store.get_comfy` / `resolve_comfy_base_url`, call
  `comfyui.generate(...)` (per-character positive/negative; portrait-orientation
  size default e.g. 832×1216), convert PNG bytes → WebP with Pillow, write
  `<uuid>.webp` to `portraits_dir`, return `{"portrait": "/media/portraits/<id>.webp"}`.
  Route in `routes/characters.py`: `POST /characters/portrait` (id-agnostic) with
  `PortraitGenerateRequest{positive, negative, baseUrl?, workflow?, width?,
  height?, steps?, cfg?}` → `PortraitGenerateResponse{portrait}`. Tests:
  `utils/tests/backend/services/test_portraits.py` — monkeypatch
  `comfyui.generate` to return fake PNG bytes; assert a real WebP is written
  (Pillow can reopen it, `format == "WEBP"`) and the URL is returned; route test
  via `TestClient` with the patched service. Docs: `docs/api-contract.md`,
  `docs/structure.md` (media dir), `docs/workflow.md`/`docs/architecture.md`
  (pillow), `docs/deployment.md` (MEDIA_DIR + static mount).
- **Rationale:** Realizes the "persist as WebP avatar" decision while keeping the
  ComfyUI client and bundled workflow untouched (convert at the edge). Id-agnostic
  so creation can attach a portrait before the character row exists.
- **Action:** Run `uv run pytest` (services + api), ruff/mypy. Once green, commit:
  `Character Creator (3/6) Complete: ComfyUI→WebP portrait generation, media serving.`

### Phase 4 — Frontend types, API client, and `useLibraryState` handlers

- **Locations:** `web/frontend/lib/types.ts` (`Character` gains `appearance`,
  `background`, `personality`, `portrait?`). `web/frontend/features/library/editor.ts`
  (`Draft` gains `appearance`/`background`/`personality`/`portrait` + internal
  `_portraitPositive`/`_portraitNegative`/`_startingStats`; `DEFAULT_DRAFTS.character`
  + `editCharacter` prefill updated; `isDraftValid` unchanged). `web/frontend/lib/api.ts`:
  extend `CharacterInput`; add `draftCharacter(seed, docsOverview?, storylineId?)`,
  `generatePortraitPrompts(body)`, `proposeStartingStats(body)`,
  `generatePortrait(body)` + their result interfaces; add `setCharacterStats(id,
  values)` (`PUT /characters/{id}/stats`); add a `mediaUrl(path)` helper resolving
  `/media/...` against the API origin. `web/frontend/features/library/useLibraryState.ts`:
  add `draftCharacter()`, `generatePortraitPrompts()`, `proposeStartingStats()`,
  `generatePortrait()`, `applyStartingStats(characterId)` handlers — each with its
  own loading flag + error handling (mirror `draftStoryline`/`generatePrimer`);
  doc grounding via `concatDocs(docsForDraft(draft._docFiles))`; the character
  `submit` path includes the new fields + `portrait`; expose everything on the hook
  return. Tests: `web/frontend/features/library/*.test.ts(x)` — a hook test
  (api mocked) asserting `draftCharacter()` populates the new fields + sets `_ai`,
  and that `generatePortrait()` stores `draft.portrait`.
- **Rationale:** Wire the data path end-to-end before building the modal, so the UI
  phase is pure presentation against a tested hook (same sequencing the storyline
  feature used).
- **Action:** Run `npm test` + `npm run typecheck`. Once green, commit:
  `Character Creator (4/6) Complete: character draft/portrait/stat API + hook handlers.`

### Phase 5 — Frontend: `CharacterModal.tsx` (agentic UI) + Library wiring

- **Locations:** `web/frontend/components/feature/CharacterModal.tsx` (new,
  mirroring `StorylineModal.tsx`): main column with the by-hand form (name, role,
  traits, speech, goal, secret + **Appearance**, **Background**, **Personality**
  textareas) and the accent/portrait header (Monogram preview OR the WebP portrait
  when set); an agentic **"❖ Draft with Velora"** seed box + button
  (`lib.draftCharacter`); a detached **context-files** rail reusing the
  `readDocs`/drop-zone + per-file Draft/RAG/KG toggle pattern from `StorylineModal`;
  a **Portrait** section (Generate prompts → editable positive/negative → "Generate
  portrait" → preview + persisted into `draft.portrait`); a **Starting stats**
  section (Propose → list of proposed values with **Save** and **Redo**, Save
  enabled only when editing an existing character / after first save). Reuse
  `Modal`, `Eyebrow`, `TextArea`, `Button`, `Monogram`, `PALETTE`. Wire in
  `web/frontend/features/library/LibraryView.tsx` (render `<CharacterModal lib={lib} />`);
  make `EntityModal` return null for `character` (as it already does for
  `storyline`) so there's no double render; retire the fake character branch of
  `lib.generate()`. Tests: `CharacterModal.test.tsx` (renders the new fields; Draft
  button calls the hook; a dropped doc's text reaches the draft call). a11y +
  responsive pass at 320/375/768/1024 (keyboard, focus, contrast, no overflow);
  if the shared working dir's dev server is occupied, verify structurally + via
  `next build` and record the deferral in `docs/checklist.md` (consistent with
  prior entries).
- **Rationale:** The dedicated modal is the natural mirror of the storyline split
  and the surface the whole feature exists to deliver.
- **Action:** Run `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`;
  attempt the in-browser a11y/responsive pass (or document deferral). Once green,
  commit: `Character Creator (5/6) Complete: agentic CharacterModal (draft, upload, portrait, stats) wired into the Library.`

### Phase 6 — Portrait/identity display in cards & profile + docs/checklist

- **Locations:** a small avatar helper (extend `components/ui/Monogram.tsx` to
  accept an optional `src`, or a thin `Avatar` wrapper) used in
  `components/feature/CharacterCard.tsx`, `CharacterProfileModal.tsx`, and the
  `CharacterForm`/`CharacterModal` preview — render the WebP portrait when present,
  else the monogram. `CharacterProfileModal.tsx` additionally shows
  Appearance / Background / Personality. Docs: `docs/component-map.md`
  (CharacterModal + avatar), `docs/documentation.md` (status: agentic character
  creator landed), `docs/checklist.md` (new "done" entry + deferrals: orphaned-file
  cleanup, RAG/KG toggles still seams, any deferred in-browser a11y pass). Tests:
  card/profile render test asserting the portrait `img` appears when `portrait` is
  set and the monogram otherwise.
- **Rationale:** Closes the loop so a generated portrait actually surfaces as the
  character's face across the Library, and leaves the docs/checklist authoritative.
- **Action:** Run `npm test` + `npm run typecheck` + `npm run build`. Once green,
  commit: `Character Creator (6/6) Complete: portrait avatar + richer profile display, docs finalized.`

### Finalization

- Merge the feature branch into `main` locally (the user asked to **commit, not
  push**; "merge with main" if a branch/worktree is used). Resolve any conflicts.
  Do **not** push or open a PR.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Character base-identity columns | `appearance`/`background`/`personality`/`portrait` (nullable) | `web/backend/app/models/character.py`, `web/backend/app/schemas/character.py`, `web/backend/app/services/crud.py` |
| Character agent | Draft + portrait-prompt + starting-stat generation | `web/backend/app/agents/character_agent.py` |
| Agent schemas + routes | Draft/portrait-prompt/starting-stat request/response + endpoints | `web/backend/app/schemas/character.py`, `web/backend/app/routes/characters.py` |
| Portrait service | ComfyUI→WebP generation + persistence | `web/backend/app/services/portraits.py`, `web/backend/app/main.py`, `web/backend/app/core/config.py` |
| Frontend data path | Types, API calls, hook handlers | `web/frontend/lib/types.ts`, `web/frontend/lib/api.ts`, `web/frontend/features/library/editor.ts`, `web/frontend/features/library/useLibraryState.ts` |
| Character modal | Agentic create/edit UI (draft, upload, portrait, stats) | `web/frontend/components/feature/CharacterModal.tsx`, `web/frontend/features/library/LibraryView.tsx` |
| Avatar + profile display | Portrait-or-monogram avatar; richer profile | `web/frontend/components/ui/Monogram.tsx`, `web/frontend/components/feature/CharacterCard.tsx`, `web/frontend/components/feature/CharacterProfileModal.tsx` |
| Backend tests | Agent, portrait service, CRUD/field roundtrip | `utils/tests/backend/agents/test_character_agent.py`, `utils/tests/backend/services/test_portraits.py`, `utils/tests/backend/{data,api}/...` |
| Frontend tests | Hook + modal + card/profile behavior | `web/frontend/features/library/*.test.ts(x)`, `web/frontend/components/feature/CharacterModal.test.tsx` |
| Docs | Contract, structure, data-flow, deployment, component-map, status, checklist | `docs/*.md` |
