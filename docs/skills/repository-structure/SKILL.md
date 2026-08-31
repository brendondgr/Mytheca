---
name: repository-structure
description: Use this skill when adding files, restructuring, or enforcing Mytheca's repository layout — the web/ split (Next.js frontend + FastAPI backend), the root app.py launcher, test placement, and the docs/ source of truth.
---

# Mytheca Repository Structure Standard

Where a new file goes, and why. Paired with `website-architecture` (routes, stack, data flow) and `ui-frontend` (component work).

`docs/` is the documentation source of truth. All runtime code lives under `web/`. The root `app.py` launches **both** sides and owns the Docker data stores.

The authoritative tree lives in `docs/structure.md` — read it rather than duplicating it here. This skill covers the rules for placing things.

## Ownership Rules

| What you're adding | Where it goes |
| --- | --- |
| A page or route | `web/frontend/app/` (thin), with logic in `features/<module>/` |
| Route-level state + composition | `web/frontend/features/` — currently `story-player/`, `library/`, `options/`, `documents/` |
| Domain UI (cards, rails, modals, panels) | `web/frontend/components/feature/` |
| A reusable, domain-agnostic primitive | `web/frontend/components/ui/` |
| App chrome (shell, header, providers) | `web/frontend/components/layout/` |
| A shared React hook | `web/frontend/hooks/` |
| A frontend helper or API call | `web/frontend/lib/` |
| An API or streaming endpoint | `web/backend/app/routes/` |
| An LLM agent | `web/backend/app/agents/` |
| Orchestration, persistence, or integration glue | `web/backend/app/services/` |
| A DB model | `web/backend/app/models/` (+ an Alembic migration if non-additive) |
| A Pydantic request/response schema | `web/backend/app/schemas/` |
| RAG pipeline code | `web/backend/app/rag/` |
| Redis-backed live state | `web/backend/app/memory/` |
| Event envelope or stream code | `web/backend/app/events/` |
| Config, DB/Redis/Neo4j/Qdrant clients, preflight | `web/backend/app/core/` |
| Authored content (stat guidance, type catalogue) | `web/backend/app/content/` |
| A standalone dev/ops script | `utils/scripts/` |
| A ComfyUI workflow JSON | `utils/workflows/` |
| A backend test | `utils/tests/backend/{api,agents,services,rag,data}/test_<behavior>.py` |
| A frontend test | **Co-located** next to the file it tests (`Foo.tsx` → `Foo.test.tsx`) |
| Design tokens / visual decisions | `web/frontend/styles/themes.css` + `docs/design-system.md` |
| A plan or handoff | `docs/plans/<feature-name>.md` |

## Placement rules that are easy to get wrong

- **Frontend tests are co-located, not centralized.** `utils/tests/frontend/` contains only an `__init__.py` and must stay empty. All 84 frontend test files sit beside their subjects.
- **Backend tests have five area folders**, not three: `api/`, `agents/`, `services/`, `rag/`, `data/`.
- **`web/shared/contracts/` is empty.** The FE↔BE contract is hand-mirrored in `web/frontend/lib/events.ts` and `lib/types.ts`. Don't document it as a live source; if you change `app/events/envelope.py`, update the mirror in the same change.
- **There is no `libs/`.** It existed as an empty placeholder until 2026-08-31 and was removed — a directory reserved for ten weeks and never used is a note, not a directory. Shared helpers live in `utils/`; if something genuinely outgrows that, create the package then.
- **Neo4j and Qdrant are implemented**, not future seams. Graph code lives in `services/graph_{reader,writer}.py` and `services/type_registry.py`; RAG lives in `app/rag/`. Don't write "leave a seam for a vector DB" — it's built.
- **Media output** goes to `MEDIA_DIR` (default `<repo>/media`), is gitignored, and is served read-only at `/media`.

## General Rules

- Max file length 800 lines (aim under 500). Split when a file grows past its job.
- Python sub-packages need `__init__.py`.
- `uv` is the only Python package manager.
- **Keep `docs/structure.md` updated whenever the tree changes.** This is mandatory, not optional.
- Delete a worktree when its branch merges.
