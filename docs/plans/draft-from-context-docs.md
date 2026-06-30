# Draft a Character / Setting from an uploaded Context File (no seed required)

## 1. Introduction

When an author opens the **Character** or **Setting** editor in agentic mode, drops a `.txt`/`.md`
reference file into the **Context files** panel, and leaves its **Draft** toggle on, they expect
"❖ Draft with Velora" to ground the draft on that file. Today it does not: drafting is gated on a
typed **seed sentence** in three independent places, so with no sentence the button is disabled and
the request never fires — the uploaded file is effectively ignored.

This plan removes the *seed-only* requirement and makes a Draft-tagged context file a valid grounding
source on its own. After the change, "Draft with Velora" is enabled when there is **either** a seed
sentence **or** at least one Draft-tagged context file, and the backend `draft_character` /
`draft_setting` agents draft from whichever is present (seed, docs, or both), only erroring when
*both* are empty. The fix spans the FastAPI authoring agents (`web/backend/app/agents/`), the two
modals (`web/frontend/components/feature/`), and the shared `useLibraryState` hook — the request body,
API client, and `ContextFilesPanel` data flow already carry the doc text and need no shape change.

## 2. Gaps & Unanswered Questions

- **What grounds the draft when no seed is given?** *Assumption:* the concatenated Draft-tagged
  context documents (already sent as `docsOverview`). The backend prompt currently opens with
  `"<Entity> seed: {seed}"`; with an empty seed it will instead instruct the model to draft *from the
  provided reference documents*. No new request field is needed.
- **Scenario editor parity?** The scenario draft (`draftScenario` / `scenario_agent.draft_scenario`)
  has the same seed gate, but the user reported only Character and Setting. *Assumption:* keep scope
  to Character + Setting; scenario parity is noted as optional follow-up in `docs/checklist.md`, not
  done here.
- **Both empty:** drafting with no seed *and* no Draft-tagged doc must still fail clearly (button
  disabled on the client; `400 bad_request` on the server if called directly). Confirmed in scope.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend: draft from docs when the seed is empty

- **Locations:**
  - `web/backend/app/agents/character_agent.py` — `draft_character` (the `if not seed: raise APIError(400, …)` guard ~L117-119 and the user-prompt assembly ~L122-123).
  - `web/backend/app/agents/setting_agent.py` — `draft_setting` (guard ~L84-86, prompt ~L88-91).
  - `web/backend/app/schemas/character.py` / `setting.py` — `CharacterDraftRequest` / `SettingDraftRequest` docstrings only (the `seed: str` / `docsOverview` fields already exist; no shape change).
  - Tests: `utils/tests/backend/agents/test_character_agent.py`, `test_setting_agent.py`.
- **Change:** replace the unconditional seed guard with: trim the seed; compute whether
  `docs_overview` has content; if **both** are empty, raise the existing `400 bad_request` (reworded
  to mention reference files, e.g. *"Describe the character in a sentence or add a Draft reference
  file."*). When a seed is present, keep the current `"<Entity> seed: {seed}"` opener; when the seed
  is empty but docs exist, open with a docs-only instruction (e.g. *"Draft a character from the
  reference documents below."*) so the prompt never emits a dangling `"seed: "`. `docs_block` /
  `world_context` / `rag_block` assembly is unchanged.
- **Rationale:** the agent is the lowest gate; until it accepts a docs-only draft, no UI change can
  reach a successful generation.
- **Tests:** update `test_draft_requires_a_seed` (Character + Setting) so it now asserts (a) empty
  seed **and** no docs → `400 bad_request`, and (b) **new:** empty seed **with** `docsOverview` →
  succeeds and the doc text reaches the prompt (extend the existing
  `test_draft_docs_overview_reaches_prompt` monkeypatch pattern with an empty `seed`).
- **Action:** Run `uv run pytest utils/tests/backend/agents/test_character_agent.py utils/tests/backend/agents/test_setting_agent.py` (plus `ruff`/`mypy` on the two agents). Once green, commit:
  `Draft From Context Docs (1/3) Complete: character/setting agents draft from docs when the seed is empty.`

### Phase 2 — Frontend: enable Draft on a seed OR a Draft-tagged doc

- **Locations:**
  - `web/frontend/components/feature/CharacterModal.tsx` — `canDraft` (L47-48).
  - `web/frontend/components/feature/SettingModal.tsx` — `canDraft` (L43-44).
  - `web/frontend/features/library/useLibraryState.ts` — `draftCharacter` (L259-265, the `if (!seed) return;` early-return) and `draftSetting` (L394-404).
  - `web/frontend/lib/readDocs.ts` — reuse `docsForDraft` (the existing `useDraft !== false` filter) for the "has a Draft-tagged doc" check; no new helper unless trivial.
  - Tests: `web/frontend/components/feature/CharacterModal.test.tsx`, `SettingModal.test.tsx` (these live under `web/frontend/features/library/` per the repo's co-located convention — confirm path at edit time), `web/frontend/features/library/useLibraryState.character.test.ts`.
- **Change:**
  - `canDraft` becomes `Boolean(seedText) || docsForDraft(d._docFiles ?? []).length > 0`.
  - `draftCharacter` / `draftSetting` drop the bare `if (!seed) return;`; instead they compute
    `docsOverview` first and bail only when *both* the trimmed seed and `docsOverview` are empty.
    The seed is still passed (possibly `""`) to `api.draftCharacter` / `api.draftSetting`, which
    already forward it; `docsOverview` is already wired.
- **Rationale:** mirrors the backend contract on the client so the button reflects what the server
  will accept, and a docs-only author can actually trigger the request.
- **A11y/responsive:** no new interactive surface — only the `disabled` predicate of an existing
  `<Button>` changes; contrast/focus/layout unchanged. Note this in the commit + checklist (live
  in-browser pass deferred per the standing shared-dir constraint; the disabled→enabled transition is
  covered by the component tests).
- **Tests:** add cases asserting the Draft button is enabled with no seed but a Draft-tagged
  `_docFiles` entry (and still disabled when the only doc has `useDraft: false`); add a hook test that
  `draftCharacter` calls `api.draftCharacter` with the concatenated doc text when the seed is empty.
- **Action:** Run `npm test` (Vitest) + `npm run typecheck` + `npm run lint` in `web/frontend`. Once
  green, commit: `Draft From Context Docs (2/3) Complete: enable Draft with Velora from a Draft-tagged context file alone.`

### Phase 3 — Docs, full validation, merge

- **Locations:** `docs/api-contract.md` (Character/Setting draft request: `seed` now optional when
  `docsOverview` is present), `docs/data-flow.md` (authoring-flow note), `docs/documentation.md`
  (status line), `docs/checklist.md` (this entry + scenario-parity follow-up), this plan file.
- **Rationale:** documentation must move with behavior (global rule); the contract change (seed no
  longer strictly required) is author-facing.
- **Action:** Run the full gate — `uv run pytest` (backend) + `npm test`/`typecheck`/`lint`
  (frontend). Record any deferred a11y item in `docs/checklist.md`. Commit:
  `Draft From Context Docs (3/3) Complete: docs + full validation.` Then merge the worktree branch
  into `main` (fast-forward/no-ff as clean), resolving any conflicts, and verify the suite stays green
  on `main`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Character agent draft-from-docs | Seed optional when docs present; docs-only prompt path | `web/backend/app/agents/character_agent.py` |
| Setting agent draft-from-docs | Same for settings | `web/backend/app/agents/setting_agent.py` |
| Backend agent tests | Empty-seed+docs succeeds; both-empty → 400 | `utils/tests/backend/agents/test_character_agent.py`, `test_setting_agent.py` |
| Modal Draft gating | `canDraft` enabled on seed OR Draft-tagged doc | `web/frontend/components/feature/CharacterModal.tsx`, `SettingModal.tsx` |
| Hook draft handlers | Don't early-return on empty seed when docs exist | `web/frontend/features/library/useLibraryState.ts` |
| Frontend tests | Button enabled with doc-only; hook sends doc text | `*/CharacterModal.test.tsx`, `SettingModal.test.tsx`, `useLibraryState.character.test.ts` |
| Docs | Contract + data-flow + status + checklist | `docs/api-contract.md`, `docs/data-flow.md`, `docs/documentation.md`, `docs/checklist.md` |
