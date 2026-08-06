# Plan — Backend-Controlled Reasoning Budget (vLLM / llama.cpp)

## 1. Introduction

Mytheca's authoring agents (triage, build-the-whole-world, and the standalone
storyline / character / setting drafters) call a local **reasoning model**. Those
models spend most of their wall-clock on hidden *thinking* tokens before emitting
the visible reply, so a single triage of one document takes 10–20s. We want to cap
that thinking on a **per-operation** basis so triage finishes in ~5s, while still
giving the richer world-build calls a little more room.

Both supported local engines expose a numeric thinking-budget lever, but under
**different request keys** — vLLM uses `thinking_token_budget`, llama.cpp uses
`thinking_budget_tokens`. They also expose distinct, non-OpenAI probe endpoints
(`GET /version` → vLLM, `GET /props` → llama.cpp), so the backend can **auto-detect
which engine is configured** and send the matching key. The approach: a small
detection service with a TTL cache (refreshed by a background poller so it adapts
when the operator swaps engines), a reasoning-effort vocabulary mapped to token
budgets, injection of the right key inside `services/llm.chat_complete`, and
**backend-set effort per call-site** — the user never sees or controls it for
Storyline/Character/Setting creation (per the requirement). Triage = **Low**,
the world build + standalone drafts = **Medium**.

This is **backend-only**: no frontend changes, no new user-facing settings. The
detected engine is exposed read-only via a diagnostic endpoint for observability.

## 2. Gaps & Unanswered Questions

- **Effort → token budget (given by the user):** Low 256, Medium 512, High 1024,
  Very High 2048, Max 4096. Locked.
- **Which effort per call-site:** triage = **Low** (user-specified). World build +
  standalone storyline/character/setting drafts = **Medium** (user said build is
  "Low or Medium"; Medium chosen for the generative calls so quality holds while
  thinking stays bounded). Assumption, proceeding.
- **Lever choice:** use the **numeric thinking budget** for both engines (exact, and
  it covers all five levels uniformly) rather than vLLM's `reasoning_effort` enum
  (which lacks "very high"/"max"). Assumption, proceeding.
- **Unsupported engine / unknown:** if detection returns UNKNOWN (neither probe
  matched), inject **nothing** — behaviour is exactly as today (graceful). The
  thinking budget only takes effect on a detected vLLM/llama.cpp that has reasoning
  enabled server-side (vLLM `--reasoning-parser`; llama.cpp `--jinja --reasoning on`
  with no CLI `--reasoning-budget`). Documented, not enforced.
- **Detection freshness:** a background poller refreshes the cache every
  `LLM_BACKEND_POLL_SECONDS` (default 30); a lazy probe fills a cold cache on first
  use. The poller is disabled under SQLite (the test/offline profile) so the suite
  never hits the network. Assumption, proceeding.
- **Refactor of the earlier triage prompt hack:** the prior ad-hoc `/no_think`
  prefix + tiny `max_tokens` cap on triage is **superseded** by this system and is
  not part of the branch (already reverted); triage relies purely on the Low budget.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Reasoning vocabulary + engine-detection service
- **Locations:**
  - `web/backend/app/schemas/reasoning.py` (new): `ReasoningEffort` str-enum
    (`low`/`medium`/`high`/`very_high`/`max`) + `THINKING_BUDGET: dict[ReasoningEffort, int]`
    (256/512/1024/2048/4096) + a `budget_for(effort)` helper.
  - `web/backend/app/services/llm_backend.py` (new): `InferenceBackend` str-enum
    (`vllm`/`llamacpp`/`unknown`); `detect_backend(base_url, api_key)` — strips a
    trailing `/v1`, probes `GET /version` (vLLM) then `GET /props` (llama.cpp) using
    `llm.get_http_client` (patchable, short timeout), returns the enum; a module TTL
    cache keyed by normalized base URL with `get_backend(base_url, api_key, *, force=False)`;
    `apply_reasoning(body, backend, effort)` — mutates the request body, adding
    `thinking_token_budget` (vLLM) or `thinking_budget_tokens` (llama.cpp), nothing for
    unknown; `refresh_for_config(db)` — resolve stored creds via `settings_store` and
    `get_backend(..., force=True)`.
  - `web/backend/app/core/config.py`: add `llm_backend_poll_seconds: int = 30` and a
    `llm_backend_cache_ttl_seconds: int = 60`. `.env.example`: document both.
- **Rationale:** the vocabulary and the detector are the foundation every later phase
  builds on; isolating them keeps `llm.py` thin and makes them unit-testable offline.
- **Tests:** `utils/tests/backend/api/test_llm_backend.py` — `/version`→vllm,
  `/props`→llamacpp, neither→unknown (MockTransport); `apply_reasoning` body shapes
  per engine + no-op for unknown; `budget_for` mapping; cache returns without a second
  probe inside the TTL and re-probes on `force`.
- **Action:** Run `uv run pytest utils/tests/backend` (+ ruff/mypy on the new files).
  Once green, commit: `Reasoning Budget (1/5) Complete: effort vocabulary + vLLM/llama.cpp detection service.`

### Phase 2 — Inject the budget inside `chat_complete`
- **Locations:** `web/backend/app/services/llm.py` — `chat_complete(...)` gains a
  keyword-only `reasoning: ReasoningEffort | None = None`. When set, resolve the engine
  via `llm_backend.get_backend(base_url, api_key)` (cached) and call
  `llm_backend.apply_reasoning(body, backend, reasoning)` before sending. Unchanged
  when `reasoning is None`.
- **Rationale:** one choke-point — every agent already funnels through `chat_complete`,
  so wiring here means call-sites only pass an effort, not engine logic.
- **Tests:** extend `utils/tests/backend/api/test_llm.py` — a combined MockTransport
  handler answering the detection probe (`/version` or `/props`) and `/chat/completions`;
  assert the chat body carries the right budget key for the detected engine, and carries
  nothing when the probe matches neither.
- **Action:** Run `uv run pytest utils/tests/backend/api/test_llm.py` (+ ruff/mypy).
  Commit: `Reasoning Budget (2/5) Complete: chat_complete injects the engine-specific thinking budget.`

### Phase 3 — Backend-set effort at every authoring call-site
- **Locations:**
  - `web/backend/app/agents/_common.py`: add `DEFAULT_AUTHORING_EFFORT = ReasoningEffort.MEDIUM`
    (single source for the non-triage default).
  - `web/backend/app/agents/triage_agent.py`: pass `reasoning=ReasoningEffort.LOW` on both
    `chat_complete` calls (batch + per-file).
  - `web/backend/app/agents/storyline_agent.py`, `character_agent.py`, `setting_agent.py`:
    each public draft/primer/prompt/stat function gains
    `reasoning: ReasoningEffort = DEFAULT_AUTHORING_EFFORT` and forwards it to
    `chat_complete`. (User has no UI lever — the value is fixed in the backend.)
  - `web/backend/app/agents/build_agent.py`: pass `reasoning=ReasoningEffort.MEDIUM`
    on its own blueprint `chat_complete` and into the `storyline/character/setting`
    draft calls it makes.
- **Rationale:** this is where the user-visible speedup lands — triage drops to Low,
  the world build stays at Medium — all server-side, none of it reaches the client.
- **Tests:** extend `test_triage_agent.py` (assert the per-file/batch chat body carries
  the Low budget for a detected engine) and `test_build_agent.py` (assert Medium). Reuse
  the combined probe+chat handler from Phase 2.
- **Action:** Run `uv run pytest utils/tests/backend/agents` (+ ruff/mypy).
  Commit: `Reasoning Budget (3/5) Complete: triage=Low, build + standalone drafts=Medium (backend-set).`

### Phase 4 — Background poller + diagnostic endpoint
- **Locations:**
  - `web/backend/app/main.py`: in `lifespan`, start an `asyncio` task that every
    `llm_backend_poll_seconds` runs `llm_backend.refresh_for_config` via
    `asyncio.to_thread` (best-effort, never crashes the app), cancelled on shutdown;
    **skipped when `get_settings().is_sqlite`** so the test profile never polls.
  - `web/backend/app/schemas/settings.py`: `LlmBackendResponse` (detected `backend` +
    the `budgets` map).
  - `web/backend/app/routes/options.py`: `GET /options/llm/backend` returning the cached
    detection for the configured endpoint (force-refresh once if cold).
- **Rationale:** satisfies "check every N seconds so the server adapts to changes" and
  makes the auto-detection observable without adding a user setting.
- **Tests:** `utils/tests/backend/api/test_options.py` — `GET /options/llm/backend`
  returns the engine via a mocked probe and the budgets map; a direct single-iteration
  test of the refresh function (no real network, MockTransport).
- **Action:** Run `uv run pytest utils/tests/backend/api/test_options.py` (+ ruff/mypy).
  Commit: `Reasoning Budget (4/5) Complete: lifespan poller refreshes detection + GET /options/llm/backend.`

### Phase 5 — Docs, full validation, merge to main
- **Locations:** `docs/api-contract.md` (new endpoint + reasoning-injection note),
  `docs/data-flow.md` (detection + budget injection in the authoring flow),
  `docs/workflow.md` + `.env.example` (the two new env vars),
  `docs/documentation.md` (status line), `docs/checklist.md` (this entry).
- **Rationale:** docs must move in the same change (project rule); the merge lands the
  feature on `main` locally as the user asked (no push).
- **Tests:** full `uv run pytest` + `uv run ruff check .` + `uv run mypy web/backend`.
  Frontend untouched (no run needed; note it).
- **Action:** Run the full backend suite green, then merge `feat/reasoning-budget` → `main`
  locally (resolve any concurrent-session conflicts), commit:
  `Reasoning Budget (5/5) Complete: docs + full validation + merge to main.` Do not push.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Reasoning vocabulary | Effort enum + token-budget map | `web/backend/app/schemas/reasoning.py` |
| Engine detector | vLLM/llama.cpp probe, TTL cache, budget injector | `web/backend/app/services/llm_backend.py` |
| Config | Poll interval + cache TTL env vars | `web/backend/app/core/config.py`, `.env.example` |
| chat_complete wiring | Per-call thinking-budget injection | `web/backend/app/services/llm.py` |
| Call-site efforts | triage=Low, build+drafts=Medium (backend-set) | `web/backend/app/agents/*.py` |
| Poller + endpoint | Lifespan refresh + `GET /options/llm/backend` | `web/backend/app/main.py`, `routes/options.py`, `schemas/settings.py` |
| Tests | Detection, injection, per-call effort, endpoint | `utils/tests/backend/api/test_llm_backend.py`, `test_llm.py`, `test_options.py`, `utils/tests/backend/agents/test_triage_agent.py`, `test_build_agent.py` |
| Docs | Contract, data-flow, workflow, status, checklist | `docs/*.md` |
