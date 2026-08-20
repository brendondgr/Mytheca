# Mytheca — Architecture

Boundaries, data layer, and the decisions behind them. For the turn walkthrough see `data-flow.md`; for endpoints and event payloads see `api-contract.md`.

## Application Mode

API + separate frontend, streaming-first. The Next.js app is the renderer; the FastAPI app is the brain that runs the multi-agent turn loop and streams story events.

## Core Principle

**The AI generates validated story events; the UI renders them. The AI never decides UI layout.**

The model emits small typed events, the backend validates them (including stat clamping), and the frontend maps each event type to a component. This keeps the model out of presentation and avoids one large blob of prose.

## Domain Model

```
Storyline (the world; owns the baseline stat schema)
 ├── Characters (each holding stat values)
 ├── Settings (the places)
 └── Scenarios (the live situations)
```

Exact column lists live in `documentation.md`. Two things worth stating here because earlier docs got them wrong:

- **There is no `User` model and no auth.** Postgres holds no users table; nothing in `app/` implements login, sessions, or tokens.
- **Character relationships are not Postgres columns.** They exist only as Neo4j graph edges, written by `services/relationships.py` (first-turn seeding from bios) and `services/turn_writer.py` (cold path).

## Backend Components

FastAPI, Python 3.13, `uv`.

| Concern | Where it actually lives |
| --- | --- |
| Turn loop / coordination | `app/services/turn_engine.py` |
| Who acts next | `app/agents/planner_agent.py` (`next_beat`) — a per-beat ReAct decision |
| How grave the moment is | `app/agents/planner_agent.py` (`next_beat` → `register` + `stakes`, no extra call) |
| Voicing one character | `app/agents/character_turn_agent.py` (think → speak, one isolated call) |
| Narration interstitials | `app/agents/narrator_agent.py` |
| Player-intent reading | `app/agents/intent_agent.py` |
| Scene direction (what the turn owes) | `app/agents/direction_agent.py` (`parse`, `schedule`) |
| Follow-up suggestions | `app/agents/director_agent.py` (`propose_branches`, `propose_pov_lines`) |
| Context assembly | `app/services/assembler.py` |
| Emission parsing | `app/services/emission.py` |
| Validation / clamping | `app/services/validator.py` |
| Within-turn continuity | `app/services/consistency.py` |
| Event envelope + NDJSON | `app/events/` |
| Persistence | `app/models/`, `app/services/events_store.py`, `crud.py` |
| Config, clients, preflight | `app/core/` |

There is no "Orchestrator", "Rules Engine", "Memory System", or "KG Builder" module — earlier docs named components that were never built. The list above is the real set.

### Dead code, kept deliberately

`director_agent.who_is_up` and `director_agent.rerank` are the **superseded one-shot speaker picker**. They are called only from `utils/tests/backend/agents/test_director_agent.py`; no production path invokes them. Their prompt-registry keys (`director.who_is_up`, `director.rerank`) are still exposed through the Options API, so an operator can edit prompts for an agent that never runs. Either remove both, or leave them and treat this paragraph as the warning.

## Agent Roles (as built)

1. **`intent_agent`** — is the player narrating, addressing someone, directing a character to act, or speaking to the group?
2. **`direction_agent`** — the player's scene direction as a list of outcomes the turn owes, each optionally bound to a cast member, plus the deterministic packer that fits what is left into the beats that are left. In narrator mode the requirements ride on the `intent_agent` call that already read the line; POV-mode `guidance` is a separate string and gets its own parse.
3. **`planner_agent`** — the ReAct loop. One beat at a time: `speak` / `narrate` / `exit` / `end`, chosen only from **present** cast members, with the POV character locked out. The same reply carries the beat's **`register`** (`light`/`neutral`/`tense`/`grave`) and **`stakes`** — the scene-appraisal signal every speaker conditions on, obtained without a second LLM call. It is also shown what the direction still owes and how many beats remain; once those numbers meet, the engine schedules the rest itself.
4. **`character_turn_agent`** — one isolated LLM call per beat. Emits a visible in-voice `<thinking>` block, then speech, in a thin tagged format the backend parses.
5. **`narrator_agent`** — scene-setting and interstitials.
6. **`director_agent`** — end-of-turn follow-up suggestions (situation branches, or first-person lines when POV is active).
7. **`reflection_agent`** / **`relationship_agent`** — off-hot-path interior state and graph edges.

Authoring-time agents (`storyline_agent`, `storyline_edit/`, `roster_agent`, `character_agent`, `setting_agent`, `scenario_agent`, `triage_agent`) are separate from the turn loop.

## Structured Side Effects Are Proposals

A character may propose a stat change, a relationship edge, or its own scene exit. Each is parsed tolerantly and then checked server-side by `validator.py`:

- `validate_stat` — unknown key dropped; value resolved from `value` or `delta`; result clamped to `[min, max]`; free-text `reason` kept as an audit trail.
- `validate_relationship` — type must be in the registry; target must resolve to a real cast member (exact match, then substring fallback); self-directed edges dropped.
- `validate_presence` — status must normalize and the transition must be legal (no exit from `dead`).

The model can therefore never push a value out of bounds or invent a stat key.

## Stat System

A stat is a bounded numeric value on a character. Health, trust, suspicion, patience are all the same object.

- The **Storyline** defines the baseline schema (key, label, description, `min`/`max`, default, visibility, optional guidance file). Bands ("tickers") name what ranges *mean*.
- Guidance is Markdown under `app/content/stats/`, loaded by `services/stat_guidance.py` and rendered into the character prompt by `services/stat_render.py` (current band + `{Character}` substitution).
- Changes ride on `state_update` events and are clamped by the validator.
- **Scenario-level stat additions and range overrides are not implemented** — the `Scenario` model has no such field. Earlier docs described this; treat it as unbuilt.

## Presence

Runtime scene presence is **derived from the session's event log** — `character_status_change` events folded by `services/presence.py` (latest per character, default `present`). No extra table, survives reload. Five statuses: `present` · `unconscious` · `departed` · `left` · `dead`. Only `present` members are selectable by the planner.

Four detection paths, all automatic: a `health`-keyed stat clamped to its floor; the planner's `exit` beat; a character's self-declared `presence_change` block; and a manual override (`POST /play/{id}/presence`), which is not bound by the transition guard so the player may resurrect.

## Frontend/Backend Boundary

- Frontend owns routing and UX-level validation; backend owns the API, the streaming lifecycle, authoritative validation (Pydantic), errors, retries, and stat clamping.
- **`web/shared/contracts/` is empty.** The live TypeScript mirror of the event and entity contract is hand-maintained in `web/frontend/lib/events.ts` and `lib/types.ts`. Keeping it in sync with `app/events/envelope.py` is a manual step.
- Library CRUD uses **await-then-apply** (await the mutation, splice the returned entity, surface errors) — not optimistic UI. Optimistic UI is reserved for story-player turn submission. The client is a hand-rolled `fetch` in `lib/api.ts`.

## Data Layer

- **PostgreSQL** — 13 tables covering the four canonical objects, stats, events, play sessions, turn traces, context documents, app settings, and the Story-Graph type registry. Sync SQLAlchemy 2.0 + psycopg3; camelCase over the wire; string PKs; branches as JSON, stats normalized.
- **Redis** — recent-turn buffer (`memory/buffer.py`) and per-character interior state (`memory/interior.py`). Best-effort.
- **Neo4j** — the Story Graph. Node `type` → label, edge `type` → relationship type, every node also `:Node`; dynamic labels bound as parameters (`MERGE (n:Node {id}) SET n:$($type)`, 5.26+). The Type Registry in Postgres is the semantic source of truth; Neo4j holds instances. Consequences are reified `:Consequence` nodes. Best-effort — never blocks CRUD.
- **Qdrant** — one `mytheca_lore` collection with named dense + sparse vectors (fastembed `BAAI/bge-large-en-v1.5` 1024-dim + BM25), fused by RRF. Embed-on-save, prune-on-delete. Best-effort.

**How the graph actually reaches the model:** not through `TurnContext.subgraph`. That object is assembled every turn but its only consumer is a boolean `available` flag in the diagnostic trace — `character_turn_agent.py` never reads it. What conditions generation is `graph_reader.relationship_context()`, a direct 2-hop Cypher read folded into a plain-language relationship note in the character prompt.

## Streaming Layer

NDJSON, one JSON object per line, streamed **directly in the turn POST response** (`POST /api/play/{scenarioId}/turn`). A separate `GET /stream` with Redis pub/sub fan-out remains an unbuilt seam.

Two modes:

- **Full events** — used for state and stat updates.
- **Delta streaming** — used for visible prose. The **same story event** (identical `id` and `seq`) is re-emitted with incremental `text` and `done: false → true`. There is **no** `message_start` / `message_delta` / `message_end` frame set; earlier docs claimed one.

Two transport-only frames exist alongside story events: `TurnErrorFrame` (`{type:"error", message}`) and `TurnTraceFrame` (`{type:"trace", n, step, title, detail, data}`).

## Auth (not built)

There is no authentication of any kind: no user model, no auth routes, no session or token handling. Everything is single-tenant and unauthenticated. Roles, protected routes, and the JWT-vs-cookie decision are open items in `checklist.md`. Do not describe auth as "backend-owned and decided" — it is undesigned.

## Key Decisions Log

- Event-driven rendering; **7** event types.
- Per-beat ReAct planner replaced the one-shot director; the old arm survives only in tests.
- One isolated LLM call per speaker, to hold voices apart.
- The beat's **register** rides on the planner's existing reply (no second appraisal call) and drives the character prompt's tail, voice-sample selection, and sampler.
- Server-side clamping of every proposed side effect.
- Best-effort substrates throughout (Neo4j / Qdrant / Redis / ComfyUI down → degrade, never block).
- **No dice** — narrative resolution only; `branch_choices` carry `label` + `outcome` and the check card was retired.
- **Alembic adopted** — 12 migrations, coexisting with `create_all` + an additive reconciler. (Earlier docs said "Alembic deferred"; that is wrong.)
- Persistence: sync SQLAlchemy 2.0 + Postgres; tests on in-memory SQLite.
- Story-Graph visualization via `react-force-graph-2d` (canvas + d3-force), isolated in `components/feature/GraphCanvas.tsx`, lazy-loaded with `next/dynamic({ ssr:false })`. Deterministic type→color map (`lib/graphColors.ts`) plus a visible legend and an `sr-only` table as the canvas text alternative.
- Provider-agnostic LLM access is one OpenAI-compatible proxy (`services/llm.py`) serving cloud OpenAI, vLLM, and llama.cpp alike. It offers a blocking primitive (`chat_complete` / `chat_complete_usage`) and a streaming one (`chat_complete_stream`, SSE). The streaming primitive separates the model's **reasoning** channel from its **answer** channel — reading whichever field the endpoint uses for it — **`delta.reasoning_content` on llama.cpp, `delta.reasoning` on vLLM** (`llm._reasoning_field` checks both; reading only one silently discards the channel on the other, which looks like a model that does no reasoning) — and splitting inline `<think>` blocks out of `delta.content` where neither is offered — and degrades to the blocking path (one delta at the end) on any endpoint that refuses `stream: true`, so callers never branch on transport. Structural JSON calls stay blocking: their result is useless until complete.
- **`docs/research/` is the single research record** (2026-08-06). Every experiment, claim, figure and finding lives there and nowhere else; the unit of record is an experiment directory with a fixed contract, not a loose markdown file. Enforcement is `make validate-research`, run by hand — CI and pre-commit were deliberately not adopted (`research/DECISIONS.md` D-005). Two dependencies were added in a `research` group and kept out of the runtime list: `pyyaml` (manifest parsing) and `matplotlib` (figure generators, which must emit `.svg` and `.pdf` from recorded metrics, never hardcoded numbers).
