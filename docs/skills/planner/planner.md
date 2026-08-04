# Plan Creation Reference (Mytheca)

Guidelines for generating explicit, hierarchical, phase-by-phase implementation plans for Mytheca. Save finished plans in `docs/plans/<plan-name>.md`.

## Trigger

When a user asks to "create a plan", "plan this out", or requests structured steps to solve a problem.

## Plan Structure

Output the plan in clean Markdown following the structure below.

---

### 1. Introduction

1–2 paragraphs summarizing the problem and the overall approach within Mytheca's architecture (Next.js frontend, FastAPI backend, multi-agent brain, Postgres/Redis).

> **Example:** This plan adds the live scene event stream. The goal is to deliver narrator/character beats to the UI in real time. The approach: define the NDJSON event contract in `web/shared/contracts`, expose an SSE route in the FastAPI backend, and consume it with a React hook in the Next.js story player.

---

### 2. Gaps & Unanswered Questions

- **Simple gaps:** state the most logical assumption and proceed.
- **Complex gaps:** ask explicitly and state: "Human intervention is needed to answer this question."

---

### 3. Hierarchical Step-by-Step Instructions

Detail the work sequentially. Each phase must enable the next. For each step include:

- **Locations:** exact file names, classes, and functions — use real Mytheca paths (`web/frontend/...`, `web/backend/app/...`, `utils/tests/backend/...`). Note that `web/shared/contracts/` is empty; the FE↔BE contract mirror lives in `web/frontend/lib/{events,types}.ts`.
- **Rationale:** why this step must happen here and now.
- **NO large code blocks:** name the parts/files involved, not full implementations.
- **Validation & Commit (end of every phase):**
  > *Action: Run the validation for this phase — `uv run pytest` for affected backend areas and the relevant frontend component/route tests; for web/UI changes also run an accessibility + responsive pass (keyboard, focus, contrast, 320/375/768/1024). Once green, commit locally: `[Plan Name] (Current/Total) Complete: <one sentence on what was done>`. Do not push or open a PR unless the user asks.*

> **Example:**
> #### Step 1: Add the `scene_transition` story event
> - **Locations:** `web/backend/app/events/envelope.py` (new variant on the `StoryEvent` union), `web/frontend/lib/events.ts` (the hand-maintained mirror), `web/frontend/components/feature/TranscriptBeat.tsx` (renderer).
> - **Rationale:** The envelope and its TypeScript mirror must agree before either side can stream the new beat; `docs/api-contract.md` is updated in the same step.
> - **Action:** Run validation for this phase (`uv run pytest utils/tests/backend/services`, plus `npm test` for the touched components and `npm run typecheck`). Once green, commit: `Scene Transitions (1/4) Complete: Added the scene_transition event to the envelope and its frontend mirror.`

---

### 4. Deliverables Table

After all steps, list deliverables and locations. **Tests are required** — include small, focused tests exercising the new behavior. Backend tests go under `utils/tests/backend/{api,agents,services,rag,data}/`; **frontend tests are co-located** beside the component (`Foo.tsx` → `Foo.test.tsx`), never under `utils/tests/frontend/`, which is empty by design.

> | Deliverable | Description | Location |
> | --- | --- | --- |
> | Event variant | New typed story event on the union | `web/backend/app/events/envelope.py` |
> | Emission | Engine emits it on the turn path | `web/backend/app/services/turn_engine.py` |
> | TS mirror | Hand-maintained frontend contract | `web/frontend/lib/events.ts` |
> | Renderer | Beat component for the new type | `web/frontend/components/feature/TranscriptBeat.tsx` |
> | Backend tests | Envelope + engine coverage | `utils/tests/backend/services/test_turn_engine_events.py` |
> | Frontend test | Renderer coverage, co-located | `web/frontend/components/feature/TranscriptBeat.test.tsx` |

## Conventions (locked for Mytheca)

- Granularity: full phase-by-phase plans.
- Validation: pytest (backend) + frontend component/route tests; a11y + responsive pass for web/UI.
- Git: commit per phase, no auto push/PR.
- Audience: agentic + solo implementation.
