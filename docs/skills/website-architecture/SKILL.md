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

- **Application mode:** API + separate frontend (Mode G), real-time/streaming-first.
- **Frontend:** Next.js (App Router), React, **TypeScript**, Tailwind CSS, Framer Motion. Rendering: mostly client/SSR app shell with streamed content; static where it fits (marketing/landing).
- **Backend:** FastAPI (Python, `uv`), launched from root `app.py`. Owns the multi-agent brain, rules, events, and persistence.
- **Data:** PostgreSQL (core state), Redis (live/cache). Vector DB (semantic memory) + Neo4j (advanced KG) are planned later — leave seams, don't build yet.
- **AI:** LLMs via OpenAI or local, behind a provider-agnostic interface.
- **Streaming:** SSE / WebSockets carrying an **NDJSON event stream**; the UI renders chat, narrator cards, side panels, and graph visualizations from those events.

Any addition beyond this stack must have a defined job and be recorded in `docs/architecture.md` (purpose) + `docs/workflow.md` (commands). Avoid overlapping libraries (e.g. two routers, two form libs, two animation systems).

### Optional libraries — adopt only by job

- Data/server-state caching for API-heavy views → TanStack Query (when needed).
- Dense tabular data → TanStack Table (when a real table appears).
- Complex forms (character/scene editors) → React Hook Form + Zod.
- Component primitives → native HTML first; Radix UI / shadcn-style copy-owned components when accessible headless behavior is needed (keep copied components in `web/frontend/components/ui/`).

## Frontend/Backend Boundary

- **Routing:** Next.js owns frontend routing; FastAPI owns API + streaming routes.
- **Auth/session:** owned by the backend (token/session); the frontend stores and sends credentials and guards protected routes. Define the exact mechanism in `docs/architecture.md` before building auth.
- **Validation:** backend validates with Pydantic schemas (`web/backend/app/schemas/`); the frontend validates input with Zod for UX but trusts the backend as source of truth.
- **Contracts:** shared request/response and event types live in `web/shared/contracts/`; keep them in sync with `docs/api-contract.md`.
- **Errors/retries/caching/optimistic updates:** define per endpoint in `docs/api-contract.md`.

## Required Outputs (keep current in docs/)

1. Application mode & rendering model → `docs/architecture.md`
2. Route map → `docs/routes.md`
3. User role & auth map → `docs/architecture.md`
4. Data-flow map (including the streaming/event path) → `docs/data-flow.md`
5. Component ownership → `docs/component-map.md`
6. API + event contract → `docs/api-contract.md`
7. Design-system & anti-generic brief → `docs/design-system.md`
8. Deployment & env → `docs/deployment.md`
9. Directory layout → `docs/structure.md`
10. Build/run/test/lint/format commands → `docs/workflow.md`

## Route Map Rules

For every route/page record: path, purpose, required auth level, data dependencies, primary page/layout/components, backend endpoints used, and the loading / empty / error / partial-data / success / permission states. See `docs/routes.md`.

## Data Flow Rules

Document where each piece of data originates and how it moves: static content, PostgreSQL records, Redis live state, third-party/LLM APIs, server-rendered context, client-only state, derived/cached data, and **streaming/real-time updates** (the NDJSON event stream is first-class here). See `docs/data-flow.md`.

## Design-Quality Planning Gate

Before UI implementation, `docs/design-system.md` must define: Mytheca's specific visual motif, color/type/radius/shadow/icon/spacing rules, the real narrative artifacts shown near the top of key pages (a live scene, a narrator card, an event timeline — not abstract orbs), concrete domain vocabulary for copy (scene, character, event, memory, beat), at least one Mytheca-specific layout decision, and the required UI states (loading, empty, error, partial-data, success, permission, mobile, reduced-motion).

UI must follow `docs/skills/ui-frontend/ui/design-quality.md`. Remove generic AI-site patterns (vague productivity copy, glowing gradients, fake metrics, abstract orbs, repeated identical card grids) unless Mytheca specifically justifies them.

## Setup Questionnaire

The original architecture questionnaire is preserved in [SETUP.md](SETUP.md) for re-planning new surfaces; most answers are already captured in the locked stack and the `docs/` files above.
