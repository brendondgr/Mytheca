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

- **Re-running world population on an existing world.** `POST /storylines/{id}/populate/stream` is only wired to the create flow (`BuildWorldModal` → `commitWorld`). A world created before the feature, or one whose population partly failed, has no in-app way to top up its cast — the author adds the rest by hand. The endpoint itself is id-scoped and would work; it needs a Library-side entry point (and a decision about whether it appends to, or dedupes against, the existing roster).
- **Population never proposes scenarios.** It writes characters and settings only (each character whole — draft, voice profile, starting stats, portrait); the first scenario is still authored by hand.
- **A stopped build leaves a partly-built world.** *Stop* aborts the stream but does not roll back the rows already committed, and there is no in-app way to resume the run — the author finishes the cast by hand. Tied to the missing re-run entry point above.
- **Relationship / mood stats** — extend the stat machinery to values with a relational target. Relationships currently live only in the graph.
- **Scenario-level stat additions and range overrides** — described in old docs, never implemented; `Scenario` has no such column.
- **Separate `GET /stream` transport** — the turn POST streams NDJSON directly. A standalone stream endpoint with Redis pub/sub fan-out is a seam, not a plan.
- **Cross-encoder rerank** — `RERANK_MODEL = "BAAI/bge-reranker-v2-m3"` is pinned in `rag/const.py` but nothing calls a reranker.
- **Neo4j KG-edge expansion in retrieval** — walking `related` edges during RAG retrieve.
- **RAG-first ingestion + tool-calling authoring** — plan exists (`docs/plans/rag-first-ingestion.md`), not implemented.
- **Text2Cypher read path** — `type_registry.schema_blob()` is compiled but has no consumer.
- **Register-aware narration.** The per-beat `register`/`stakes` from `planner_agent.next_beat` reaches the *character* prompt but not `narrator_agent` — narration still leans on the authored `Setting.atmosphere` for scenery. A grave beat should narrate differently from a light one; the signal is already on `BeatDecision`, so this is threading, not new machinery.
- **A live scene state.** `Setting.current_state` and `Setting.atmosphere` are written at world creation and **never again during play**. The character prompt no longer misrepresents them as the present moment, but nothing yet maintains a rolling "what this place is like now" line from the transcript.
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
- **`sr-only` inside a clipping container is a repo-wide latent bug.** Tailwind's
  `sr-only` is `position: absolute`; with no positioned ancestor its containing block is
  the *initial* containing block, so it is **not** clipped by an `overflow: hidden`
  ancestor and instead grows the **root** scroller. `TriagePanel`'s doc list hit this
  hard (6212px of blank page below the fold for 28 files) and was fixed on 2026-08-11 by
  making the scroller `relative`. **The rest of the tree has not been swept** — any
  `sr-only` (or other absolutely-positioned) element inside a long scrolling list within
  a `h-dvh`/`overflow-hidden` shell can reproduce it. The symptom is
  `documentElement.scrollHeight > clientHeight` while `document.body` is viewport-sized.
- **The context rail is very cramped below `lg`.** With the rails stacked, `TriagePanel`'s
  sticky header (upload target + drop zone + Triage button) consumes almost the whole
  `42dvh` strip, leaving the doc list ~34px of scroll at 320×720 and 375×812 (134px at
  768). Functional — the list scrolls and the page does not overflow — but poor; part of
  the unbuilt mobile-drawer work under *Known UI limitations*.
- **An unreproduced connect failure on the storyline Assistant.** Reported as
  "Could not reach the server." on `/storylines/new` → Assistant → Send, on plain
  localhost with nothing in between, while the local LLM was still generating. That
  string can only come from a rejected `fetch()`, i.e. no response headers ever
  arrived — but the agent stream returns headers in 4–16 ms, so the request must be
  failing at connect time. **Ruled out empirically on 2026-08-11:** backend timeouts
  (300 s, never reached), connect failures under load (60 POSTs at load average 5.3 →
  0 failures), the uvicorn keep-alive boundary race (a sweep across 4.3–5.6 s idle →
  0 rejections), and the dev-server reloader (its supervisor holds the listening
  socket, so a restart neither refuses new connects nor killed an in-flight stream in
  testing). Not reproduced locally. `lib/api.ts` now attaches `TransportFailure`
  (`path`, `elapsedMs`, `attempts`, `cause`, `phase`) to the thrown error and logs it
  — `elapsedMs` is the discriminator, since the browser reports every transport
  failure as an opaque `TypeError`. **Next occurrence: capture that console line.**
- **The blocking generation POSTs still hold a silent socket.** `/storylines/primer`,
  `/storylines/draft`, `/storylines/triage`, and the character/setting/scenario draft +
  art endpoints send **no bytes at all** until generation finishes (measured 7.1 s for
  the primer; minutes on a large local model). The agent *streams* got keep-alive frames
  on 2026-08-11 and the client now retries a connect-time failure once, but a hard idle
  timeout shorter than the generation would still kill these. The fix is to convert them
  to NDJSON streams with keep-alives, mirroring the existing `/triage` + `/triage/stream`
  pair. Not started — waiting on confirmation of which control actually fails in the
  field, since the work is a new endpoint plus UI per call site.
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
