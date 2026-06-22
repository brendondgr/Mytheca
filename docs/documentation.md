# Velora — Project Documentation

## Purpose

Velora is an AI-driven, multi-character roleplay chat engine. Characters converse with one another while roleplaying inside a living world; the user directs how the conversation flows and can also play as a character. A persistent **Narrator** describes the situation and environment alongside character dialogue, so the central chat reads like a scene rather than a flat message thread.

The story is driven by a multi-agent backend that emits **small, typed story events** — the AI generates validated events and the UI renders them; the AI never decides UI layout. A near-term **character stat system** (bounded, guided numeric values that shape outcomes) gives the world continuity and consequence. Dice-based resolution is treated as an optional later layer.

**Core domain objects:** Storyline, Character, Setting, Scenario — plus the **Story Event** abstraction and the **Stat** system.

- **Storyline** — the overarching world and its persistent truth; owns the baseline **stat schema** and holds its characters, settings, and scenarios.
- **Character** — a person in the storyline: descriptive (personality, speech, goals, secrets, relationships) and numeric (a stat block of current values).
- **Setting** — a place within the storyline, tracked over time (who's there, state, time/weather, features).
- **Scenario** — the live "truth object" for the present moment: active characters, turn order, goals, tone, world flags, and any scenario-specific stat additions/overrides. The model generates *from* this and emits events that *update* it.

## Tech Stack

| Layer | Choice |
| --- | --- |
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS, Framer Motion |
| Backend | FastAPI (Python 3.13, `uv`), served via `python app.py backend` |
| Brain | Orchestrator/Director · Narrator · Character agents · State manager · Validator |
| Core data | PostgreSQL (storylines, characters, settings, scenarios, events, stat values) |
| Live/cache | Redis (active scenario state, stream pub/sub, caching) |
| Static config | YAML (storylines, characters, settings, stat definitions) |
| Stat guidance | Markdown (one human-readable file per stat, injected into agent context) |
| Validation | JSON Schema / Zod (parse → validate → repair/retry; enforces stat ranges) |
| Semantic memory | Vector DB — **deferred (design seam only)** |
| AI | LLMs via OpenAI or local models, behind a provider-agnostic interface |
| Streaming | SSE / WebSockets carrying an **NDJSON** event stream |
| UI renderer | Narrator cards, character bubbles, action cards, side panels (stats, turn order, branch choices) |

## Architecture Summary

```
User Input → Orchestrator → Scenario State → Character/Narrator agents
→ Structured Event Output → Validator (incl. stat clamping) → Event Stream → Frontend Renderer
```

```
Frontend (Next.js/React/TS/Tailwind/Framer Motion)
        ↓  HTTP + SSE/WebSocket (NDJSON events)
Backend "Brain" (FastAPI): Orchestrator/Director · Narrator · Character · State manager · Validator
        ↓
Data: PostgreSQL (core) · Redis (live scenario) · [Vector DB]  ← bracketed = deferred
        ↓
AI: LLMs (OpenAI / local) · multi-agent · YAML config + Markdown stat guidance injected per turn
```

The frontend and backend both live under `web/`; a thin root `app.py` runs the FastAPI backend. See `docs/architecture.md` for route/auth/data-flow detail, `docs/structure.md` for the layout, and `docs/design-system.md` for the visual language.

## Major Decisions

- **Domain model:** four canonical objects (Storyline / Character / Setting / Scenario) + a Story Event abstraction + a Stat system. Replaces the earlier flat "scene" model.
- **Event-driven rendering:** the AI emits small typed events; the backend validates them; the frontend maps each event type to a component. Start with **five** event types (`narration`, `character_dialogue`, `character_action`, `state_update`, `branch_choices`).
- **Stat system (near-term):** bounded numeric values defined on the storyline (and optionally tightened by a scenario), held per character, **clamped by the validator**, with a Markdown guidance file per stat injected into agent context. Relationship/mood values are the same object with a relational target.
- **Format split:** YAML for hand-authored config, Markdown for stat guidance, JSON/NDJSON for live streaming, JSON Schema/Zod for validation.
- **Repo layout:** "everything under `web/`" — `web/frontend` (Next.js) + `web/backend` (FastAPI) + `web/shared/contracts`. Root `app.py` is the backend entrypoint.
- **Python tooling:** `uv` only, Python 3.13.
- **Agent tools supported:** Claude Code, OpenAI Codex, Cursor. Canonical instructions live in `docs/skills/`; agent folders only point to them.
- **Git workflow:** commit per phase (no auto push/PR unless requested).
- **Validation gate:** pytest (backend) + frontend component/route tests; web/UI changes also require an accessibility + responsive pass.
- **Deferred capabilities:** dice-based resolution (optional later layer) and a Vector DB for semantic memory — designed for with seams, not yet implemented.

## Selected Skills

`global-project-rules` (mandatory), `repository-structure`, `website-architecture`, `ui-frontend`, `accessibility-mobile`, `ada-compliance`, `planner`. All under `docs/skills/`.

## Current Status

Repository initialized: docs, canonical skills, agent pointers, and a structural skeleton (directories + config stubs) are in place. The product concept and data model are captured in `docs/briefings/storyline-chat-briefing.md` and reflected across these docs. Application code (Next.js app, FastAPI app, DB integration, agents, stat system) is **not yet implemented** — that is the next step. Open items are tracked in `docs/checklist.md`.
