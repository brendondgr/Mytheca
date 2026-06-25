# Velora — The Story Graph (Neo4j substrate)

Velora keeps **one** knowledge graph, the **Story Graph**, on Neo4j. Characters,
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
as a shared `:Consequence` node (§6.4) — provided as the machinery the async
cold-path writer (§8, deferred) will use.

## Read path (§7.2 + §7.4)

`GET /api/scenarios/{id}/graph` **materializes** the scenario's cast + setting from
Postgres into Neo4j (idempotent `MERGE`, drawing `present_at` edges — so the seeded
world appears on first load), then **reads** the subgraph through pre-written,
parameterized Cypher templates in a **read-only** transaction (a stray write is
rejected by the server). Returns `{ available, scenarioId, nodes[], edges[] }`.

## Deferred seams (prerequisites don't exist yet)

- **§8 async turn-writer** — cold-path consequence extraction; needs a turn loop / story engine.
- **§7.1 vector entry-point** — needs an embedding stack + a native vector index.
- **§7.3 Text2Cypher** — `schema_blob` is compiled and ready; live generation awaits a hot-path consumer (staged per §10).
- **Graph visualization UI** — the API-client + types seam exists (`web/frontend/lib/api.ts`, `lib/types.ts`); no graph-viz component yet.

## Environment

```
NEO4J_URI=bolt://localhost:3349      # blank to disable the graph entirely
NEO4J_USER=neo4j
NEO4J_PASSWORD=velora-graph          # matches docker-compose NEO4J_AUTH
```

## Tests

Offline (no container): `app/core/neo4j.py` exposes an injectable `build_driver`,
and the writer/reader take a session argument so a recording fake stands in for
Neo4j (`utils/tests/backend/{data,api,services}/test_{neo4j,graph_types,graph_writer,graph_reader,scenario_graph}.py`).
A conftest autouse fixture disables the graph for the suite; graph tests enable it
explicitly with a fake driver/session. Live validation against the running
container is recorded in `docs/checklist.md`.
