# Velora — Architecture

## Application Mode

API + separate frontend (streaming-first). The Next.js frontend is the UI renderer; the FastAPI backend is the "brain" that runs the multi-agent system and streams story events to the UI.

## Core Architectural Principle

**The AI generates validated story events; the UI renders them. The AI never decides UI layout.**

The model emits small, typed events (one unit of story progress each), the backend validates them (including stat clamping), and the frontend maps each event type to a visual component. This keeps the frontend "dumb" and the agent framework "smart," and avoids the model returning one large blob of prose.

```
User Input → Orchestrator → Scenario State → Character/Narrator agents
→ Structured Event Output → Validator → Event Stream → Frontend Renderer
```

## Domain Model

Four canonical objects define the world; everything else hangs off them.

```
Storyline (the world, owns the baseline stat schema)
 ├── Characters (the people, each holding stat values)
 ├── Settings (the places)
 └── Scenarios (the live situations being acted out — many, ever-changing,
                may add their own stats)
```

- **Storyline** — title, genre, world setting, atmosphere/tone, history, ongoing situations, persistent world flags, and the **baseline stat definitions**. Container that owns its characters, settings, and scenarios.
- **Character** — id, display name, role, avatar/accent color, personality (traits, speech style, tone), goals, secrets, relationship values, and a **stat block** (current values, always within range). Belongs to a storyline.
- **Setting** — id, name, description, atmosphere, time/weather, who/what is present, notable features, current state. Belongs to a storyline; a scenario points at the setting it takes place in.
- **Scenario** — the live truth object: which storyline/setting it belongs to, active characters, turn order, current turn index, goals with status, tone (primary + intensity), world flags in play, and any **scenario-specific stat additions or range overrides**.
- **Story Event** — the central abstraction. Every visible thing in the chat is an event with a base envelope plus type-specific fields (see `docs/api-contract.md`).

## Rendering Model

- App shell and interactive surfaces: Next.js App Router (client + SSR as appropriate).
- Live story content: pushed from the backend over SSE/WebSocket as an NDJSON event stream and rendered incrementally — narrator cards, character bubbles, action cards, and side-panel updates.
- Static/marketing surfaces (landing, docs): static/SSG where it fits.

## Frontend Stack

Next.js (App Router), React, TypeScript, Tailwind CSS, Framer Motion. The visual language is defined in `docs/design-system.md`. Optional, adopted only when a real need appears: TanStack Query (server-state caching), TanStack Table (dense tables), React Hook Form + Zod (complex editors), Radix UI / shadcn-style copy-owned primitives (`web/frontend/components/ui/`).

## Backend Stack

FastAPI (Python 3.13, `uv`). Components:

- **Orchestrator / Director** (`app/services/`) — decides what happens next, who speaks, whether narration is needed, pacing, scenario transitions, and **what stat changes a turn's events imply** (reading each stat's guidance).
- **Event Engine** (`app/events/`, `app/services/`) — produces the NDJSON event stream.
- **State Manager** (`app/services/`, `app/models/`) — canonical source of truth for the storyline, characters, settings, the active scenario, and all stat values.
- **Validator** (`app/services/`, `app/schemas/`) — rejects invalid event types, unknown character/setting IDs, malformed JSON, impossible state changes, unauthorized knowledge leaks, and **stat changes that reference undefined stats or fall outside the defined range** (it clamps rather than crashes).
- **Agents** (`app/agents/`) — Narrator + Character agents (Orchestrator/Director above coordinates them).
- **Core** (`app/core/`) — config, Postgres/Redis clients, provider-agnostic LLM interface, config/guidance loaders (YAML + Markdown).

## Agent Roles

A multi-agent split rather than one monolithic model:

1. **Orchestrator / Director** — sequencing, pacing, scenario transitions, and implied stat changes per turn.
2. **Narrator agent** — turns resolved events into descriptive prose and reflects stat states in the world (a wounded character moves stiffly).
3. **Character agents** — each carries personality, goals, memory, relationships, secrets, emotional state, and its own stat values, which color behavior.
4. **State manager** — canonical state for storyline/characters/settings/scenario and all stat values.
5. **Validator** — enforces the event/stat contract and clamps out-of-range values.

An explicit **agent output contract** instructs the model to emit only valid structured events — every spoken line as `character_dialogue`, every description as `narration`, every movement as `character_action`, every world/stat change as `state_update`, branch options as `branch_choices` — and to never invent character/setting IDs or stat keys.

## Stat System

A **stat** is a bounded numeric value attached to a character (or, relationally, between characters) that the AI reads and updates as the story unfolds. Health, strength, trust, suspicion, morale are all the same object.

- The **Storyline** defines the baseline stat schema (key, display name, description, `min`/`max`, default, visibility, guidance file). **Scenarios** may add scenario-specific stats or tighten/override a range while active.
- Each **stat definition** points at a **Markdown guidance file** (what raises it, what lowers it, magnitude guidance, meaningful bands, and how each band should affect behavior and narration). Relevant guidance files are injected into agent context each turn.
- The **range and starting value are locked at creation** and enforced by the validator: every incoming stat change is clamped to `[min, max]`, so the AI can never push a value out of bounds.
- Stat changes ride on `state_update` events (carrying character, stat key, new value or delta, and a short **reason** — a free audit trail). A dedicated `stat_update` event can be promoted later for bespoke rendering.
- **Visibility** (`public`, `private_to_user`, `private_to_character`, `hidden`) controls what the player sees vs. what only affects agent reasoning (e.g. a hidden "suspicion" value).

See `docs/briefings/storyline-chat-briefing.md` §9 for the full stat design and `docs/api-contract.md` for the event payloads.

## User Roles & Auth

| Role | Access |
| --- | --- |
| Public | Landing/marketing, sign-up, sign-in. |
| Authenticated user | Own storylines, characters, settings, scenarios, play sessions. |
| Admin (future) | Moderation, global content management. |

Auth/session is **backend-owned** (token/session). The frontend stores credentials and guards protected routes; the backend is the source of truth and validates every request. The exact mechanism (JWT vs. session cookie, provider) is to be finalized before auth is built — tracked in `docs/checklist.md`.

## Frontend/Backend Boundary

- Frontend owns frontend routing and UX-level validation (Zod); backend owns API + streaming routes and authoritative validation (Pydantic, `app/schemas/`).
- Shared request/response and event types live in `web/shared/contracts/` and mirror `docs/api-contract.md`.
- Backend owns errors, retries, caching (Redis), the streaming lifecycle, and stat clamping; the frontend owns optimistic UI and reconnect behavior.

## Data Layer

- **PostgreSQL** — core state: users, storylines, characters, settings, scenarios, events, stat definitions, stat values.
- **Redis** — live scenario state, pub/sub for streaming, and caching.
- **Static config** — YAML for hand-authored storylines/characters/settings/stat definitions; Markdown for per-stat guidance. Loaded into the State manager / agent context.
- **Vector DB** (deferred) — semantic memory retrieval; build the memory seam behind an interface so it can be added without rewrites.

## AI Layer

LLMs via OpenAI or local models behind a provider-agnostic interface in `app/core/`. The multi-agent system composes Orchestrator/Director + Narrator + Character agents per turn, with the active scenario state, current stat values, and the relevant stat guidance files injected into context.

## Streaming Layer

SSE or WebSockets carry an **NDJSON** event stream (one JSON object per line). Two streaming modes:

- **Full events** — send only complete events; easy to validate and render. **Used for state and stat updates.**
- **Delta streaming** — `message_start` → repeated `message_delta` → `message_end`; gives a live-typing feel. **Used for visible messages** (narration, dialogue). The frontend renders deltas as they arrive, then finalizes on `message_end`.

Pipeline: `AI output → parse → validate (incl. stat clamping) → repair/retry if invalid → stream to UI`.

## Optional Later Layer: Dice-Based Resolution

How uncertain outcomes get resolved is the genuinely optional layer. Default (in scope now) is **narrative resolution**: the Director decides the outcome and stat change directly, guided by the stat files. **Dice-based resolution** (later) layers a roll-and-threshold pattern (`check_request` → `roll_result` → `consequence` → `state_update`) on top of the existing stats and ranges — dice just become the function that decides the delta. The design system already renders a "check" card for this.

## Key Decisions Log

- Event-driven model: AI emits validated typed events; UI renders. Five event types to start.
- Domain model: Storyline / Character / Setting / Scenario + Story Event + Stat system.
- "Everything under `web/`" layout with root `app.py` backend entrypoint.
- `uv`-only Python tooling, Python 3.13.
- Format split: YAML config · Markdown stat guidance · JSON/NDJSON streaming · JSON Schema/Zod validation.
- Provider-agnostic LLM interface from day one.
- Dice-based resolution and Vector DB semantic memory deferred; design seams only.
