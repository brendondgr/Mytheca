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

Repository initialized: docs, canonical skills, agent pointers, and a structural skeleton (directories + config stubs) are in place. The product concept and data model are captured in `docs/briefings/storyline-chat-briefing.md` and reflected across these docs. The **Next.js frontend** is scaffolded with the Library front page and the story player on in-memory seed data; the Library now centers on the **Storyline** object — a header storyline switcher plus three open columns (Scenarios · Characters · Settings) with cross-column highlighting. The **FastAPI app + Postgres data layer** are implemented (CRUD for the four core objects, the stat seam, the Options menu + LLM proxy). A **ComfyUI image-generation client** (`web/backend/app/services/comfyui.py`) drives a local Comfy server end-to-end (status → load/build/queue → WebSocket wait → history → download), configured from the Options menu's **Image Generation** tab; see `docs/comfyui-image-generation.md`. The **first agent has landed**: a creation-time **storyline authoring agent** (`web/backend/app/agents/storyline_agent.py`) drafts storyline metadata from a one-sentence seed and generates the agent-facing **World Primer** (stored on the storyline alongside `premise`, editable in the create modal); dropped reference files ground a single generation only and are *not* persisted (the retrieval/RAG layer is a later plan). An **agentic Character Creator** now mirrors that flow for characters (`web/backend/app/agents/character_agent.py` + `web/frontend/components/feature/CharacterModal.tsx`): from a seed (optionally grounded in the world + dropped docs) it drafts a character's **base identity** — role, traits, voice, goal, secret, plus **appearance / background / personality** (new nullable Character columns) — proposes **starting stats** keyed to the storyline's stat schema (review/adjust → applied on save), and, opt-in, renders a **watercolor profile portrait** through the ComfyUI pipeline (PNG→**WebP** via Pillow, saved under `MEDIA_DIR`, served at `/media`, shown as the avatar with a monogram fallback). This is the **preparation phase for the character knowledge graph** (`Documents/Plans/3.character-graph-structure-prep.md`): it produces §1 *node properties* only — **no graph** (edges, secret nodes, Neo4j) is built. The **universal stat system is now authorable in the UI**: the Storyline editor defines the world's shared stats (used by every character) with **labeled bands ("tickers")** that name what value ranges *mean* (e.g. Health 0–20 = "nearly dead", 81–100 = "very healthy") — stats are freely add/edit/removable (delete prunes character values), and the bands feed the Character creator's band-aware stat proposal and future state-extraction. The storyline **seal** moved into a dedicated pop-up (`SealModal`) with an expanded shape set + a custom color wheel; the per-character accent palette grew to **12** colors. An **agentic Setting Creator** now mirrors the character/storyline flow (`web/backend/app/agents/setting_agent.py` + `web/frontend/components/feature/SettingModal.tsx`, extracted out of the generic `EntityModal` so it now owns scenarios only): from a seed (optionally grounded in the world + dropped docs) it drafts a setting's **base description + current state** — the §4.1 Setting-node metadata of `Documents/Plans/4.story-graph-structure-prep.md` (new nullable `atmosphere` / `features` / `current_state` columns, alongside `desc`) — and, opt-in, renders a watercolor **establishing image** through the ComfyUI pipeline (WebP under `/media/scenes`, shown on the setting card). The §4.1 **event timeline** ships as an empty, play-accrued seam (a `timeline` column + a read-only modal note) — this is the **preparation phase for the Setting node**: §4.1 *node properties* only, **no graph** (edges, Event/Faction nodes, Neo4j). The streaming story engine and the in-scene stat-panel UI remain **not yet implemented**. Open items are tracked in `docs/checklist.md`.
