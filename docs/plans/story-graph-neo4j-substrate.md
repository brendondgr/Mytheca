# Plan — The Story Graph: Neo4j Substrate (§6/§7 realization)

> Source brief: `Documents/Plans/5.4_story-graph-structure-prep.md` (the authoritative
> Story-Graph spec). This plan implements the **substrate realization** (§6), the
> **Type Registry** (§1.4), the **write path** (§6.5 / §8 authoring side), and the
> **template read path** (§7.2 + §7.4) — committing Velora to **Neo4j** as the one
> Story Graph. The async turn-writer (§8 cold path), vector entry-point (§7.1), and
> Text2Cypher (§7.3) are built as **documented seams**, not live, because their
> prerequisites (a turn loop / story engine and an embedding stack) do not exist yet.

## 1. Introduction

Every prior graph-prep phase (Character Creator → `3.*`, Setting Creator → `4.*`)
deliberately produced **node properties only — no graph**. This plan builds the
graph itself. It stands up **Neo4j** beside Postgres/Redis as a Docker-managed,
`app.py`-owned data store, adds a lazy/graceful driver client mirroring
`app/core/redis.py`, introduces the **Type Registry** (the semantic type system,
§1.4) in Postgres, and **syncs Character/Setting nodes (and the edge/Consequence
machinery) into Neo4j on create/edit** while **reading the scenario subgraph on
scenario load** through parameterized, read-only Cypher templates.

The connection lifecycle matches the user's directive: the Neo4j **container** is
brought up automatically by `app.py` (like Postgres/Redis), but the **driver
session** is opened lazily — when a Scenario is loaded, or when a Character/Setting
is created/edited. Per the confirmed decisions, graph sync is **best-effort**: if
Neo4j is unavailable (including the no-Docker `pytest` path on SQLite), CRUD still
succeeds and the sync is logged-and-skipped (Neo4j is an *optional* preflight check,
like Redis). The graph **self-materializes from Postgres on demand** (an idempotent
upsert of a scenario's cast+setting before the read), so the seeded Embergate world
appears in the graph the first time a scenario is loaded — no backfill migration.

Architecturally: a new `app/core/neo4j.py` client, an `app/models/graph_type.py` +
`app/services/type_registry.py` registry, an `app/services/graph_writer.py` (write
path, hooked into `services/crud.py`), an `app/services/graph_reader.py` (read path,
exposed at `GET /api/scenarios/{id}/graph`), all offline-testable via an injected
fake Neo4j session (the `comfyui.get_http_client` injectable pattern).

## 2. Gaps & Unanswered Questions

**Resolved with the user (confirmed before planning):**
- **Neo4j posture → graceful/best-effort.** Container auto-managed by `app.py`;
  graph sync never blocks CRUD; Neo4j is an *optional* preflight check; `pytest`
  runs with no Neo4j.
- **Scope → substrate + sync + template read.** Async turn-writer (§8 cold path),
  vector entry-point (§7.1), and Text2Cypher (§7.3) ship as documented seams.
- **Open seam §10 → staged.** User-defined types are written/read on the async/non-hot
  path only until promoted; the registry `status` field is `built_in | experimental |
  trusted`; only `built_in`/`trusted` reach the hot path.

**Assumptions (simple gaps — proceeding):**
- **Custom container** = a Dockerfile extending `neo4j:5.26-community` (≥5.26 is
  required for the dynamic-label `CREATE (n:$(type))` form, §6.2), baking in the
  **APOC** plugin and dynamic-label/security config + a healthcheck. `app.py`'s
  Docker handling is extended to **build** that image (`compose up -d --build --wait`,
  `pull --ignore-buildable`).
- **Host ports** follow Velora's coexistence convention: **3349→7687 (bolt)**,
  **3350→7474 (http)**. Auth `neo4j` / a password from `NEO4J_PASSWORD` (default
  `velora-graph` in `.env.example`, matching the Postgres/Redis "documented default"
  style). Named volume `velora_neo4jdata`.
- **Registry scope:** built-in seed types are **global** (`storyline_id = NULL`,
  `status = built_in`) so every storyline shares them; user-defined types are
  **per-storyline**. Built-ins are seeded idempotently in preflight, independent of
  the Embergate world seed (they must exist on a fresh DB).
- **Graph node id =** the Postgres id (`c_…`, `s_…`); `:Node(id)` is globally unique.
  `storyline` is a node property so a storyline delete can clean its subgraph.
- **No edge-authoring UI exists**, so this phase ships the **edge write machinery +
  Consequence reification + tests**, plus presence/`from`-style edges *derived* at
  scenario-materialization time from the scenario's cast/setting — but authors no
  speculative relationship edges. Live relationship authoring is a seam.
- **Frontend:** add the API-client seam (`getScenarioGraph`, graph-types listing) +
  types + mock + a unit test only. A graph **visualization** UI remains the existing
  deferred item (no new components → no new live a11y surface).

**Complex gaps:** none outstanding — the three load-bearing decisions were confirmed.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Neo4j substrate & connection lifecycle

- **Locations:** `pyproject.toml` (add `neo4j` driver), `web/backend/app/core/config.py`
  (`neo4j_uri` / `neo4j_user` / `neo4j_password` fields + an `is_neo4j_configured`
  helper), `.env.example` (activate the Neo4j vars with documented defaults +
  3349/3350 note), `web/backend/docker/neo4j/Dockerfile` (**new** — custom image
  `FROM neo4j:5.26-community`, APOC + dynamic-label/security config + healthcheck
  helper), `web/backend/docker-compose.yml` (new `neo4j` service: `build:` the custom
  image, `image: velora-neo4j:local`, ports 3349/3350, `NEO4J_AUTH`, named volume,
  `healthcheck`), `app.py` (`ensure_docker_services` → build the custom image:
  `pull --ignore-buildable` + `up -d --build --wait`; keep messaging), new
  `web/backend/app/core/neo4j.py` (lazy `get_driver()` lru_cache singleton, injectable
  `get_driver_factory` for tests, `ping()` graceful, `read_session()` /
  `write_session()` context managers with `default_access_mode` READ/WRITE for §7.4,
  `close_driver()`, `is_enabled()`), `web/backend/app/core/bootstrap.py` (add an
  optional `neo4j` check after `redis`, `required=False`).
- **Rationale:** the store, its lifecycle, and a graceful health gate must exist
  before anything reads or writes the graph. Mirroring `redis.py` (lazy singleton +
  never-raising `ping`) keeps the posture consistent and the test path Docker-free.
- **Tests:** extend `utils/tests/backend/data/test_config.py` (Neo4j fields/defaults);
  new `utils/tests/backend/data/test_neo4j.py` (ping returns `False` when the injected
  driver factory raises — graceful; `is_enabled` reflects config; read/write session
  access-mode is set). No live Neo4j.
- **Action:** Run `uv run pytest utils/tests/backend/data` (+ `ruff`/`mypy`). Once
  green, commit: `[Story Graph Neo4j] (1/5) Complete: Neo4j substrate, custom container, graceful driver client + preflight check.`

### Phase 2 — The Type Registry (§1.4)

- **Locations:** new `web/backend/app/models/graph_type.py` (`GraphTypeDefinition`:
  `id`, `storyline_id` nullable, `kind` node|edge, `type_name`, `field_schema` JSON,
  `description` Text, `valence` nullable, `decay` JSON nullable, `status`; unique
  `(storyline_id, kind, type_name)`), register in `web/backend/app/models/__init__.py`;
  new `web/backend/app/schemas/graph_type.py` (CamelModel Base/Create/Update/Read);
  new `web/backend/app/content/graph_registry.py` (the **seed catalogue** = §5 types:
  Character/Setting/Event/Secret/Faction nodes + their edges `loves/trusts/fears/
  resents/knows/suspects/member_of/at_war_with/allied_with/from/present_at/controls/
  claims/occurred_at/connected_to/involved/subject` with declared valence);
  new `web/backend/app/services/type_registry.py` (`seed_builtin_types(db)` idempotent;
  `list_types` / `get_type` / `create_user_type` / `update_user_type` /
  `delete_user_type`; `validation_rules(db, storyline_id)` → the compiled validation
  artifact; `schema_blob(db, storyline_id)` → schema+descriptions blob for the §7.3
  seam); call `seed_builtin_types` from `bootstrap.run_preflight` (independent of the
  Embergate seed); new `web/backend/app/routes/graph.py` (`GET/POST/PATCH/DELETE
  /api/storylines/{id}/graph/types`), register in `web/backend/app/main.py`.
- **Rationale:** Principle 3 — types are data. The registry is the semantic source of
  truth the writer validates against (§6.5) and the read path is grounded in (§7.3);
  it must exist (with its built-in seed) before any instance is written.
- **Tests:** `utils/tests/backend/data/test_graph_types.py` (model roundtrip, unique
  constraint, `seed_builtin_types` idempotency, edge requires valence);
  `utils/tests/backend/api/test_graph_types.py` (list built-ins + create/patch/delete
  a per-storyline user type; reject an edge type with no valence; `status` defaults to
  `experimental` for user types).
- **Action:** Run `uv run pytest utils/tests/backend/{data,api}` (+ `ruff`/`mypy`).
  Once green, commit: `[Story Graph Neo4j] (2/5) Complete: Type Registry model/schemas/service/routes + built-in seed catalogue.`

### Phase 3 — Graph write path (node/edge sync, Consequence reification, validation)

- **Locations:** new `web/backend/app/services/graph_writer.py`:
  `ensure_constraints(session)` (`CREATE CONSTRAINT … IF NOT EXISTS` on `:Node(id)`
  + per-type indexes, §6.6); `node_props_from_character` / `node_props_from_setting`
  (ORM → `{id,type,label,storyline,metadata…}`); `upsert_node` (registry-validate →
  `MERGE (:Node {id})` + dynamic label `$(type)` §6.2 → set props); `delete_node`
  (DETACH DELETE); `upsert_edge` (validate type+valence → dynamic rel type);
  `attach_consequence` (MERGE a shared `:Consequence` node §6.4 — seam helper);
  top-level **best-effort** `sync_character` / `sync_setting` / `remove_node`
  (catch-all + log, no-op when `neo4j.is_enabled()` is false); injectable session
  factory for tests. Hook these into `web/backend/app/services/crud.py` after commit
  in `create_character` / `update_character` / `delete_character` / `create_setting` /
  `update_setting` / `delete_setting` (lazy import to avoid cycles). Call
  `ensure_constraints` best-effort from `bootstrap.run_preflight` when Neo4j is up.
- **Rationale:** the authoring write path (§6.5) — the only hand-curated writes — must
  validate against the registry and use dynamic labels so built-in *and* user-defined
  types travel the same indexed path. Best-effort hooks honor the graceful posture
  (CRUD never fails because the graph is down).
- **Tests:** `utils/tests/backend/services/test_graph_writer.py` (inject a recording
  fake session: assert `MERGE` keyed on `id`, label = `type`, metadata props mapped;
  registry validation rejects unknown type / missing required field / edge missing
  valence; `:Consequence` attach shape; **graceful no-op when disabled**); extend
  `utils/tests/backend/api/test_characters.py` + `test_settings.py` to assert CRUD
  still returns 201/200 with Neo4j disabled (sync skipped, no error surfaced).
- **Action:** Run `uv run pytest utils/tests/backend` (+ `ruff`/`mypy`). Once green,
  commit: `[Story Graph Neo4j] (3/5) Complete: Graph write path — node/edge sync, Consequence reification, registry validation, best-effort CRUD hooks.`

### Phase 4 — Read path on scenario load (§7.2 templates + §7.4 read-only)

- **Locations:** new `web/backend/app/services/graph_reader.py`:
  `ensure_scenario_materialized(db, scenario)` (idempotent upsert of the scenario's
  cast + setting nodes and derived `present_at`/`from`/`occurred_at`-eligible edges
  from Postgres — so the seed appears on first load); parameterized read-only Cypher
  **templates** `scenario_subgraph(cast_ids, setting_id)`, `presence_casting`,
  `secret_reachability` (§7.2; all via `neo4j.read_session()` → §7.4 enforced);
  `scenario_graph(db, scenario_id)` orchestrator returning a serializable
  `{available, nodes[], edges[]}` (graceful `available:false` when Neo4j is down);
  new schema `ScenarioGraphRead` in `web/backend/app/schemas/scenario.py`; add
  `GET /api/scenarios/{scenario_id}/graph` to `web/backend/app/routes/scenarios.py`.
- **Rationale:** the hot path is reads only (§8), and the built-in traversals are
  pre-written templates (§7.2) run in **read-only transactions** (§7.4 — a stray
  write is rejected by the driver, not by convention). "Connect when loading a
  Scenario" = materialize-then-read on this endpoint.
- **Tests:** `utils/tests/backend/api/test_scenario_graph.py` (Neo4j disabled →
  200 `available:false`, graceful; injected fake session → nodes/edges returned);
  `utils/tests/backend/services/test_graph_reader.py` (template params; materialization
  idempotency; a write attempted inside `read_session()` raises — §7.4 mechanical
  proof).
- **Action:** Run `uv run pytest utils/tests/backend` (+ `ruff`/`mypy`). Once green,
  commit: `[Story Graph Neo4j] (4/5) Complete: Read path — scenario-subgraph templates, read-only enforcement, materialize-on-load, GET /scenarios/{id}/graph.`

### Phase 5 — Frontend seam, docs, and full validation sweep

- **Locations:** `web/frontend/lib/api.ts` (`getScenarioGraph(id)`, `listGraphTypes`,
  `createGraphType`/`updateGraphType`/`deleteGraphType`), `web/frontend/lib/types.ts`
  (`GraphNode` / `GraphEdge` / `ScenarioGraph` / `GraphTypeDefinition`),
  `web/frontend/test/api-mock.ts` (mirror the new calls), one unit test under
  `web/frontend/lib/` or `features/` exercising the new client wrapper; docs sweep —
  `docs/structure.md` (neo4j core module, `docker/neo4j/`, graph model/services/routes),
  `docs/workflow.md` (Neo4j env + ports + Docker line), `docs/architecture.md`
  (substrate + read/write paths + the confirmed decisions), `docs/data-flow.md`
  (graph write-on-author / read-on-scenario-load), `docs/api-contract.md` (graph-types
  + scenario-graph endpoints/shapes), `docs/deployment.md` (Neo4j env), `.env.example`
  (already done Phase 1 — cross-check), `docs/documentation.md` (status + Neo4j
  substrate decision), and a new `docs/story-graph-neo4j.md` (substrate guide,
  mirroring `docs/comfyui-image-generation.md`); `docs/checklist.md` (completed entry +
  the §7.1/§7.3/§8 seams listed as deferred).
- **Rationale:** the contract the future graph-viz/story-engine consumes must be typed
  and mocked; docs must move in the same change that alters behavior (global rule).
- **Tests / validation:** full `uv run pytest` (all backend) + `ruff` + `mypy`;
  `npm test` + `npm run typecheck` + `npm run lint` + `npm run build` in
  `web/frontend`. No new live UI surface (API-client + types only) → record the
  standing live-a11y deferral (shared dev-server constraint) in `docs/checklist.md`.
- **Action:** Run the full backend + frontend validation sweep. Once green, commit:
  `[Story Graph Neo4j] (5/5) Complete: Frontend graph seam + full docs + validation sweep.`
  Then **merge the feature branch into `main`** locally (no push), resolving any
  drift, and confirm `main` is green.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Neo4j driver client | Lazy/graceful singleton, read/write sessions (§7.4), injectable factory | `web/backend/app/core/neo4j.py` |
| Config + env | `neo4j_uri/user/password`, documented `.env.example` defaults | `web/backend/app/core/config.py`, `.env.example` |
| Custom container | `FROM neo4j:5.26-community` + APOC/dynamic-label config + healthcheck | `web/backend/docker/neo4j/Dockerfile`, `web/backend/docker-compose.yml` |
| Docker bring-up | Build the custom image in `app.py`'s preflight (`up --build --wait`) | `app.py` |
| Preflight check | Optional `neo4j` check + constraint bootstrap | `web/backend/app/core/bootstrap.py` |
| Type Registry | Model + schemas + service + routes + built-in seed catalogue (§1.4/§5) | `web/backend/app/models/graph_type.py`, `app/schemas/graph_type.py`, `app/services/type_registry.py`, `app/content/graph_registry.py`, `app/routes/graph.py` |
| Graph write path | Node/edge upsert, `:Consequence` (§6.4), validation, best-effort CRUD hooks | `web/backend/app/services/graph_writer.py`, `app/services/crud.py` |
| Graph read path | Scenario-subgraph templates (§7.2), read-only (§7.4), materialize-on-load | `web/backend/app/services/graph_reader.py`, `app/routes/scenarios.py`, `app/schemas/scenario.py` |
| Frontend seam | API client + types + mock for scenario graph & graph types | `web/frontend/lib/api.ts`, `lib/types.ts`, `test/api-mock.ts` |
| Backend tests | config/driver, registry (data+api), writer (services+api), reader (services+api) | `utils/tests/backend/{data,api,services}/test_neo4j.py`, `test_graph_types.py`, `test_graph_writer.py`, `test_scenario_graph.py`, `test_graph_reader.py` |
| Frontend test | New api-client wrapper unit test | `web/frontend/lib/*.test.ts` |
| Docs | Substrate guide + structure/workflow/architecture/data-flow/api-contract/deployment/documentation/checklist | `docs/story-graph-neo4j.md` + `docs/*.md` |

### Deferred seams (out of scope by design — recorded in `docs/checklist.md`)
- **§8 async turn-writer** (cold-path consequence extraction) — needs a turn loop / story engine.
- **§7.1 vector entry-point** — needs an embedding stack (nomic) + a native vector index.
- **§7.3 Text2Cypher** — the `schema_blob` is compiled and ready; live generation/gating awaits a hot-path consumer (staged per §10).
- **Graph visualization UI** — remains the existing deferred frontend item.
