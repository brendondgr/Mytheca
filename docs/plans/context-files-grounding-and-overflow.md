# Context Files — Assistant Grounding & Panel Overflow

## 1. Introduction

Two defects on the **New Storyline** page (`/storylines/new`, `StorylineCreatorView`)
make the Context Files column both ineffective and disruptive.

**Problem 1 — uploaded documents never reach the assistant.** The storyline
create/edit agent stream (`POST /api/storylines/agent/create/stream` and
`…/{id}/agent/edit/stream`) carries only `scope`, `messages`, and `fields`. The
author's dropped reference files live entirely in `useStorylineCreator`'s `docs`
state and are used by exactly one call — `generateWorldPrimer`. So when the author
asks the Assistant for a title, genre, tagline, premise, World Primer, or stats, the
model has never seen the uploaded material. Compounding it, a freshly-dropped file
lands with `useDraft: false` (`toCreatorDoc`), so even the primer path ignores it
unless the author hand-toggles every row. The fix threads a bounded `docsOverview`
grounding block through the existing agent request → `core.converse` → system prompt
(reusing `agents/_common.docs_block`, already used by `storyline_agent`), flips the
Draft default ON, and adds a bulk Draft toggle.

**Problem 2 — the panel inflates the page by thousands of pixels.** Verified live at
1280×720 and 375×812 with 28 files: `document.documentElement.scrollHeight` reaches
**6212px** against a 720px viewport, and scrolling pushes `main` to `top: -2000px`,
i.e. blank space. The cause is not the panel's own overflow — its list already scrolls
internally (`clientHeight 433 / scrollHeight 6119`). Each `DocRow` renders a
`<label className="sr-only">` for its category `<select>`; Tailwind's `sr-only` is
`position: absolute`, and with **no positioned ancestor** its containing block is the
*initial containing block*. Absolutely-positioned boxes are not clipped by an
`overflow: hidden` ancestor that is not in their containing-block chain, so all 56
labels escape `main`'s `overflow-hidden` and grow the **root** scroller to the full
un-scrolled list height. Making the scroll container a containing block
(`position: relative`) collapses `scrollHeight` back to the viewport — confirmed
empirically at both widths.

## 2. Gaps & Unanswered Questions

- **Does Draft-on-by-default blow the context budget?** With 28 files it could. It is
  bounded twice — `concatDocs` caps at `DOCS_CHAR_CAP = 32000` and the backend
  `docs_block` re-caps at `DOCS_CAP = 32000` — and the page already shows a live
  `ContextBudgetMeter`. Assumption: honour the request (all files selected by default),
  rely on the existing caps + meter, and give the author a one-click bulk de-select.
  No human intervention needed.
- **Should the edit-mode assistant also receive the docs?** Yes — the same panel is
  present on `/storylines/[id]/edit` and the surprise is identical there. The field is
  optional on the request, so edit mode is a pass-through with no contract fork.
- **Is `useRag` / `useExtract` in scope?** No. The report names the *draft* checkbox.
  `useRag` keeps its existing default (ON) and `useExtract` stays opt-in OFF.
- **Should the `sr-only` fix be global?** Scoped, not global. The fix lands on the two
  containers that host the long list (`TriagePanel`'s scroller and the creator `main`),
  so the panel is safe wherever it is embedded. A repo-wide sweep for the same
  `sr-only`-escapes-clipping pattern is recorded in `docs/checklist.md` instead of
  being bundled here.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Contain the panel's absolutely-positioned descendants

#### Step 1.1: Make the context-file scroller a containing block
- **Locations:** `web/frontend/components/feature/TriagePanel.tsx` — the scrollable
  body `<div>` (the `overflow-y-auto` sibling of the sticky header) gains `relative`;
  `web/frontend/features/library/StorylineCreatorView.tsx` — the `<main>` shell gains
  `relative` as a page-level belt so no other stray absolute descendant can inflate the
  root scroller.
- **Rationale:** `position: relative` on the scroller makes it the containing block for
  every `sr-only` label inside it, which brings those boxes back under the scroller's
  own `overflow-y: auto` clipping. This is the minimal change that removes the phantom
  page height at every breakpoint, and it fixes the panel as a component rather than
  only on this one route.

#### Step 1.2: Regression test
- **Locations:** `web/frontend/components/feature/TriagePanel.test.tsx` — a new case
  asserting the scrolling body carries both `overflow-y-auto` and `relative` (jsdom has
  no layout, so the invariant is asserted structurally, with the live measurement
  recorded here and in the commit message).
- **Action:** Run `npm test -- TriagePanel` and `npm run typecheck` in `web/frontend`.
  Re-measure live at 1280×720 and 375×812 with 28 files: `documentElement.scrollHeight`
  must equal `clientHeight`. Once green, commit:
  `[Context Files] (1/4) Complete: Contained the context-file list's sr-only labels so the page no longer grows by thousands of blank pixels.`

### Phase 2 — Draft on by default + a bulk Draft toggle

#### Step 2.1: Flip the Draft default
- **Locations:** `web/frontend/features/library/storylineCreator.ts` — `toCreatorDoc`
  defaults `useDraft` to `true`; `web/frontend/components/feature/TriagePanel.tsx` —
  the `uploadUses` initial state sets `useDraft: true`; update the doc comments on both
  (and on `ReadDoc.useExtract`'s neighbours in `web/frontend/lib/readDocs.ts` where the
  default is described).
- **Rationale:** The report's "all context files should be selected by default" is the
  precondition for Phase 3 to be useful — grounding that defaults to empty is grounding
  the author never sees.

#### Step 2.2: Add the De-select All / Re-select All toggle
- **Locations:** `web/frontend/components/feature/TriagePanel.tsx` — a new control row
  above the doc list showing the Draft count (`n/N`) and one button that reads
  **De-select All** while any doc has Draft on and **Re-select All** when none do;
  `web/frontend/features/library/useStorylineCreator.ts` — a new `setAllDocUse(key,
  value)` action; `StorylineCreatorView.tsx` wires it through as `onSetAllUse`.
- **Rationale:** A single stateful toggle is what was asked for, and with 28 rows the
  per-row toggles are unusable. Keeping the mutation in the hook (not the panel) matches
  how every other doc mutation is owned.

#### Step 2.3: Tests
- **Locations:** `web/frontend/features/library/storylineCreator.test.ts` (default),
  `web/frontend/features/library/useStorylineCreator.test.ts` (`setAllDocUse`),
  `web/frontend/components/feature/TriagePanel.test.tsx` (label flip + click).
- **Action:** Run `npm test` in `web/frontend` plus `npm run typecheck && npm run lint`.
  Keyboard + focus pass on the new button (native `<button>`, visible focus ring, AA
  contrast on the existing tokens). Once green, commit:
  `[Context Files] (2/4) Complete: Context files default to Draft-on with a bulk De-select All / Re-select All toggle.`

### Phase 3 — Thread the selected documents into the assistant

#### Step 3.1: Accept the grounding on the agent request (backend)
- **Locations:** `web/backend/app/schemas/storyline_edit.py` —
  `StorylineAgentRequest` gains `docs_overview: str = ""` (wire `docsOverview`);
  `web/backend/app/routes/storylines.py` — both stream endpoints pass it to their agent;
  `web/backend/app/agents/storyline_edit/creation.py` and `editor.py` — accept and
  forward `docs_overview`; `web/backend/app/agents/storyline_edit/core.py` —
  `converse` folds it into `_build_system` via the existing
  `app.agents._common.docs_block`.
- **Rationale:** `docs_block` already exists, is already bounded by `DOCS_CAP`, and is
  already the phrasing used by `storyline_agent`'s primer/draft path — so the assistant
  sees the uploaded material described exactly the way the rest of the authoring surface
  describes it. Optional-with-default keeps the endpoint backward compatible.

#### Step 3.2: Send the grounding from the page (frontend)
- **Locations:** `web/frontend/lib/api.ts` — `StorylineAgentBody` gains optional
  `docsOverview`; `web/frontend/features/library/useStorylineAgent.ts` — a new
  `getDocsOverview?: () => string | undefined` option, read per turn like `getFields`;
  `web/frontend/features/library/useStorylineCreator.ts` — expose the existing
  `draftGrounding(docs)` result as `docsOverview`;
  `web/frontend/features/library/StorylineCreatorView.tsx` — wire it into
  `useStorylineAgent`.
- **Rationale:** Reading it per turn (not per render) means a file dropped mid-conversation
  is picked up on the next message, matching how `fields` already behaves.

#### Step 3.3: Tests
- **Locations:** `utils/tests/backend/agents/test_storyline_edit_agent.py` (the system
  prompt contains the doc text when `docs_overview` is set),
  `utils/tests/backend/api/test_storyline_agent_stream.py` (the route accepts and
  forwards `docsOverview`), `web/frontend/features/library/useStorylineAgent.test.ts`
  (the request body carries `docsOverview`),
  `web/frontend/features/library/useStorylineCreator.test.ts` (only Draft-selected docs
  are concatenated).
- **Action:** Run `uv run pytest utils/tests/backend/agents utils/tests/backend/api`
  then the full `uv run pytest`, plus `npm test` in `web/frontend`. Once green, commit:
  `[Context Files] (3/4) Complete: Draft-selected context files ground the storyline create/edit assistant end to end.`

### Phase 4 — Documentation, full gate, merge

#### Step 4.1: Update the docs in the same change
- **Locations:** `docs/api-contract.md` (the `docsOverview` field on both agent
  streams), `docs/data-flow.md` (where the uploaded corpus enters the authoring
  prompt), `docs/component-map.md` (TriagePanel's new bulk control),
  `docs/checklist.md` (record the repo-wide `sr-only`-inside-a-clipper sweep as open).
- **Rationale:** The global rules require docs to move in the same change as behavior.

#### Step 4.2: Full validation gate + merge
- **Action:** `uv run pytest` (all), `npm test` + `npm run typecheck` + `npm run lint`
  in `web/frontend`, and a live accessibility/responsive pass at 320/375/768/1024 on
  `/storylines/new` with a large file set. Then merge the branch into `main` and commit:
  `[Context Files] (4/4) Complete: Documented the docsOverview contract and the panel fix; full gate green.`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Overflow fix | Scroller + page shell become containing blocks so `sr-only` labels stop inflating the root scroller | `web/frontend/components/feature/TriagePanel.tsx`, `web/frontend/features/library/StorylineCreatorView.tsx` |
| Draft default | Freshly-dropped docs land Draft-on | `web/frontend/features/library/storylineCreator.ts`, `web/frontend/components/feature/TriagePanel.tsx` |
| Bulk toggle | De-select All / Re-select All for Draft | `web/frontend/components/feature/TriagePanel.tsx`, `web/frontend/features/library/useStorylineCreator.ts` |
| Request field | `docsOverview` on the create + edit agent streams | `web/backend/app/schemas/storyline_edit.py`, `web/backend/app/routes/storylines.py` |
| Prompt grounding | Selected docs folded into the agent system prompt | `web/backend/app/agents/storyline_edit/{core,creation,editor}.py` |
| TS mirror + wiring | `docsOverview` on the client body, read per turn | `web/frontend/lib/api.ts`, `web/frontend/features/library/{useStorylineAgent,useStorylineCreator,StorylineCreatorView}.tsx` |
| Backend tests | Prompt grounding + route pass-through | `utils/tests/backend/agents/test_storyline_edit_agent.py`, `utils/tests/backend/api/test_storyline_agent_stream.py` |
| Frontend tests | Containment, default, bulk toggle, request body | `web/frontend/components/feature/TriagePanel.test.tsx`, `web/frontend/features/library/{storylineCreator,useStorylineCreator,useStorylineAgent}.test.ts` |
| Docs | Contract, data flow, component map, checklist | `docs/api-contract.md`, `docs/data-flow.md`, `docs/component-map.md`, `docs/checklist.md` |
