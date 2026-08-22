# Mytheca — Project Documentation

Purpose, domain model, stack, and current status. For layout see `structure.md`, for commands `workflow.md`, for open work `checklist.md`.

## Purpose

Mytheca is an AI-driven, multi-character roleplay chat engine. You author a world and its cast, then play through scenes where several AI characters talk to you and to each other while a Narrator sets the scene. The player can also speak *as* one of the cast (POV mode).

The backend emits **small, typed, validated story events**; the frontend maps each event type to a component. The model decides what happens — it never decides layout.

## Domain Model

Four canonical objects, plus the Story Event abstraction and the Stat system.

| Object | What it is | Real Postgres columns |
| --- | --- | --- |
| **Storyline** | The world. Owns its characters, settings, scenarios, and the baseline stat schema. | `id, title, genre, tagline, premise, world_primer, symbol, symbol_color, position, prompt_overrides` |
| **Character** | A person in the world. | `id, storyline_id, name, role, color, mono, traits, speech, goal, secret, appearance, background, personality, portrait, portrait_positive, portrait_negative, voice_samples, position` |
| **Setting** | A place in the world. | `id, storyline_id, name, type, desc, atmosphere, features, current_state, image, scene_art_positive, scene_art_negative, timeline, position` |
| **Scenario** | The live situation being played. | `id, storyline_id, title, genre, tone, goal, setting_id, opening, cast_ids, branches, position, max_turns, suggestions_count, context_beats, context_policy, beat_length, direction_verbs, prompt_overrides, image, scene_art_positive, scene_art_negative` |

**Not modelled:** there is no `User` table and no `Scene` table. Character relationships are **not** Postgres columns — they live only as Neo4j graph edges.

**Stats** are bounded numeric values defined per storyline (`stat_definitions`), each with labeled bands and an optional Markdown guidance file. The validator clamps every AI-proposed change to `[min, max]`.

Their **lifecycle** is the part that trips people up (owner decision D-1). A value lives in **two** places: `character_stats` is the character's **authored** starting value, and `session_character_stats` is what a stat is worth *inside one play-through* — which is where play writes, and why two play-throughs of one scenario no longer share a value and a branch or rewind is predictable. A stat carries into the next scene only when its definition says `carry_over`; the default is **reset**. When it does carry, `character_stats.baseline` preserves the authored value the first time the carry would destroy it, and `POST /characters/{id}/stats/reset` is the way back. A stat whose `visibility` is `hidden` still moves and is still recorded — its change is simply never streamed to the transcript.

**Story Events** — 8 types, defined in `web/backend/app/events/envelope.py`:
`narration` · `character_dialogue` · `character_action` · `internal_thought` · `state_update` · `branch_choices` · `character_status_change` · `scene_image` · `cast_request`.
The first seven come from the turn loop; `scene_image` is the one the **player** triggers —
a picture of the moment, painted on demand from the scene and persisted as a beat.

Full envelope and payloads: `api-contract.md`.

## Tech Stack

| Layer | Actual choice |
| --- | --- |
| Frontend | Next.js 16 (App Router, Turbopack) · React 19 · TypeScript · Tailwind CSS v4 · Framer Motion 12 · `react-force-graph-2d` (Graph view) |
| Backend | FastAPI · Python 3.13 · `uv` · SQLAlchemy 2.0 · Alembic |
| Core data | PostgreSQL — 13 tables (storylines, characters, settings, scenarios, stat_definitions, character_stats, events, play_sessions, turn_traces, context_documents, context_document_links, app_settings, graph_type_definitions) |
| Live state | Redis — recent-turn buffer, per-character interior state |
| Story Graph | Neo4j 5.26 (custom APOC image) — typed nodes/edges, best-effort |
| Semantic memory | Qdrant + fastembed `BAAI/bge-large-en-v1.5` (1024-dim), hybrid dense + BM25 + RRF — best-effort |
| Images | ComfyUI (local) — character portraits, setting/scenario scene art, and in-play scene images, saved as WebP |
| AI | OpenAI-compatible endpoints (cloud OpenAI or local vLLM / llama.cpp) behind one proxy |
| Streaming | NDJSON over the turn POST response |

Stat guidance is Markdown (`web/backend/app/content/stats/*.md`). There is **no YAML config layer** — earlier docs claimed one; entities live in Postgres.

## Architecture Summary

```
Player line
  → assembler (cast + clamped stats + Redis buffer + gated RAG + prompt prefix)
  → intent_agent (narrate / address / puppet / whole-group; + direction requirements)
  → direction_agent (the player's direction → outcomes the turn owes, scheduled to fit)
  → ReAct loop: planner_agent.plan_beats (up to N beats/call) → speak | narrate | exit | end
       └ character_turn_agent (think → speak, one isolated call per beat)
       └ emission parse → validator (clamp / drop)
  → NDJSON story events streamed to the browser
  → cold path: turn_writer → Neo4j · read-time: reflection → Redis
```

Detail: `architecture.md` (decisions), `data-flow.md` (the turn walkthrough), `api-contract.md` (endpoints + events).

## Major Decisions

- **Event-driven rendering** — the AI emits typed events, the backend validates, the frontend renders. 8 event types.
- **ReAct planner with lookahead, and it can be switched off** — `planner_agent.plan_beats` decides up to `TURN_PLANNER_LOOKAHEAD` beats per call from the present roster, and the engine re-plans when the queue empties or a planned beat goes stale. It replaced the older one-shot `director_agent.who_is_up` / `rerank`, which are now **dead code kept only for their unit tests**. Deciding one beat at a time made this agent 41 % of all turn time (EXP-2026-08-005); `next_beat` remains as the one-beat wrapper. A scene (or one turn) can bypass it entirely — `plannerMode: "off"` runs `services/beat_order`, the model-free scripted order, which is the largest latency lever a player has and costs the register, the stakes, mid-turn narration and exits.
- **The scene remembers as much as the model can hold** — the transcript window is fitted to the
  model's real context budget each turn rather than to a number the player picks, and what it
  reached is *reported* (the Inspector's `window` step, the config menu's "What the scene
  remembers", and a visible line in the transcript where verbatim recall ends). Folding the
  beats that fall out into a rolling summary is built and **defaults off** — `EXP-2026-08-011`
  measured it and the compacted arm lost a fact the control kept, so C-013 stays
  `unsupported`.
- **The player's direction is a contract, not a hint** — `direction_agent` turns it into ordered requirements and the engine schedules them into the scene's `maxTurns` budget, taking the decision off the planner once the budget is as tight as the direction is long. Each beat is told the outcome it owes, never the words. **A requirement is confirmed by the prose that landed, not by entering a prompt** (`direction_check`), an unconfirmed one is retried and then reported honestly, and whatever the turn could not deliver is **carried to the next turn** until it lands or the player dismisses it. The player can aim a line at one character by `@`-naming them, and a target they set is never silently re-owned by the narrator — if that character is not in the scene, the requirement waits and the scene *asks* whether to bring them in. **The AI never introduces a character on its own initiative.**
- **One isolated LLM call per speaker** — no shared multi-POV prompt, to keep voices distinct.
- **Situational adaptation is computed, not requested** — `planner_agent.plan_beats` returns the beat's **register** (`light`/`neutral`/`tense`/`grave`) and **stakes** on the call it was already making. The register is stated as fact in the character prompt's recency tail, selects which voice samples the speaker is shown, and tunes the sampler. Telling a character in prose to "adapt to the moment" loses to the concrete voice samples proving how it sounds at rest; giving it a different set of samples does not.
- **Server-side clamping** — proposed stat / relationship / presence changes are proposals; `validator.py` clamps or drops them.
- **Best-effort substrates** — Neo4j, Qdrant, Redis and ComfyUI each degrade to a no-op when absent. CRUD and the full test suite run with none of them.
- **No dice** — narrative resolution only; `branch_choices` carry `label` + `outcome`.
- **Alembic is adopted**, not deferred: 12 migrations under `web/backend/alembic/versions/`, coexisting with `create_all` + an additive column reconciler.
- **`uv` only** for Python; npm for the frontend.

## Current Status

Implemented and exercised end to end:

- Full CRUD for the four canonical objects, plus stats, context documents, and the Story-Graph type registry.
- Agentic authoring: storyline draft + primer, conversational scope-aware storyline **editing** (`storyline_edit/`), **create-time world population** (`roster_agent` + `services/world_populate` — the generated cast + settings a new world starts with), character / setting / scenario creators, document triage, portrait + scene-art generation.
- The runtime turn loop: intent → ReAct planner → per-character think→speak → validator → NDJSON stream, with presence tracking, POV play, follow-up suggestions, cold-path Neo4j writes, and read-time reflection.
- In-narrative images: a **Create image** control at the foot of the transcript writes an appearance-first prompt from the live scene (`moment_agent`) and renders it landscape through ComfyUI (`scene_moment`), persisted as a `scene_image` beat.
- Persistent sessions: every turn and its diagnostic trace are stored (`events`, `turn_traces`); reopening a scenario resumes the latest session; sessions export as JSON or Markdown.
- Hybrid RAG with embed-on-save and a conservative retrieval gate.
- Story-Graph view in the story player (force-directed canvas + inspector rail) with an accessible text alternative.
- Three themes, four font-size presets, and a WCAG-AA contrast gate script.

Not built: authentication (no user model, no auth routes), a standalone `GET /stream` transport, admin surfaces, dice resolution, and any evaluation/benchmark harness. Open items: `checklist.md`.

**Validation baseline:** 948 backend pytest cases and 637 Vitest cases across 90 co-located frontend test files, all passing.

**Research status:** Mytheca has **no evaluation results that support a claim** — no benchmark, baseline, ablation or human study. That is recorded, not glossed: `docs/research/` is the single research record, all seven claims in `research/CLAIMS.md` remain `unsupported`, and `research/mytheca-research-audit.md` is the external audit that established it. Two experiment folders exist: `EXP-2026-08-001` (failed — no LLM endpoint was reachable) and `EXP-2026-08-002` (complete — a 3-run, single-arm *functional* verification of the in-narrative image prompts, with no baseline and no claim attached).
