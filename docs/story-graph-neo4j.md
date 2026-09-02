# Mytheca — The Story Graph (Neo4j substrate)

Mytheca keeps **one** knowledge graph, the **Story Graph**, on Neo4j. Characters,
Settings, Events, Secrets, and Factions are all *node types* inside it; their
connections are edges. This document is the implementation guide for that
substrate. The full conceptual model is `Documents/Plans/5.4_story-graph-structure-prep.md`;
the implementation plan is `docs/plans/story-graph-neo4j-substrate.md`.

## What's implemented

| Piece | Where | Notes |
| --- | --- | --- |
| Driver client | `web/backend/app/core/neo4j.py` | Lazy, graceful singleton; `read_session`/`write_session` set Neo4j READ/WRITE access mode (§7.4). |
| Custom container | `web/backend/docker/neo4j/Dockerfile` + `docker-compose.yml` | `neo4j:5.26-community` + APOC; Bolt on host **3349**, Browser on **3350**; built + started by `app.py`. |
| Type Registry | `app/models/graph_type.py`, `app/services/type_registry.py`, `app/content/graph_registry.py`, `app/routes/graph.py` | §1.4 — the semantic type system in Postgres; built-in seed catalogue (§5). |
| Write path | `app/services/graph_writer.py` (hooked into `services/crud.py`) | §6 — node/edge upsert with dynamic labels, `:Consequence` reification, registry validation; best-effort. |
| Read path | `app/services/graph_reader.py`, `GET /api/scenarios/{id}/graph` | §7.2 — read-only Cypher templates over the scenario subgraph; materialize-on-load. |
| Turn-loop read consumer | `graph_reader.relationship_context` + `graph_reader.offscene_ties`, called from `services/beat_runner.relationship_note()` | Direct + 2-hop character↔character edges, folded into the character-turn LLM prompt (§7.2 — the graph's actual influence on generated dialogue). **How wide is the player's choice** — see *Tie scope* below. |

## Connection lifecycle (the operating boundary, §8)

- **Container:** owned by `app.py` like Postgres/Redis. `ensure_docker_services()`
  builds the custom image (`compose up -d --build --wait`, with
  `pull --ignore-buildable` for the image-only services) and waits on its
  healthcheck. You never run `docker compose` yourself.
- **Driver:** connects **lazily** — only when a Scenario is loaded
  (`GET /scenarios/{id}/graph`) or a Character/Setting is created/edited (the CRUD
  sync hooks). The driver is a long-lived, pooled singleton (`get_driver`).
- **Graceful / best-effort (decided):** graph sync **never blocks CRUD**. When
  `NEO4J_URI` is unset or the server is down, writes log-and-skip and the read
  endpoint returns `{ "available": false, … }`. Neo4j is an *optional* preflight
  check (like Redis). The test suite runs with the graph disabled — no Docker.

## Why Neo4j 5.26 + dynamic labels (§6.2)

A node's `type` is a Neo4j **label** (`:Character`) and every node also carries a
base **`:Node`** label; an edge's `type` is the **relationship type** (`:loves`).
Since 5.26, labels/relationship types can be referenced from a **bound parameter**
(`MERGE (n:Node {id}) SET n:$($type)`), so built-in *and* user-defined types alike
travel the indexed label path with no Cypher-injection risk. This is the version
pin's whole reason; the writer relies on it.

## The Type Registry (§1.4)

The registry is the **semantic source of truth** (what types exist, their field
schema, meaning, and edge valence). It lives in Postgres (`graph_type_definitions`),
separate from Neo4j (which holds *instances*). Built-in types are **global**
(`storyline_id = NULL`, `status = built_in`, immutable); users add **per-storyline**
types (`status = experimental` until promoted to `trusted`). It compiles into two
artifacts: `validation_rules` (what the writer enforces, §6.5) and `schema_blob`
(grounding for the future Text2Cypher read path, §7.3).

**Open seam (§10) — staged user types (decided):** only `built_in`/`trusted` types
are hot-path eligible; `experimental` user types are written/read by the async /
non-hot path until promoted. `status` is the gate.

## Write path (§6 — authoring side)

On Character/Setting create/edit/delete, `services/crud.py` calls best-effort
`graph_writer.sync_*`/`remove_node` after the DB commit. Each upsert validates the
instance against the registry, then `MERGE`s a `:Node` keyed on the Postgres id,
adds the dynamic type label, and sets metadata properties (clearing a field
removes the property via `+=` null). The recurring consequence record is reified
as a shared `:Consequence` node (§6.4); edges and `:Consequence` nodes are written
today, on the cold path, by `services/turn_writer.py` — after every turn with
durable consequences it routes each one by the "…toward whom?" rule (a relational
target becomes an `upsert_edge` + `attach_consequence`; a non-relational change was
already applied as a stat on the hot path and is recorded here only for audit) and
appends an `:Event` node tied to its setting (`occurred_at`) **and to every character
present** (`involved`). This is separate from `crud.py`'s `sync_*` hooks, which
only mirror Character/Setting *nodes* on create/edit/delete.

### Episodic memory is mirrored here, not stored here

`(:Character)-[:remembers {memory, gloss, salience}]->(:Event)` is a **mirror** of a
`character_memories` row, written best-effort by `graph_writer.mirror_memory_safe` after the
Postgres commit. Losing it costs the ability to walk from a person to a moment; it never
costs the memory. The `:Event` node is upserted rather than assumed, because `turn_writer`
only appends one on a turn with durable *consequences* and a turn can be memorable without
moving a single stat — the quiet ones often are.

`remembers` carries no `decay` in the registry, unlike the feeling edges: fade and
reinforcement are computed by the recall path over the Postgres row, so a decay declared
here would be a second, unread answer to the same question.

### Subjects are promoted, never authored

A subject tag on a memory (`ogres`, `the-north-road`) becomes a `:Subject` node only once it
**recurs** — three or more memories, or two or more scenarios — via
`graph_writer.promote_subjects_safe`, on the cold path. The threshold is the whole point:
without it every noun anyone mentions becomes a permanent node and traversal gets slower for
nothing. `ogres` earns a node in a world precisely because ogres kept mattering there.

Promoted nodes buy **traversal** — "who fears ogres", "every memory about the north road" —
and nothing the hot path depends on: the cue scan matches tags straight off the memory rows,
so a promotion that never happens costs a query nobody is running yet. Memories link to them
with `concerns`.

### Edge provenance and what a rewind rolls back

A relationship edge written during play carries its **`reason`** — the same field
`services/relationships.py` writes at seed time, so `graph_reader.relationship_context()`
renders a tie formed in play and a tie read off a bio identically. It also carries
`origin: "play"` and `status: "active"`.

Every edge and `:Consequence` written by the turn path is stamped with its origin:
`created_session`/`created_seq` (written once, on creation) and `session`/`seq` (last
touch). `graph_writer.remove_edges_after` deletes on the **creation** stamp, and
`session_state.truncate_session` calls it on every rewind.

That rollback is exact for the case that matters — an edge whose `created_seq` is above
the cut never existed before the removed turns, and a relationship *formed* by cut turns
is precisely such an edge. It does **not** revert an edge that existed before the cut and
was merely reinforced afterwards: that edge keeps its post-cut `weight`, because
recomputing it would mean replaying contributions from a log this schema does not keep in
a queryable form. The residue is a number being too high, not a relationship with no story
behind it.

## Read path (§7.2 + §7.4)

`GET /api/scenarios/{id}/graph` **materializes** the scenario's cast + setting from
Postgres into Neo4j (idempotent `MERGE`, drawing `present_at` edges — so the seeded
world appears on first load), then **reads** the subgraph through pre-written,
parameterized Cypher templates in a **read-only** transaction (a stray write is
rejected by the server). Returns `{ available, scenarioId, nodes[], edges[] }`. This
is the **visualization** read path only (the story player's Graph view, below) —
it does not feed the LLM.

### Turn-loop read path — the graph's actual influence on dialogue

`services/turn_engine.py`'s `_relationship_note()` calls
`graph_reader.relationship_context(speaker_id, other_ids)` for every character beat:
direct char↔char edges plus 2-hop indirect ("you and X are both connected to Y")
links, best-effort (empty when the graph is off/unreachable). The result is folded
into a plain-language sentence and injected straight into the character-turn LLM
prompt — this, not the visualization endpoint, is the mechanism by which the Story
Graph actually shapes generated dialogue.

By contrast, `assembler.py` assembles `TurnContext.subgraph` (the scenario subgraph)
on every turn, but nothing renders it into a prompt — its only consumer is the
boolean `available` flag folded into the diagnostic trace (`graph_available` in
`turn_engine.py`).

**Unused query templates.** `graph_reader.presence_casting` and
`graph_reader.secret_reachability` are defined Cypher templates with no callers
anywhere in the codebase today — reserved for future use, not currently live.

## Deferred seams (prerequisites don't exist yet)

- **§7.1 vector entry-point** — needs an embedding stack + a native vector index.
- **§7.3 Text2Cypher** — `schema_blob` is compiled and ready; live generation awaits a hot-path consumer (staged per §10).
- **Graph visualization UI** — *implemented*. The story player's **Graph view** (`components/feature/GraphView.tsx` + `GraphCanvas.tsx`, reached by the `SceneHeader` Chat ⇄ Graph switch) renders this endpoint's subgraph as a `react-force-graph-2d` canvas, colored by type via `lib/graphColors.ts`, with a legend + sr-only table. Degrades to a calm "offline" state when this read path returns `available:false`.

## Environment

```
NEO4J_URI=bolt://localhost:3349      # blank to disable the graph entirely
NEO4J_USER=neo4j
NEO4J_PASSWORD=mytheca-graph          # matches docker-compose NEO4J_AUTH
```

## Tests

Offline (no container): `app/core/neo4j.py` exposes an injectable `build_driver`,
and the writer/reader take a session argument so a recording fake stands in for
Neo4j (`utils/tests/backend/{data,api,services}/test_{neo4j,graph_types,graph_writer,graph_reader,scenario_graph}.py`).
A conftest autouse fixture disables the graph for the suite; graph tests enable it
explicitly with a fake driver/session. Live validation against the running
container is recorded in `docs/checklist.md`.

## Tie scope — how much of a speaker's history reaches their beat

A per-scene setting (`scenarios.tie_scope`) with a per-turn override
(`TurnRequest.overrides.ties`). `NULL` reads as `scene`, which is the default.

| Stop | Who the speaker is given | Cost |
| --- | --- | --- |
| `addressed` | Only the ids the caller passed — which the planner narrows to the addressee. What shipped before this control. | none |
| **`scene`** (default) | Every other **present** cast member. | none — the same `_REL_DIRECT` / `_REL_INDIRECT` queries with a wider `$others` list |
| `world` | …plus the speaker's direct ties to characters **not** in the scene, rendered as a marked trailing clause: *"Elsewhere: you resent Corvin, who is not in this scene."* | one extra query per beat (`_REL_OFFSCENE`) |

`_REL_OFFSCENE` is read-only and fully parameterised, excludes the scene's cast **inside**
the match (so its `LIMIT 8` applies to rows that will actually be used rather than being
spent on in-scene edges), and is storyline-scoped so a tie cannot reach across worlds. The
off-scene clause is folded in **before** the existing 8-line cap, so `world` cannot grow the
prompt: it competes for the same budget, and the in-scene ties are added first, so the cap
trims the *elsewhere* tail rather than the people in the room.

**Why the default moved to `scene`.** A speaker given only the addressee's history is why two
characters could stand in the same room with a decade between them and neither mention it.
That change costs nothing — it is the same query with a longer id list.

**What this is not.** This is **prompt-side edge expansion**. It is *not* the RAG-side
`related`-edge expansion the checklist lists as unbuilt (`docs/rag.md`), it gives
`TurnContext.subgraph` no job (still fetched, still unused — see `docs/checklist.md`), and it
cannot use `secret_reachability`, because nothing in the codebase has ever written a `Secret`
node (also recorded in the checklist).

**Degradation.** `offscene_ties` guards on `neo4j.is_enabled()` and swallows every exception,
exactly as `relationship_context` does. With no graph, all three stops produce the same empty
note and the beat is byte-identical to today's. `GET /play/{id}/relationships` reports
`graphAvailable` so the UI can disable the control **and say why**, rather than offering one
that silently does nothing.
