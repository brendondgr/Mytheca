---
name: website-architecture
description: Use this skill when planning, scaffolding, restructuring, or documenting Mytheca's web surface — its locked Next.js + FastAPI stack, route map, real-time event streaming boundary, data flow, and the design-quality gate that must pass before UI is built.
---

# Mytheca Website Architecture

This skill owns the structural phase that happens before UI code is generated. It sits between `repository-structure` and `ui-frontend`. For Mytheca the high-level stack is **already decided** (below); use this skill to keep the route map, data flow, frontend/backend boundary, and design-quality brief current — not to re-pick the framework.

All web code lives under `web/` (`web/frontend`, `web/backend`, `web/shared`). Documentation lives under `docs/`. Pair this skill with `ui-frontend`, `accessibility-mobile`, and `ada-compliance`.

## Core Rule

Do not generate isolated visual pages until routes, data flow, the streaming contract, and the design-quality requirements are defined and recorded in `docs/`.

## Locked Stack (Mytheca)

- **Application mode:** API + separate frontend, streaming-first.
- **Frontend:** Next.js 16 (App Router, Turbopack), React 19, **TypeScript**, Tailwind CSS v4, Framer Motion 12, `react-force-graph-2d`. Mostly a client/SSR app shell with streamed content.
- **Backend:** FastAPI (Python 3.13, `uv`), launched from root `app.py`. Owns the turn loop, agents, events, and persistence.
- **Data:** PostgreSQL (core state) · Redis (live turn state) · **Neo4j 5.26** (Story Graph, **implemented**) · **Qdrant + fastembed** (hybrid RAG, **implemented**). The last three are best-effort and degrade to no-ops — but they exist, so don't write "leave a seam for a vector DB".
- **AI:** one OpenAI-compatible proxy serving cloud OpenAI, vLLM, and llama.cpp.
- **Streaming:** **NDJSON returned directly in the turn POST response** (`POST /api/play/{scenarioId}/turn`). There is no SSE endpoint and no WebSocket for story events; a separate `GET /stream` with pub/sub fan-out remains an unbuilt seam. (ComfyUI image generation does use a WebSocket, but that is a backend↔ComfyUI detail, not the story transport.)

Any addition beyond this stack must have a defined job recorded in `docs/architecture.md` and `docs/workflow.md`. Avoid overlapping libraries — two routers, two form libs, two animation systems.

### Libraries deliberately NOT installed

Native HTML plus hand-written accessible behavior has covered every need so far. None of these are present, and adding one needs a real justification:

- **No headless component library** (Radix / shadcn). Focus traps, roving tabindex, and listbox semantics are hand-written in `components/ui/`.
- **No TanStack Query** — the API client is a hand-rolled `fetch` in `lib/api.ts` using await-then-apply.
- **No TanStack Table** — `DocumentsTable` is hand-built.
- **No React Hook Form / Zod** — editors manage draft state directly.
- **No GSAP.** Framer Motion is the animation system.

## Frontend/Backend Boundary

- **Routing:** Next.js owns frontend routing; FastAPI owns API + streaming routes, all mounted under `/api`.
- **Auth/session:** **does not exist.** No user model, no auth routes, no session or token handling. Nothing is gated. The mechanism is undesigned — see `docs/checklist.md`. Do not write code or docs that assume a current user.
- **Validation:** the backend validates with Pydantic (`web/backend/app/schemas/`) and is the source of truth. The frontend does light UX-level checks inline; there is no Zod.
- **Contracts:** `web/shared/contracts/` is **empty**. The live TypeScript mirror is hand-maintained in `web/frontend/lib/events.ts` and `lib/types.ts` against `web/backend/app/events/envelope.py`. Changing the envelope means updating the mirror and `docs/api-contract.md` in the same change.
- **Errors/retries/caching/optimistic updates:** defined per endpoint in `docs/api-contract.md`. Library CRUD is await-then-apply; optimistic UI is reserved for turn submission.

## Required Outputs (keep current in docs/)

1. Application mode & rendering model → `docs/architecture.md`
2. Route map → `docs/routes.md`
3. Data-flow map (including the streaming/event path) → `docs/data-flow.md`
5. Component ownership → `docs/component-map.md`
6. API + event contract → `docs/api-contract.md`
7. Design-system & anti-generic brief → `docs/design-system.md`
8. Deployment & env → `docs/deployment.md`
9. Directory layout → `docs/structure.md`
10. Build/run/test/lint/format commands → `docs/workflow.md`

## Route Map Rules

For every route/page record: path, file, purpose, data dependencies, backend endpoints used, and the loading / empty / error / partial-data / success / mobile states. See `docs/routes.md`.

**Only document routes that exist.** `docs/routes.md` previously listed eight routes — auth, admin, per-entity editors — that were never built and never scheduled; that made the whole file untrustworthy. If a route is planned but unbuilt, it belongs in `docs/checklist.md`, not the route map.

## Data Flow Rules

Document where each piece of data originates and how it moves: static content, PostgreSQL records, Redis live state, third-party/LLM APIs, server-rendered context, client-only state, derived/cached data, and **streaming/real-time updates** (the NDJSON event stream is first-class here). See `docs/data-flow.md`.

## Design-Quality Planning Gate

Before UI implementation, `docs/design-system.md` must define: Mytheca's visual motif (the illuminated manuscript), the color/type/radius/shadow/icon/spacing rules for all three themes, the real narrative artifacts shown near the top of key pages (a live scene, a narrator card, a cast rail — not abstract orbs), at least one Mytheca-specific layout decision, and the required UI states (loading, empty, error, partial-data, success, mobile, reduced-motion).

Copy uses the **actual domain vocabulary**: storyline, scenario, character, setting, cast, beat, turn, stat, narrator. Not "scene" as a top-level object — that model was replaced by Storyline/Scenario and no `Scene` entity exists.

UI must follow `ui-frontend/ui/design-quality.md`. Remove generic AI-site patterns (vague productivity copy, glowing gradients, fake metrics, abstract orbs, repeated identical card grids) unless Mytheca specifically justifies them.
