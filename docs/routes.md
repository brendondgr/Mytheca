# Velora — Route Map

Planned routes for the Next.js frontend. Routes are not yet implemented; this is the agreed map. Update it whenever a route is added or changed. For each route: path, purpose, auth, data, ownership, backend endpoints, and required UI states.

> Auth legend: **Public** (no session), **User** (authenticated), **Admin** (future high-permission).

## Frontend Routes

| Path | Purpose | Auth | Data dependencies | Primary ownership | Backend endpoints | States to design |
| --- | --- | --- | --- | --- | --- | --- |
| `/` | Landing / product intro with a real scene/narrator-card sample | Public | Static | `app/(marketing)/page.tsx` | — | loading, mobile |
| `/sign-in`, `/sign-up` | Auth | Public | — | `app/(auth)/...` | `POST /auth/*` | loading, error, success |
| `/dashboard` | User home: recent scenes, characters | User | Postgres (scenes, characters) | `app/(app)/dashboard` | `GET /scenes`, `GET /characters` | loading, empty, error, permission, mobile |
| `/characters` | List/manage characters | User | Postgres | `features/characters` | `GET/POST/PATCH/DELETE /characters` | loading, empty, error, mobile |
| `/characters/[id]` | Character editor | User | Postgres | `features/characters` + `components/feature` | `GET/PATCH /characters/{id}` | loading, error, partial-data, success, permission |
| `/scenes` | List/manage scenes | User | Postgres | `features/scenes` | `GET/POST /scenes` | loading, empty, error, mobile |
| `/scenes/[id]` | Scene editor / setup | User | Postgres | `features/scenes` | `GET/PATCH /scenes/{id}` | loading, error, success, permission |
| `/play/[sceneId]` | **Story player** — live, streamed scene | User | Postgres + Redis + event stream | `features/story-player` + `components/feature` (narrator cards, side panels) | `POST /play/{sceneId}/turn`, `GET /stream/{sessionId}` (SSE/WS) | loading, empty, **streaming/partial**, stalled-stream, reconnect, error, permission, mobile, reduced-motion |
| `/graph/[sceneId]` | Knowledge/relationship graph view (planned with graph DB) | User | Postgres (+ Neo4j later) | `features/graph` | `GET /graph/{sceneId}` | loading, empty, error, **accessible text alternative**, mobile |
| `/settings` | Account & preferences | User | Postgres | `app/(app)/settings` | `GET/PATCH /me` | loading, error, success |
| `/admin/*` | Moderation/management (future) | Admin | Postgres | `app/(admin)` | `GET /admin/*` | permission, empty, error |

## Notes

- The **story player** (`/play/[sceneId]`) is the core surface: it consumes the NDJSON event stream and renders chat turns + narrator cards + side panels. Its streaming and reconnect states are mandatory, not optional.
- Protected routes redirect logged-out users to `/sign-in`.
- Every page needs a unique, descriptive `<title>` and a logical heading hierarchy (see `docs/skills/ada-compliance/SKILL.md`).
