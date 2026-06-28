# Velora — Data Flow

How data originates and moves through Velora. The streaming/event path is first-class.

> **Current implementation.** The **Library** is now backend-backed: it reads from and writes to the FastAPI CRUD API via `web/frontend/lib/api.ts` (hand-rolled fetch, await-then-apply), so storylines/characters/settings/scenarios **persist** in Postgres. The backend is seeded with the Embergate world (`web/backend/app/core/seed.py`) so the app looks the same. The **Story player** still runs on in-memory seed data (`web/frontend/features/story-player/scene-data.ts`) — the streaming path below is the planned design. (TanStack Query is still deferred; the hand-rolled client suffices for this CRUD surface.)

## Sources

| Source | Examples | Where it lives |
| --- | --- | --- |
| PostgreSQL (core state) | users, storylines, characters, settings, scenarios, events, stat definitions, stat values | `web/backend/app/models/` |
| Redis (live/cache) | active scenario state, stream pub/sub, cached reads | `web/backend/app/core/` (client), used by `services/` |
| Neo4j (Story Graph) | character/setting nodes + their edges (the one knowledge graph); instances only — the type system lives in Postgres | `app/core/neo4j.py` (client), `app/services/graph_{writer,reader}.py` |
| YAML config | hand-authored storylines, characters, settings, stat definitions | loaded by `app/core/` → `services/` (State manager) |
| Markdown guidance | one file per stat (what raises/lowers it, bands, behavior) | `app/core/` loader → injected into agent context |
| LLM providers | model completions for agents | `web/backend/app/core/` (provider interface) → `app/agents/` |
| Client-only state | UI state, draft input, panel toggles, theme | `web/frontend/` (React state) |
| Derived/cached | computed scenario state, summaries | `app/services/`, cached in Redis |
| Vector DB (deferred) | semantic memory retrieval | `app/memory/` (seam) |

## Read Path (e.g. open a scenario)

1. Frontend route loads → calls `GET /scenarios/{id}` (and related storyline/characters/settings) via the `lib/` API client.
2. FastAPI route → service → Postgres model → Pydantic schema → JSON response.
3. Frontend renders; server-state caching via TanStack Query if/when adopted.

## Write Path (e.g. submit a turn)

1. User submits a turn in the Story Player → `POST /play/{scenarioId}/turn`.
2. Backend validates (Pydantic), persists the user event (Postgres), updates live scenario state (Redis).
3. The **Orchestrator/Director** runs the relevant agents (Character/Narrator) against the canonical scenario state, the current stat values, and the injected stat guidance files, consulting the LLM provider.
4. Each proposed event (and any implied stat change) is **validated and clamped**, persisted (Postgres), and emitted to the **Event Engine**.

## Streaming Path (live story output)

1. The client opens `GET /stream/{sessionId}` (SSE or WebSocket).
2. The Event Engine publishes typed events as **NDJSON** (one JSON object per line) — `narration`, `character_dialogue`, `character_action`, `state_update`, `branch_choices`.
3. Redis pub/sub fans events from the orchestrator to the active stream connection(s).
4. `useEventStream` parses each line and routes by `type`: visible messages render as deltas arrive (then finalize on `message_end`); `state_update` (incl. stat changes) updates the side panels without adding a chat message; `branch_choices` updates the branch panel.
5. Connection states (connecting, open, stalled, reconnecting, closed) are surfaced in the UI.

## Stat Change Flow

```
Director/character agent proposes a change (stat key, delta or value, reason)
  → emitted as a state_update event
  → Validator confirms the stat exists and clamps the result to [min, max]
  → event streamed to the UI
  → Stats panel updates; narrator may reference the new state next turn
```

The change carries a **reason**, giving a free audit trail ("Health −25: struck by the falling beam") useful for debugging the model and for showing the player *why* a number moved. Current stat values plus their guidance files feed back into agent context each turn, so a near-dead character fights weakly and a high-strength character can plausibly force a door.

The event schema is shared via `web/shared/contracts/` and documented in `docs/api-contract.md`. Keep all three in sync.

## Settings Flow (Options menu)

```
Options page (/options) → lib/api.ts → GET/PATCH /api/options
  → settings_store reads/writes the app_settings rows (one per namespace)
  → LLM tab: POST /api/options/llm/{models,test}
      → backend httpx proxy → {baseUrl}/models · {baseUrl}/chat/completions
      → result returned to the UI (CORS-free; API key stays server-side)
  → Image Generation tab: GET /api/options/comfy/workflows · POST /api/options/comfy/status
      → comfyui client → {baseUrl}/system_stats (status); the full generate
        pipeline (POST /prompt → WebSocket wait → /history → /view) is server-side
```

The LLM API key is **write-only**: stored in the `app_settings` row, never
returned to the browser (reads expose `hasApiKey` + a masked hint). Model listing
and the connection test run on the backend so they work against `localhost:*`
servers that don't send CORS headers, and so the key never reaches the client.
When the multi-agent brain lands it reads the same stored config.

## Reasoning-Budget Flow (engine detection + thinking cap)

```
App startup (lifespan) → background poller every LLM_BACKEND_POLL_SECONDS
  → llm_backend.refresh_for_config → probe configured endpoint
      GET {root}/version → vLLM · GET {root}/props → llama.cpp · else unknown
  → cached per base URL (LLM_BACKEND_CACHE_TTL_SECONDS)

Authoring call → agent passes a backend-set reasoning effort
  → llm.chat_complete(reasoning=) → llm_backend.get_backend (cached)
      → apply_reasoning: vLLM thinking_token_budget / llama.cpp thinking_budget_tokens
      → unknown: no key added (unchanged behaviour)
GET /api/options/llm/backend → read-only view of the detected engine + budgets
```

The effort is **never user-controllable** for Storyline/Character/Setting creation —
it is fixed at each call-site (**Triage = Low**, build + standalone drafts =
**Medium**). The poller lets the server adapt when the operator swaps engines without
a restart; it is skipped under SQLite (the test/offline profile).

## Storyline Authoring Flow (creation-time agent)

```
Create modal (StorylineModal) → lib/api.ts
  → POST /api/storylines/draft   {seed, docsOverview?}  → {title, genre, tagline, premise}
  → POST /api/storylines/primer  {premise, seed?, docsOverview?} → {worldPrimer}
      → routes/storylines → agents/storyline_agent
          → settings_store resolves the configured endpoint/model/key
          → services/llm.chat_complete → {baseUrl}/chat/completions
  → drafted fields + primer fill the form; author edits, then the normal
    POST/PATCH /api/storylines persists premise + worldPrimer
```

This is a **one-time, creation-time** generation, not a per-turn cost. There is
**no retrieval / RAG**: `docsOverview`, when present, is text read from dropped
reference files *in the browser* and passed inline for that one call only — the
files are never uploaded, persisted, or indexed (the corpus/RAG layer is a later
plan). The agent reuses the same stored LLM config as the Options menu.

## Character Authoring Flow (creation-time agent + portrait)

```
Character modal (CharacterModal) → lib/api.ts
  → POST /api/characters/draft            {seed, docsOverview?, storylineId?}
        → {name, role, traits, speech, goal, secret, appearance, background, personality, color}
  → POST /api/characters/portrait-prompts {name, appearance, traits, species?, ...} → {positive, negative}
  → POST /api/characters/portrait         {positive, negative}  → {portrait: "/media/portraits/<id>.webp"}
        → routes/characters → agents/character_agent (draft/prompts/stats; same
          settings_store + services/llm.chat_complete as the storyline agent)
        → routes/characters → services/portraits → services/comfyui.generate
          (watercolor pipeline) → PNG → Pillow → WebP saved under MEDIA_DIR, served at /media
  → POST /api/characters/starting-stats   {storylineId, ...} → {proposals:[…]}  (proposal only)
  → drafted fields + portrait fill the form; author edits, then the normal
    POST/PATCH /api/storylines/{id}/characters persists the fields + portrait URL;
    accepted starting stats are applied via PUT /api/characters/{id}/stats
```

Same **creation-time, no-RAG** rules as storyline authoring. Everything produced
is a character's **own base identity** (§1 node properties) — no graph structure
is built here. Portrait generation is an explicit, opt-in step (it spends GPU
time on the local ComfyUI server); starting stats are **proposal-only** until the
author saves them.

## Setting Authoring Flow (creation-time agent + scene art)

```
Setting modal (SettingModal) → lib/api.ts
  → POST /api/settings/draft               {seed, docsOverview?, storylineId?}
        → {name, type, desc, atmosphere, features, currentState}
  → POST /api/settings/scene-art-prompts   {name, atmosphere, features, ...} → {positive, negative}
  → POST /api/settings/scene-art           {positive, negative}  → {image: "/media/scenes/<id>.webp"}
        → routes/settings → agents/setting_agent (draft/scene-art prompts; same
          settings_store + services/llm.chat_complete as the storyline agent)
        → routes/settings → services/scene_art → services/comfyui.generate
          (watercolor pipeline) → PNG → services/media (Pillow → WebP) saved under
          MEDIA_DIR/scenes, served at /media
  → drafted fields + image fill the form; author edits, then the normal
    POST/PATCH /api/storylines/{id}/settings persists the fields + image URL
```

Same **creation-time, no-RAG** rules. Everything produced is a setting's **own
base description + current state** (§4.1 Setting-node properties) — never the
play-accrued **event timeline** (ships empty, written async once play exists) and
never graph edges. Scene art is an explicit, opt-in step (it spends GPU time on
the local ComfyUI server).

## Scenario Authoring Flow (creation-time agent)

```
Scenario modal (EntityModal + ScenarioForm) → lib/api.ts
  → POST /api/scenarios/draft   {seed, docsOverview?, storylineId?}
        → routes/scenarios → agents/scenario_agent.draft_scenario
            world_context + numbered ROSTER (crud.list_characters / list_settings,
              capped at 40 each) → services/llm.chat_complete (same settings_store)
            model returns names → resolve names→ids (case/whitespace-folded):
              drop unknown cast · setting → "" when unmatched · dedupe cast
        → {title, genre, tone, goal, opening, castIds, settingId}
  → drafted fields + the resolved cast (MultiSelect multiple) + setting (MultiSelect
    single) fill the form; author edits, then the normal
    POST/PATCH /api/storylines/{id}/scenarios persists it
```

Same **creation-time, no-RAG** rules. The key invariant: the drafted `castIds` /
`settingId` are **always real members of the active storyline** — the agent never
trusts model-emitted ids, it resolves names against the live roster and drops
anything that doesn't match, preserving `resolveScenario`'s soft-reference
fallback by construction. The scenario modal grounds on **seed + world roster**
only (no `ContextFilesPanel` yet); branches are not drafted in this first cut.

## Orphaned-Media Cleanup Flow (maintenance)

```
Options → About tab → Maintenance section → lib/api.ts
  → GET  /api/options/media/orphans?min_age_hours=24   (dry-run scan)
        → routes/options → services/media_cleanup.scan_orphans
            referenced = {basenames of Character.portrait} ∪ {Setting.image}
            for *.webp in MEDIA_DIR/portraits + MEDIA_DIR/scenes:
              orphan   = basename ∉ referenced
              eligible = orphan AND mtime older than min_age_hours (grace period)
        → {portraits, scenes, orphanCount, eligibleCount, totalBytes, eligibleBytes, minAgeHours}
  → author reviews counts, confirms, then
  → POST /api/options/media/cleanup?min_age_hours=24   (delete eligible only)
        → services/media_cleanup.delete_orphans (re-scans; unlinks eligible orphans)
        → {deletedCount, freedBytes, skippedRecentCount}
```

A WebP is written to disk the moment ComfyUI renders it — before the entity is
saved — so a cancelled draft or a deleted Character/Setting leaves an unreferenced
file behind. Cleanup cross-references disk against the two media columns. The
**grace period** (`min_age_hours`, default 24) is the safety valve: a just-generated
file from an in-flight draft counts as an orphan but is *not eligible*, so an
author mid-creation never loses their pending image. Deletion is doubly guarded
(unreferenced AND grace-expired), `.webp`-only, and scoped to the two media subdirs.

## Build Everything Flow (the New Storyline world build)

```
New Storyline page → "Build the whole world" → POST /storylines/build {seed?, docsOverview?}
  → build_agent orchestrates (configured LLM, one call per entity):
      draft_storyline → metadata
      generate_world_primer → World Primer
      blueprint → universal stat schema + character/setting concepts
      draft_character × N (grounded in the just-drafted world brief)
      draft_setting   × M
  → ProposedWorld returned for REVIEW (nothing persisted yet)
  → author edits/prunes → "Create world" commits via normal CRUD:
      POST /storylines → POST …/stats × → POST …/characters × (+ portrait if ComfyUI)
        + PUT …/stats → POST …/settings × (+ scene-art if ComfyUI)
        + POST …/context-docs/bulk (the triaged corpus)
  → navigate to /{newStorylineId}
```

The build is a **one-time, creation-time** orchestration (not a per-turn cost) and
**persists nothing** — it returns a proposal so the author reviews before a dozen
AI-drafted rows are written. Images are **opt-in** and rendered at commit only when
ComfyUI is configured (best-effort per entity; a failed render never aborts the build).
Same **no-retrieval** rule as the other authoring agents: `docsOverview` is inline
dropped-file text, bounded and used for the build only.

### Live build (streaming) — the default UI path

```
New Storyline page → "Build the whole world" → POST /storylines/build/stream  (NDJSON)
  → for-await over the response body (lib/api.postNdjson):
      status → meta  → left fields fill (Title/Genre/Tagline/Premise)
      status → primer→ World Primer fills
      status → plan  → stat schema + skeleton labels (the attached doc names)
      character × N  → one per ATTACHED character-doc, fills its skeleton card
      setting   × M  → one per ATTACHED setting-doc, fills its skeleton card
      done           → canonical ProposedWorld swapped in (review mode)
  → if ComfyUI REACHABLE (status preflight): renderProposalImages renders each
      portrait/scene-art and patches the displayed entity → IMAGE previews pop in live
  → "Create World" commit → persists everything; attaches already-rendered images and
      renders any still missing (renderPortrait/renderSceneArt) → navigate to /{id}
```

The build creates the storyline, the stat schema, and **only the characters/settings
attached as context docs** — one entity per doc, drafted from it. It never invents a
cast: no character docs → no characters created (likewise settings). `useStorylineCreator.build()`
sends `characterDocs`/`settingDocs` (docs categorized as such); the backend builds one
entity per doc.

The page consumes the stream in `useStorylineCreator.build()`, accumulating into
`proposed` + `planConcepts`; the right pane (`WorldBuildPanel`) renders the cast/settings
as they arrive (a "drafting…" skeleton per not-yet-drafted concept), then becomes the
editable review. **Images render as part of the build** (`renderProposalImages`, best-effort,
skipping entities that already have one) — but only after a ComfyUI **status preflight**
confirms the server is actually reachable (`imagesAvailable` just means a URL is
configured), and a **circuit breaker** stops on the first failed render so a stopped
ComfyUI never produces a 502-per-entity storm. The image-gen endpoints are id-agnostic
so no persistence is needed yet; the **commit** then attaches those URLs (and renders any
still missing, with the same one-failure-then-stop guard). Hitting *Create World*
mid-render aborts the build's image loop (no double-render, no race). The non-streaming
`/build` collector remains for back-compat.

## Context Document Flow (the triaged RAG corpus)

```
New Storyline page → pick an upload target (Uncategorized / Character / Setting /
  Other + Draft/RAG defaults) → drop .txt/.md (read in-browser)
  → files land pre-categorized into that bucket (a whole batch at once, no triage)
  → leftovers left Uncategorized → POST /storylines/triage/stream (Uncategorized only)
      → per file: status {name,index,total} → item {category, includeDraft, includeRag}
      → each row fills in LIVE (the active file shows a "classifying…" badge)
  → author reviews the buckets (Characters / Settings / Other) + Draft/RAG flags
  → on commit: POST /storylines/{id}/context-docs/bulk persists the corpus
      → ContextDocument rows (content stored verbatim, char_count cached)
```

The author can **bulk-categorize on upload** — choose a bucket (and the Draft / RAG
defaults) once, then drop a folder of e.g. character sheets and they all land as
Characters with no triage. **Triage** then sweeps only what's still **Uncategorized**,
leaving the manual buckets alone. Triage runs **per file** (one LLM call each) so the
panel sorts documents in front of the author; the batched `POST /storylines/triage`
remains for back-compat. A per-doc failure falls back to `other`/RAG-on without
aborting the run.

The **context budget** (the inline grounding cap + the meter on the page) is **32000
characters** (`_common.DOCS_CAP` / `readDocs.DOCS_CHAR_CAP`; ~8000 tokens), raised from
the original 8K so larger lore/corpus batches can ground generation.

This is the **persistence seam** for retrieval: the documents are durably stored
per storyline and survive reload. **Nothing reads `content` at runtime yet** —
chunking, embeddings, hybrid search, and runtime retrieval remain a later plan.
`includeDraft` docs additionally ground the creation-time generation (inline, not
retrieved); `includeRag` simply marks corpus membership for the future retriever.

## Story Graph Flow (Neo4j substrate)

```
Write (authoring) — on Character/Setting create/edit/delete:
  routes → services/crud (commit to Postgres)
    → graph_writer.sync_character / sync_setting / remove_node  (best-effort, after commit)
        → validate the instance against the Type Registry (§6.5)
        → neo4j.write_session → MERGE (:Node {id}) SET dynamic label + metadata (§6.2)
  (graph down/disabled → logged + skipped; CRUD still succeeds)

Read (scenario load) — GET /api/scenarios/{id}/graph:
  routes/scenarios → graph_reader.scenario_graph
    → ensure_scenario_materialized: upsert the cast + setting (+ present_at edges)
      from Postgres into Neo4j (idempotent; so the seeded world appears on first load)
    → neo4j.read_session (READ access mode, §7.4) → parameterized Cypher templates (§7.2)
    → { available, scenarioId, nodes[], edges[] }   (available:false when off/unreachable)
```

The **Type Registry** (`graph_type_definitions` in Postgres) is the semantic
source of truth — what node/edge types exist, their field schema, and edge valence
(§1.4); Neo4j holds the instances. Built-in types (§5) are global + immutable; users
add per-storyline types via `POST /storylines/{id}/graph/types`. **Deferred seams:**
the async turn-writer (§8 cold path), the vector entry-point (§7.1), and
Text2Cypher (§7.3) — their prerequisites (a turn loop, an embedding stack) don't
exist yet. See `docs/story-graph-neo4j.md`.

## State Ownership

- Authoritative state: backend (Postgres) — validated server-side, stats clamped.
- Live/ephemeral state: Redis (active scenario).
- UI/interaction state: frontend only (panel toggles, theme, draft input).
- Never trust client-sent state as authoritative; always re-validate on the backend.
