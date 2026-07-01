# Character Voice & Tone Consistency

## 1. Introduction

Characters in Velora drift in tone during roleplay: each character "thinks" and "speaks" according to their `personality`/`speech` descriptors, but there is no concrete, worked example telling the model *how* that personality should actually sound in a line of dialogue or an internal thought. This plan closes that gap by attaching a **voice & tone profile** to every character — a small set of **situation → sample-response** pairs — generated at creation time from the character's background/personality, editable in the character menu, and injected into the live turn loop so both spoken lines and the hidden `<thinking>` step are anchored to a consistent voice.

The approach follows Velora's proven `Setting.timeline` pattern for structured list data: a portable `JSONColumn` on the `Character` model, a Pydantic sub-model with a `None → []` coercion, an Alembic migration chained onto the current head (`f1a2b3c4d5e6`), a dedicated generation agent + endpoint mirroring `propose_starting_stats`, a repeatable-rows editor UI modeled on `StatsEditor`, and a per-speaker HEAD injection in `character_turn_agent` (kept out of the byte-identical system message so vLLM prefix caching still holds). Best-effort throughout: a character with no samples behaves exactly as today.

**Data shape (locked):** each pair is `{ situation, sample }` — `situation` is a short description of a story event or interaction; `sample` is what the character would say/do in response. Stored as `character.voice_samples` (`list[dict]`), surfaced as `voiceSamples: { situation, sample }[]` in the frontend.

## 2. Gaps & Unanswered Questions

- **Storage type (resolved, assumption):** use `JSONColumn` (`list[dict]`) exactly like `Setting.timeline` — nullable, `default=list`, self-heals via the additive reconciler on dev DBs and Alembic on Postgres. No new table (samples are authored prose, not queried relationally).
- **Generation: one call or dedicated?** (resolved, assumption): a **dedicated** `propose_voice_samples` agent + `POST /characters/voice-samples` endpoint, mirroring `propose_starting_stats`. Keeps the flat `draft_character` JSON stable (small local models parse it more reliably) and gives the edit menu a real "Propose / Redo" button. The standalone Character Creator auto-calls it after drafting identity; the world build calls it per character. Both run it **before** starting stats, satisfying "voice/tone comes first."
- **Sample count (resolved, assumption):** target **3** pairs (accept 2–4). Enough to establish cadence without bloating the turn prompt.
- **Prompt placement (resolved):** per-character samples go in the **user-message HEAD** of `character_turn_agent` (not the shared system contract, which must stay byte-identical for prefix caching). The generic `<thinking>` instruction in `_OUTPUT_CONTRACT` is nudged to "think in the same voice" — that text is character-agnostic, so the prefix stays stable.
- **Migration head (resolved):** current Alembic head is `f1a2b3c4d5e6` (event_session_seq_unique); the new migration chains after it.
- **No complex gaps requiring human intervention.**

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend persistence (model · schema · migration · CRUD · RAG)

- **Locations:**
  - `web/backend/app/models/character.py` — add `voice_samples: Mapped[list[dict] | None] = mapped_column(JSONColumn, nullable=True, default=list)` (import `JSONColumn` from `app.core.db`); documented like `Setting.timeline`.
  - `web/backend/app/schemas/character.py` — add a `VoiceSample(CamelModel){ situation: str = ""; sample: str = "" }`; add `voice_samples: list[VoiceSample] | None = None` to `CharacterBase` + `CharacterUpdate`; add `voice_samples: list[VoiceSample] = []` to `CharacterRead` with a `_coerce_voice_samples` before-validator (`None → []`), mirroring `SettingRead._coerce_timeline`.
  - `web/backend/app/services/crud.py` — `create_character` explicitly sets `voice_samples=data.voice_samples or []`; `update_character` already patches via `model_dump(exclude_unset=True)` (verify JSON round-trips).
  - `web/backend/alembic/versions/<ts>_character_voice_samples.py` — new revision, `down_revision = 'f1a2b3c4d5e6'`, `batch_alter_table('characters')` add nullable `sa.JSON()` column `voice_samples`; reverse drop in `downgrade`.
  - `web/backend/app/rag/entries.py` — extend `entry_from_character` body with a compact rendering of the samples (e.g. `Voice: "<sample>"` lines) so retrieval reflects voice.
- **Rationale:** Every downstream layer (generation, editor, turn loop) reads/writes this column, so the persistence foundation must land first and be independently verifiable.
- **Tests:** `utils/tests/backend/data/test_characters.py` (or the existing character data test) — round-trip a character with samples; null column reads as `[]`; `CharacterRead` shape includes `voiceSamples`. RAG: `utils/tests/backend/` existing entries test asserts a sample string reaches the body (if such a test exists; else add a focused one).
- **Action:** Run `.venv/bin/python -m pytest utils/tests/backend/data utils/tests/backend/... ` for affected areas + ruff/mypy on touched files. Once green, commit: `[Character Voice & Tone] (1/6) Complete: persist voice_samples on Character (model, schema, migration, CRUD, RAG).`

### Phase 2 — Turn-loop prompt injection (assembler · character_turn_agent)

- **Locations:**
  - `web/backend/app/services/assembler.py` — add `voice_samples: str = ""` to the `CastMember` dataclass; in `_build_cast`, render `char.voice_samples` (list) into a compact multi-line block via a small `_format_voice_samples(...)` helper (`""` when empty) and pass it to `CastMember`.
  - `web/backend/app/agents/character_turn_agent.py` — in `_build_user_prompt` HEAD (after the `speech`/`traits` lines), append a `Voice samples — how you sound (match this cadence and attitude):` block when `speaker.voice_samples`; nudge the `_OUTPUT_CONTRACT` `<thinking>` line to "think in that same voice" (character-agnostic → prefix cache unaffected).
- **Rationale:** This is the feature's core payoff (Step 4). It depends only on Phase 1's column, is backend-only, and immediately benefits any character with samples (even hand-typed), independent of the generation/UI phases.
- **Tests:** `utils/tests/backend/services/test_assembler.py` — samples read into `CastMember.voice_samples` (and empty when none). `utils/tests/backend/agents/test_character_turn_agent.py` — a sample string reaches the user prompt HEAD; the `<thinking>` contract references voice; omitted cleanly when absent.
- **Action:** Run `.venv/bin/python -m pytest utils/tests/backend/services/test_assembler.py utils/tests/backend/agents/test_character_turn_agent.py` + ruff/mypy. Once green, commit: `[Character Voice & Tone] (2/6) Complete: inject per-character voice samples into the turn-loop prompt + thinking step.`

### Phase 3 — Generation agent + endpoint + world-build wiring (backend)

- **Locations:**
  - `web/backend/app/schemas/character.py` — `VoiceSamplesRequest(CamelModel)` (name/role/traits/speech/background/personality/storyline_id) + `VoiceSamplesResponse(CamelModel){ samples: list[VoiceSample] = [] }`, mirroring the `StartingStats*` shapes.
  - `web/backend/app/agents/character_agent.py` — new `propose_voice_samples(db, *, ...)`: a focused LLM call grounded in the drafted background/personality/traits/speech (+ `world_context`) that returns 2–4 `{situation, sample}` pairs; parse defensively, cap, best-effort → `[]` on failure. Reuse `DEFAULT_AUTHORING_EFFORT`.
  - `web/backend/app/routes/characters.py` — `POST /characters/voice-samples` → `character_agent.propose_voice_samples`.
  - `web/backend/app/schemas/build.py` — add `voice_samples: list[VoiceSample] = []` to `ProposedCharacter`.
  - `web/backend/app/agents/build_agent.py` — in `iter_build_world`, after `draft_character` and **before** attaching default stats, call `propose_voice_samples` best-effort and set it on the `ProposedCharacter` (skip-on-failure so build never blocks).
- **Rationale:** Auto-populates the profile at creation (Step 1), ordered before stats. Dedicated endpoint powers the editor's Propose/Redo (Phase 5) and keeps `draft_character` output stable.
- **Tests:** `utils/tests/backend/agents/test_character_agent.py` — `propose_voice_samples` parses/caps/best-effort (offline-mocked LLM). `utils/tests/backend/api/` — route returns samples. `utils/tests/backend/agents/test_build_agent.py` — a built character carries voice samples (mocked).
- **Action:** Run `.venv/bin/python -m pytest` for the agent/api/build areas + ruff/mypy. Once green, commit: `[Character Voice & Tone] (3/6) Complete: voice-sample generation agent + endpoint + world-build wiring.`

### Phase 4 — Frontend plumbing (types · API · draft state)

- **Locations:**
  - `web/frontend/lib/types.ts` — `VoiceSample = { situation: string; sample: string }`; add `voiceSamples?: VoiceSample[]` to `Character`; add `voiceSamples: VoiceSample[]` to `ProposedCharacter`.
  - `web/frontend/lib/api.ts` — add `voiceSamples` to `CharacterInput` flow (it's `Omit<Character,...>`, so it rides along); add `proposeVoiceSamples(body)` → `POST /characters/voice-samples` returning `{ samples }`.
  - `web/frontend/features/library/editor.ts` — add `_voiceSamples?: VoiceSample[]` to `Draft`; seed `DEFAULT_DRAFTS.character._voiceSamples = []`.
  - `web/frontend/features/library/useLibraryState.ts` — `editCharacter` hydrates `_voiceSamples` from `c.voiceSamples ?? []`; character submit body sends `voiceSamples: d._voiceSamples ?? []`; add a `proposeVoiceSamples()` handler (mirrors `proposeStartingStats`, sets `_voiceSamples`); `draftCharacter` auto-generates samples after identity draft (best-effort), **before** the stat proposal.
  - `web/frontend/features/library/storylineCreator.ts` — `proposedToCharacterInput` maps `voiceSamples` into the create body.
- **Rationale:** Shared plumbing both frontend surfaces (edit menu + world build) depend on; isolating it keeps the UI phase focused.
- **Tests:** `web/frontend/features/library/useLibraryState.character.test.ts` — persist-on-save + rehydrate-on-edit + propose handler sets samples. `web/frontend/features/library/storylineCreator.test.ts` — `proposedToCharacterInput` carries `voiceSamples`. `web/frontend/lib/api.test.ts` — `proposeVoiceSamples` shape.
- **Action:** Run `npm test` (affected files) + `npm run typecheck`. Once green, commit: `[Character Voice & Tone] (4/6) Complete: frontend types, API client, and draft-state plumbing for voice samples.`

### Phase 5 — Frontend UI (CharacterModal editor + world-build display) + a11y/responsive pass

- **Locations:**
  - `web/frontend/components/feature/VoiceSamplesEditor.tsx` — new repeatable-rows editor (modeled on `StatsEditor`): each row = a `situation` input + a `sample` textarea, with add/remove/patch; `role="group"`/`aria-label` per row; accent-colored `+ Add sample` / `Remove` controls; empty-state hint.
  - `web/frontend/components/feature/CharacterModal.tsx` — render a **"Voice & Tone"** section (`<FieldLabel>` + description + `<VoiceSamplesEditor>` + a "Propose / Redo" button wired to `proposeVoiceSamples`) **immediately above** the Starting Stats section (before the `{/* Starting stats … */}` block, ~line 311).
  - `web/frontend/components/feature/WorldBuildPanel.tsx` — show a compact voice-samples indicator on each proposed character card (count/preview) so the build surface reflects Step 1.
- **Rationale:** Delivers the editable section (Step 3, positioned above stats) and makes generated samples visible in the storyline creation flow (Step 1). Involves new interactive surface → requires the a11y/responsive pass.
- **Tests:** `web/frontend/components/feature/VoiceSamplesEditor.test.tsx` (add/remove/patch rows). `web/frontend/features/library/CharacterModal.test.tsx` (section renders above stats; Propose button calls the API; rows editable). `web/frontend/components/feature/WorldBuildPanel.test.tsx` (samples shown).
- **Action:** Run `npm test` + `npm run typecheck` + `npm run lint` + `next build`; **accessibility + responsive pass** (keyboard add/remove/edit, visible focus, contrast, 320/375/768/1024) — live if the shared-dir/CORS constraint allows, else verify structurally and document the deferral in `docs/checklist.md`. Once green, commit: `[Character Voice & Tone] (5/6) Complete: Voice & Tone editor above Starting Stats + world-build display.`

### Phase 6 — Docs + full validation + merge to main

- **Locations:** `docs/api-contract.md` (Character read/write `voiceSamples` + `/characters/voice-samples` endpoint + turn-prompt note), `docs/data-flow.md` (voice samples in the authoring + turn-injection flows), `docs/documentation.md` (status), `docs/component-map.md` (`VoiceSamplesEditor` + CharacterModal section), `docs/checklist.md` (this entry + any deferrals). Then merge `feat/character-voice-tone` → `main`, resolving conflicts.
- **Rationale:** Docs must move with behavior (global rules); the worktree merges back per the task.
- **Action:** Full backend `.venv/bin/python -m pytest` + frontend `npm test`/`typecheck`/`lint`/`next build` all green. Commit: `[Character Voice & Tone] (6/6) Complete: docs + validation; merge voice/tone consistency to main.` Merge to `main` (do not push unless asked).

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| `voice_samples` column | `JSONColumn` list of `{situation, sample}` on Character | `web/backend/app/models/character.py` |
| `VoiceSample` + schema wiring | Pydantic sub-model; Base/Update/Read (+ `None→[]` coercion) | `web/backend/app/schemas/character.py` |
| Alembic migration | Add nullable `voice_samples` (chained on `f1a2b3c4d5e6`) | `web/backend/alembic/versions/<ts>_character_voice_samples.py` |
| RAG body inclusion | Voice samples in the character lore entry body | `web/backend/app/rag/entries.py` |
| Turn-prompt injection | `CastMember.voice_samples` + HEAD block + `<thinking>` nudge | `web/backend/app/services/assembler.py`, `web/backend/app/agents/character_turn_agent.py` |
| Generation agent + endpoint | `propose_voice_samples` + `POST /characters/voice-samples` | `web/backend/app/agents/character_agent.py`, `web/backend/app/routes/characters.py`, `web/backend/app/schemas/character.py` |
| World-build wiring | `ProposedCharacter.voice_samples` generated before stats | `web/backend/app/schemas/build.py`, `web/backend/app/agents/build_agent.py` |
| Frontend plumbing | Types, API client, draft state, build mapper | `web/frontend/lib/types.ts`, `web/frontend/lib/api.ts`, `web/frontend/features/library/{editor,useLibraryState,storylineCreator}.ts` |
| Voice & Tone editor | Repeatable situation→sample rows + Propose/Redo | `web/frontend/components/feature/VoiceSamplesEditor.tsx`, `web/frontend/components/feature/CharacterModal.tsx` |
| World-build display | Voice-samples indicator on proposed characters | `web/frontend/components/feature/WorldBuildPanel.tsx` |
| Backend tests | Data round-trip, assembler, agents, build, route | `utils/tests/backend/{data,services,agents,api}/...` |
| Frontend tests | Editor, modal, state, api, build panel | `web/frontend/**/*.test.{ts,tsx}` |
| Docs | Contract, data-flow, status, component-map, checklist | `docs/*.md` |
