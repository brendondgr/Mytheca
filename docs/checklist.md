# Mytheca — Checklist

**Genuinely open work only.** Completed work is not tracked here — every shipped feature has a plan under `docs/plans/` and a commit series in git history. This file was previously a 742-line append-only log whose "next steps" section had gone stale enough to contradict its own completed entries (it still listed the NDJSON stream, the validator, and the vector DB as unbuilt long after all three shipped). It is now kept short on purpose.

Verified against the code on 2026-08-04.

## Undesigned decisions

| Decision | State |
| --- | --- |
| **Auth mechanism** | Completely undesigned. There is no `User` model, no auth routes, and no session or token handling anywhere in `web/backend/app/`. JWT-vs-cookie, provider, and whether the app becomes multi-tenant at all are open. Everything downstream — protected routes, per-user libraries, admin surfaces — is blocked on this. |
| **Stat lifecycle across scenarios** | Undecided: reset / persist / partial carry-over between scenarios, and how `hidden`-visibility stats should render. |
| **Deployment target** | Undecided: containerized full-stack on one host vs. split hosting. Nothing is configured. |

## Unbuilt capabilities

- **Relationship / mood stats** — extend the stat machinery to values with a relational target. Relationships currently live only in the graph.
- **Scenario-level stat additions and range overrides** — described in old docs, never implemented; `Scenario` has no such column.
- **Separate `GET /stream` transport** — the turn POST streams NDJSON directly. A standalone stream endpoint with Redis pub/sub fan-out is a seam, not a plan.
- **Cross-encoder rerank** — `RERANK_MODEL = "BAAI/bge-reranker-v2-m3"` is pinned in `rag/const.py` but nothing calls a reranker.
- **Neo4j KG-edge expansion in retrieval** — walking `related` edges during RAG retrieve.
- **RAG-first ingestion + tool-calling authoring** — plan exists (`docs/plans/rag-first-ingestion.md`), not implemented.
- **Text2Cypher read path** — `type_registry.schema_blob()` is compiled but has no consumer.
- **Scene-appraisal signal** — one cheap shared per-turn LLM call giving every speaker a common read of mood and stakes. Revisit only if playtesting shows the current prompt-only situational adaptation is insufficient; weigh against local-model latency.
- **`end_scene` / `move_scene` verbs** — the presence/action bus is built to take them.
- **YAML config loaders** in `app/content/` — only the Markdown stat-guidance loader exists. Entities live in Postgres, so this may simply be unnecessary; decide rather than leave it pending.
- **Dice-based resolution** — explicitly dropped (decision D11), not merely deferred. The `CheckCard` renderer was removed. Reopen only as a deliberate reversal.

## Known defects and rough edges

- **Dead code on the turn path.** `director_agent.who_is_up` and `director_agent.rerank` are the superseded one-shot speaker picker, called only from `utils/tests/backend/agents/test_director_agent.py`. Their prompt keys (`director.who_is_up`, `director.rerank`) remain editable through Options → Prompts, where they silently do nothing. Decide: delete both, or hide the keys.
- **Stale module docstrings elsewhere in the tree.** The three worst offenders were corrected on 2026-08-04 (`services/turn_engine.py` described a "P3 single speaker / `_pick_speaker`" design that no longer exists, `main.py` said the brain and event stream were "added in later phases", and `graph_writer.py` called the edge/consequence writer unused machinery). Other modules have not been swept — treat any "this phase…" docstring as suspect until verified.
- **`TurnContext.subgraph` is fetched but unused.** The scenario subgraph is assembled every turn; its only consumer is a boolean `available` flag in the diagnostic trace. The graph reaches the model solely via `graph_reader.relationship_context()`. Either render the subgraph into the prompt or stop assembling it.
- **Unused graph queries.** `graph_reader.presence_casting` and `graph_reader.secret_reachability` have no callers.
- **`validate_relationship` substring fallback** will mis-bind on nested cast names ("Aldous" vs "Brother Aldous").
- **Ollama is not a detected engine.** `LOCAL_LLM_BASE_URL` defaults to `http://localhost:11434` — Ollama's port — but `services/llm_backend.py` detects only vLLM (`GET /version`) and llama.cpp (`GET /props`). An Ollama user silently gets no reasoning budget.
- **`web/shared/contracts/` is empty** while both layers hand-maintain their own copy of the event contract. Either populate it or drop the directory and document the manual mirror as the intended design.
- **No LICENSE file.** The repository is all-rights-reserved by default.

## Deferred verification

- **Live in-browser accessibility + responsive pass.** Deferred across a long series of UI changes against a persistent environment constraint: a dev server holding 3346, backend CORS pinned to that origin, and unreliable screenshot tooling inside worktrees. Each change was instead verified via green component suites, `next build`, and structural review (native controls, AA tokens, reduced-motion fallbacks). **This is the largest outstanding quality gap** — run one consolidated keyboard + 320/375/768/1024 pass over the whole app once a clean environment is available, rather than re-deferring it per feature.
- **ComfyUI end-to-end render.** The generate → edit → save → reopen loop has never been verified against a running ComfyUI server.
- **Graph node/edge click → detail.** Confirmed by unit tests; could not be driven live because synthetic canvas clicks don't reach `react-force-graph-2d`'s internal hit-testing headlessly.

## Known UI limitations

- Rails are hidden below `lg` (the transcript stays primary); mobile drawers are unbuilt.
- Graph mode is canvas-only below `lg`; the `sr-only` node/edge table remains the data alternative. Graph node clicks are wired for Character only — other types are hover-tooltip only.
- The storyline switcher is hidden below `md`, so mobile cannot switch worlds.
- At the 320px floor the scene-header Inspector icon clips ~7px. There is no page-level horizontal overflow at any width, and everything fits at 375+.

## Research record — deliberate gaps

The retrofit landed on 2026-08-06 (`docs/plans/research-record-retrofit.md`). These
are **decisions, not oversights**, recorded here so they are not mistaken for drift.

- **No CI and no pre-commit hook.** The contract's §7.4/§7.5 mandate both; enforcement
  here is `make validate-research` run by hand. Owner decision — Mytheca has never had
  a `.github/` directory. **This is the one acceptance criterion in §10 left unmet**,
  and the contract's own §7 warns that "convention without enforcement decays".
  Revisit if a second experiment lands without the validator having been run.
  (`docs/research/DECISIONS.md` D-005.)
- **EXP-2026-08-001 is recorded `failed`.** The planner-vs-director ablation could not
  run: no OpenAI-compatible endpoint is configured for this checkout, so every agent
  fell back or raised. 0 LLM calls. `C-005` stays `unsupported`. The harness is built
  and the protocol pre-registered — it is a re-run, not a rebuild.
- **Six of seven claims have no experiment at all.** `docs/research/CLAIMS.md` is the
  backlog; it is meant to look uncomfortable.
- **The audit's P1 study is not started.** 10–14 weeks, critical path 8–11
  (`docs/research/paper/OUTLINE.md`).
- **Degradation mismatch on the turn path.** `director_agent.who_is_up` propagates
  `APIError` where `planner_agent.next_beat` catches it and falls back, though both
  docstrings promise "best-effort; never raises". Found incidentally by the runner,
  not by a test. **Do not delete the dead director code while EXP-2026-08-001 is
  open** — it is the baseline arm.
- **The 2025 Wordplay accepted-paper list is unread.** ~30 papers on exactly this
  topic; the audit names it as the most likely place for a scoop it missed, and both
  remaining novelty claims rest on absence of evidence.

## Housekeeping

- **11 stale git worktrees** under `.claude/worktrees/`, all registered in `git worktree list`, each 25+ days idle with a merged-looking final commit. Prune them along with the ~45 leftover local branches.
