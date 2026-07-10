# Agentic Storyline Editing — Conversational, Scoped, Plan→Implement Agent

## 1. Introduction

Today a storyline's own fields (title, genre, tagline, premise, **World Primer**, and the
**stat schema**) are authored either by hand in `StorylineCreatorView` or, on create only, by the
one-shot streaming **"Build the whole world"** flow. There is no way to *talk* to an agent about a
storyline, no plan-before-write gate, and no way to say "only touch the tagline." This plan replaces
the "Build the whole world" entry with a **conversational, scope-aware agent** that lives beside the
storyline form on both the create and edit pages. The human picks which fields the agent may write,
**chats with it first** (in-chat memory), and the agent answers conversationally and — when asked to
change something — returns a reviewable **plan** (proposed new value + rationale per in-scope field;
per-stat before/after/delta for statistics). Nothing is written until the human approves. On edit,
approval applies the plan through the existing validated `PATCH /storylines/{id}` + stat-definition
write paths; on create, approval fills the form and the human commits via the existing "Create World"
path.

The approach fits Velora's grain. Enforcement is **belt-and-suspenders**: the agent's output is shaped
by a dynamically-built response schema + prompt containing *only* the writable fields, and a
**server-side diff guard** (the load-bearing layer, since the local stack is prompt-instructed JSON,
not constrained decoding) rejects any change to a field outside the approved write scope. The stream
reuses the proven **NDJSON-from-POST** transport (`postNdjson` ↔ `StreamingResponse(... x-ndjson ...)`).
The conversation is **client-session memory** (held in React state, sent to the server each turn), with
a one-click **New chat / reset**. The agent owns **only the storyline's own fields** — cast & settings
keep their existing per-entity "Draft with Velora" flows.

---

## 2. Gaps & Unanswered Questions

**Resolved with the user (this session):**

- **"Build the whole world" is replaced, not kept.** The streaming build hero + `WorldBuildPanel` + the
  build/extract stream are removed; the conversational agent becomes the sole agentic entry on the
  storyline create/edit pages. *(User-confirmed.)*
- **Agent scope = storyline's own fields only** — title, genre, tagline, premise, World Primer, and the
  stat *schema* (definitions: ranges, defaults, bands, guidance). Cast & settings stay on their existing
  per-entity draft flows. *(User-confirmed.)*
- **Stat edits: full schema, flagged.** The agent may add/remove stats, change min/max ranges, and edit
  band labels/descriptions + guidance — schema-altering changes are flagged distinctly in the plan as
  higher-risk and route through the clamped stat-definition services. *(User-confirmed.)*
- **Chat memory = client session (in-memory).** The conversation is held in the page's React state and
  sent to the server each turn; it resets on reload. No new DB table or migration. A **New chat / reset**
  control clears the message array and any pending plan. *(User-confirmed.)*

**Assumptions (simple gaps — proceeding):**

- **The design doc's `EntityModal`/three-column premise is superseded by repo reality.** The storyline
  create/edit surface is `features/library/StorylineCreatorView.tsx` (a two-pane shell: left = by-hand
  fields, right = triage/build), *not* `EntityModal` (which owns scenarios only). The agent is integrated
  as a **segmented right pane** — `[ Assistant | Context ]` — where *Assistant* is the new panel and
  *Context* is the existing `TriagePanel` + `ContextBudgetMeter`. This honors the design's "persistent
  panel sharing the screen with the form, re-reading current state each pass" intent without a disruptive
  three-column rebuild.
- **Enforcement layer 1 is best-effort, layer 3 is load-bearing.** The stack uses prompt-instructed JSON
  (`_common.extract_json`); there is no constrained decoding except the unused `extra_body`/`guided_json`
  seam (vLLM only). So the dynamic schema shapes the **prompt** (always) and is passed as `guided_json`
  **only when a vLLM backend is detected** (`llm_backend.detect_backend`); the **server-side diff guard**
  is the guarantee. This preserves the design's belt-and-suspenders intent given the real stack.
- **Two agents, shared core (D-3).** `storyline_editor_agent` (existing storyline) and
  `storyline_creation_agent` (blank/partial start) are separate entry functions with separate system
  prompts, over a shared `_edit_core` (plan schema, dynamic-schema builder, diff guard, LLM call). They
  differ only in prompt + starting state.
- **Stale-read reconcile without a migration.** The apply endpoint reconciles via a **content hash of the
  writable fields** (`baseVersion`) computed by the client from the snapshot it planned against; on apply
  the server recomputes from the DB and **rejects on mismatch** (409) rather than silently overwriting a
  concurrent manual edit. No `updated_at`/`version` column is added to `Storyline`.
- **Field set is 6 and field-agnostic.** `title`, `genre`, `tagline`, `premise`, `worldPrimer`,
  `statistics`. The mechanism is data-driven off a catalog so the set can grow.
- **Streaming = generate-then-chunk.** `llm.chat_complete` returns a full string (no token streaming in
  the stack). The agent computes the full reply, then emits the assistant text (chunked via
  `events.stream.chunk_text` for a live feel) followed by an optional terminal `plan` frame — matching how
  the play turn stream already works.

**Deferred (noted, not v1-blocking):**

- **Read-scope clamping** (D-6) — per-field "visible-context" toggles. Write scope ships fully in v1; read
  scope defaults to "all readable" with the toggle as a P5 stretch, otherwise a documented follow-up.
- **Server-persisted conversations** — client-session memory ships now; a persisted transcript is a future
  follow-up (would add a model + migration + endpoints).

---

## 3. Hierarchical Step-by-Step Instructions

> Branch: `worktree-agentic-storyline-editing` (isolated worktree, merged to `main` in the final phase).
> Backend tests run via the repo-root venv python; frontend via `web/frontend` npm (worktree gotchas).

### Phase 1 — Scope model, plan schema, dynamic response-schema builder + diff guard (backend, pure)

- **Locations:** new `web/backend/app/schemas/storyline_edit.py` (Pydantic: `ScopedFieldSpec`,
  `FIELD_CATALOG`, `FieldScope{writable,readable}`, `ScopeState = dict[field, FieldScope]`, `FieldChange`,
  `StatChange{key,changeType,before,after,delta?,rationale}`, `StoryPlan{changes[],statChanges[],notes?}`,
  `AgentMessage{role,content}`); new `web/backend/app/agents/storyline_edit/scope.py`
  (`response_schema_for(scope) -> dict` — JSON schema whose properties are the writable fields **only**;
  `writable_keys(scope)`, `readable_keys(scope)`, `changed_fields(plan) -> set[str]`,
  `diff_guard(plan, scope) -> None` raising `APIError` when `changed_fields ⊄ writable_keys`);
  new tests `utils/tests/backend/agents/test_storyline_scope.py`,
  `utils/tests/backend/data/test_storyline_edit_schema.py`.
- **Details:** `FIELD_CATALOG` enumerates the six fields with `key`, `label`, `kind`
  (`text` | `primer` | `stats`). `response_schema_for` returns an `object` schema with `additionalProperties:false`
  and exactly the writable keys (statistics expands to the stat-plan sub-schema); for every subset the
  non-scoped keys are structurally absent. `diff_guard` recomputes the changed-field set from a
  proposed/approved `StoryPlan` and rejects (422 `scope_violation`) if any lies outside `writable_keys`.
- **Rationale:** every later phase (agent prompt, plan stream, apply endpoint, all UI) consumes one
  canonical scope object + plan schema + guard; standing them up first with zero behavior change makes the
  new machinery unit-testable in isolation (this is the design's "make violation unrepresentable in the
  type" + "backstop guard").
- **Action:** Run `.venv/bin/python -m pytest utils/tests/backend/agents/test_storyline_scope.py
  utils/tests/backend/data/test_storyline_edit_schema.py` (schema omits non-scoped keys for every subset;
  guard rejects an out-of-scope plan; stat-change shapes validate). Once green, commit:
  `[Agentic Storyline Editing] (1/7) Complete: scope model, plan schema, dynamic response-schema builder + diff guard.`

### Phase 2 — Editor + creation agents + converse/plan NDJSON stream (backend, no writes)

- **Locations:** new `web/backend/app/agents/storyline_edit/core.py` (`converse(...) -> Iterator[frames]`
  shared engine), `agents/storyline_edit/editor.py` (`storyline_editor_agent` + `_EDITOR_SYSTEM`),
  `agents/storyline_edit/creation.py` (`storyline_creation_agent` + `_CREATION_SYSTEM`); frames in
  `schemas/storyline_edit.py` (`AgentStatusFrame`, `AgentMessageFrame`, `AgentPlanFrame`, `AgentErrorFrame`,
  union `AgentEditEvent`); new routes in `web/backend/app/routes/storylines.py`
  (`POST /storylines/{id}/agent/edit/stream`, `POST /storylines/agent/create/stream`, each with a
  `validate_*_inputs` pre-flight + `StreamingResponse(..., media_type="application/x-ndjson",
  headers=_STREAM_HEADERS)`); request schema `StorylineAgentRequest{scope, messages[], fields}`;
  tests `utils/tests/backend/agents/test_storyline_edit_agent.py`,
  `utils/tests/backend/api/test_storyline_agent_stream.py`.
- **Details:** `core.converse` (1) assembles read-scoped context from the request `fields` snapshot +
  (edit) `world_context`/`rag_block` grounding, restricted to `readable_keys(scope)`; (2) builds the
  dynamic schema (`response_schema_for`) + a system prompt that names the writable keys and instructs
  "leave every other field untouched; reply conversationally, and only when the user asks for a change,
  additionally return the plan JSON"; (3) calls `llm.chat_complete` at a **low temperature**
  (deterministic knob) with `reasoning=DEFAULT_AUTHORING_EFFORT`, passing `extra_body={"guided_json": schema}`
  **iff** `detect_backend` is vLLM; (4) parses the reply into `{assistant_message, plan?}` via
  `extract_json`, validates any `plan` against the field validators + `diff_guard` at **plan time**, then
  emits `AgentMessageFrame` (assistant text, chunked via `chunk_text`) and, when present, a terminal
  `AgentPlanFrame`. `messages` carries the client-session history (system/user/assistant). No writes.
  `editor.py`/`creation.py` differ only in system prompt (surgical/minimal vs. generative/coherent) and
  whether a storyline id is required.
- **Rationale:** this is the hardest, newest piece; isolating the plan phase (no writes) makes the
  conversation + plan generation testable end-to-end before any mutation exists.
- **Action:** Run `.venv/bin/python -m pytest utils/tests/backend/agents/test_storyline_edit_agent.py
  utils/tests/backend/api/test_storyline_agent_stream.py` (a change request yields a scope-valid plan; a
  discussion yields a message with no plan; a plan touching a non-scoped key is rejected at plan time; the
  stream serializes frames as NDJSON with a terminal error frame on failure). Once green, commit:
  `[Agentic Storyline Editing] (2/7) Complete: editor + creation agents and the converse/plan NDJSON stream (plan phase, no writes).`

### Phase 3 — Apply endpoint: diff guard + transactional validated writes (edit)

- **Locations:** new `POST /storylines/{id}/agent/apply` in `routes/storylines.py`
  (body `StorylineApplyRequest{scope, plan, baseVersion}` → `StorylineApplyResponse{storyline, applied[]}`);
  new `web/backend/app/services/storyline_apply.py` (`content_hash(fields, writable_keys)`,
  `apply_plan(db, storyline_id, scope, plan, base_version)`); reuse `crud.update_storyline` for text/primer
  fields and `services/stats.py` (`create_stat_definition`/`update_stat_definition`/`delete_stat_definition`,
  which already re-clamp) for statistics; tests `utils/tests/backend/api/test_storyline_agent_apply.py`,
  `utils/tests/backend/services/test_storyline_apply.py`.
- **Details:** `apply_plan` (1) re-runs `diff_guard(plan, scope)` (backstop at implement time); (2)
  recomputes `content_hash` of the writable fields from the current DB row and **rejects with 409
  `stale_storyline`** if it differs from `base_version` (stale-read reconcile — never silently overwrite a
  concurrent manual edit); (3) applies text/primer changes via `crud.update_storyline` and stat changes via
  the stat services (value/range/band/guidance edits, adds, removes — each flagged in the plan), all inside
  one transaction; a partial failure **rolls back the whole plan** (storyline never left half-edited);
  returns the fresh `StorylineRead` + an `applied` audit list. Statistics go through the stat services'
  existing min/max clamping + schema conformance — no bespoke stat path.
- **Rationale:** this closes the plan→gate→implement loop for editing, routed through the same validated
  write paths manual edits use (the form stays the write authority).
- **Action:** Run `.venv/bin/python -m pytest utils/tests/backend/api/test_storyline_agent_apply.py
  utils/tests/backend/services/test_storyline_apply.py` — a single-field edit leaves every other field
  byte-identical (diff across all six); a hand-crafted plan touching an out-of-scope field is rejected even
  when the schema layer is bypassed; an out-of-range stat is clamped/rejected, not written raw; a stale
  `baseVersion` is rejected (409); a mid-plan failure rolls back. Once green, commit:
  `[Agentic Storyline Editing] (3/7) Complete: apply endpoint — diff guard, transactional validated writes, stale-read reconcile.`

### Phase 4 — Frontend: types, API client, pure reducers, agent hook (client-session memory)

- **Locations:** `web/frontend/lib/types.ts` (`StorylineScope`, `FieldScope`, `AgentMessage`,
  `FieldChange`, `StatChange`, `StoryPlan`, `AgentEditEvent`); `web/frontend/lib/api.ts`
  (`storylineAgentEditStream(id, body, signal?)`, `storylineAgentCreateStream(body, signal?)` via
  `postNdjson`; `applyStorylineAgentPlan(id, body)` via `post`; `test/api-mock.ts` mocks); new pure module
  `web/frontend/features/library/storylineAgent.ts` (`defaultScope()`, `foldAgentEvent(state, ev)`,
  `contentHashOf(fields, writableKeys)`, `snapshotFields(creatorState)`); new hook
  `web/frontend/features/library/useStorylineAgent.ts`; co-located tests
  (`storylineAgent.test.ts`, `useStorylineAgent.test.ts`).
- **Details:** `useStorylineAgent({ mode: "create"|"edit", storylineId?, getFields, applyToForm })` holds
  `messages: AgentMessage[]`, `scope: StorylineScope`, `pendingPlan: StoryPlan | null`, `busy`, `error`.
  `send(instruction)` appends the user message, runs the stream (via `useEventStream`/`postNdjson`) folding
  frames with `foldAgentEvent` (assistant deltas → the streaming message; `plan` frame → `pendingPlan`).
  `approve()`: **create** → `applyToForm(pendingPlan)` fills the form; **edit** →
  `applyStorylineAgentPlan(id, {scope, plan, baseVersion: contentHashOf(snapshot, writableKeys)})` then
  surfaces the refreshed storyline. `refine(instruction)` = another `send` carrying prior context (the
  message history *is* the memory). `newChat()` clears `messages` + `pendingPlan` + `error`. `setScope`
  toggles a field's `writable` (and, if the read-scope stretch lands, `readable`).
- **Rationale:** building the state/data layer before the panel keeps the UI phase thin and lets the memory
  + plan + approve logic be unit-tested headlessly.
- **Action:** Run `cd web/frontend && npm test -- storylineAgent useStorylineAgent` + `npm run typecheck`
  (fold reducers; `send`→plan; `approve` create-fills-form vs. edit-calls-apply; `newChat` clears; scope
  toggle). Once green, commit:
  `[Agentic Storyline Editing] (4/7) Complete: frontend types, API client, reducers, and useStorylineAgent (client-session memory + reset).`

### Phase 5 — Frontend: Assistant panel UI + StorylineCreatorView integration; remove Build-the-world UI

- **Locations:** new `web/frontend/components/feature/StorylineAgentPanel.tsx` (+ `ScopeSelector.tsx`,
  or inline); edits to `web/frontend/features/library/StorylineCreatorView.tsx` (remove the "Build the
  whole world" hero block + the `WorldBuildPanel` right-pane branch; right pane becomes a segmented
  `[ Assistant | Context ]`; wire `useStorylineAgent`); **delete**
  `web/frontend/components/feature/WorldBuildPanel.tsx` + its test; trim `useStorylineCreator`/
  `storylineCreator` of build-stream state (`build`, `planConcepts`, `buildStage`, `renderProposalImages`,
  `ProcessProgress` BUILD_STEPS) now that the hero is gone (keep triage, draft-fields, generate-primer,
  commit); co-located tests (`StorylineAgentPanel.test.tsx`, updated `StorylineCreatorView.test.tsx`).
- **Details:** `StorylineAgentPanel` renders: the **scope selector** (checkbox list of the six fields,
  each labeled; statistics flagged as schema-affecting), the **chat transcript** (`role="log"`
  `aria-live="polite"` message bubbles), the **instruction input** (textarea + Send), the **plan renderer**
  (per-field before/after; for statistics a per-stat before/after/delta with **schema-change rows**
  — add/remove/re-range/guidance — visually flagged), and the controls: **Approve & apply** (edit) /
  **Approve & fill form** (create), **Refine**, and **New chat** (reset). Text-field plans also render an
  inline before/after against the center form value. On create, approve calls the creator's field setters
  (`setTitle`/`setGenre`/`setTagline`/`setPremise`/`setWorldPrimer`/`setStats`); on edit, approve calls the
  apply endpoint and re-hydrates from the response. The build hero and `WorldBuildPanel` are removed;
  triage remains under the *Context* segment.
- **Rationale:** this delivers the user-facing loop (discuss → plan → gate → implement) and completes the
  "replace Build-the-world" decision on the client.
- **Action:** Run `cd web/frontend && npm test -- StorylineAgentPanel StorylineCreatorView` +
  `npm run typecheck` + `npm run lint`; **accessibility + responsive pass** (keyboard reach of scope
  checkboxes + Send + Approve + New chat, visible focus, AA `--field`/`--card` tokens, `aria-live` chat
  log, 320/375/768/1024). Once green, commit:
  `[Agentic Storyline Editing] (5/7) Complete: Assistant panel + creator integration; Build-the-world UI removed.`

### Phase 6 — Backend: retire "Build the whole world" (routes, agents, schemas, tests)

- **Locations:** remove `POST /storylines/build` + `POST /storylines/build/stream` from
  `routes/storylines.py`; remove `web/backend/app/agents/build_agent.py` and (after confirming it has no
  other caller) `web/backend/app/agents/extract_agent.py`; remove now-orphaned build schemas in
  `web/backend/app/schemas/build.py` (`ProposedWorld`, `BuildWorldRequest`, `Build*Event`, `BuildDoc`,
  `iter_build`-only helpers) and their frontend mirrors in `lib/types.ts`/`lib/api.ts`
  (`buildWorld`, `buildWorldStream`, `BuildEvent`, `ProposedWorld`, …); delete the corresponding tests
  under `utils/tests/backend/agents/` + `utils/tests/backend/api/`. **Keep** `triage_agent` (independent
  corpus classification), the per-entity `character/setting/scenario_agent` draft functions (used by
  `/characters/draft` etc.), and `services/concurrency.py` (still used by RAG re-index).
- **Details:** trace every reference (`grep` for `build_agent`, `iter_build_world`, `build_world`,
  `ProposedWorld`, `buildWorldStream`, `BuildEvent`, `validate_build_inputs`) before deleting, so no dead
  import or route registration remains — the house rule is no dead placeholders. Removing `build_agent`
  also removes `extract_agent`'s only caller; confirm and delete it too (or keep with a note if a caller
  surfaces).
- **Rationale:** completes the "replace" decision server-side and leaves a clean tree; done **after** P5 so
  the frontend never calls a removed endpoint mid-plan.
- **Action:** Run `.venv/bin/python -m pytest` (full backend suite — all green, no orphaned imports) +
  `cd web/frontend && npm run typecheck` (no dangling build types). Once green, commit:
  `[Agentic Storyline Editing] (6/7) Complete: retired "Build the whole world" server-side + removed dead build code.`

### Phase 7 — Docs, full validation, merge to main

- **Locations:** `docs/routes.md` (agent stream/apply endpoints on `/storylines/new` + `/edit`; build hero
  gone), `docs/component-map.md` (`StorylineAgentPanel`/`ScopeSelector`/`useStorylineAgent` in;
  `WorldBuildPanel` out; `StorylineCreatorView` segmented right pane), `docs/api-contract.md`
  (`POST /storylines/{id}/agent/edit/stream`, `/storylines/agent/create/stream`,
  `POST /storylines/{id}/agent/apply` + the `AgentEditEvent`/`StoryPlan` shapes + `stale_storyline`/
  `scope_violation`; build endpoints removed), `docs/data-flow.md` (converse→plan→gate→apply path, scope
  enforcement layers, client-session memory), `docs/design-system.md` (Assistant panel + scope selector +
  plan renderer tokens), `docs/structure.md` (`agents/storyline_edit/`, `services/storyline_apply.py`,
  `schemas/storyline_edit.py`; build files removed), `docs/documentation.md` (status), `docs/checklist.md`
  (new entry + any deferred read-scope/live-a11y items), CLAUDE.md (backend/frontend component lists);
  this plan.
- **Details:** document the scope object, the three enforcement layers (schema-shaped prompt, guided_json
  when vLLM, load-bearing diff guard), the two agents, the plan→implement loop, in-chat memory + reset, and
  the removal of "Build the whole world". Record the deferred read-scope toggle + server-persisted
  conversation follow-ups and any deferred live-in-browser a11y pass (standing worktree shared-dir/CORS +
  configured-LLM constraint) in the checklist.
- **Rationale:** docs are the source of truth and land with the behavior change; the merge consolidates the
  feature onto `main`.
- **Action:** Full gate — `.venv/bin/python -m pytest`, `cd web/frontend && npm test`, `npm run typecheck`,
  `npm run lint`, `npm run build` (next build). Once green, commit:
  `[Agentic Storyline Editing] (7/7) Complete: docs + full validation.` Then merge
  `worktree-agentic-storyline-editing` into `main`, resolve any conflicts, and re-run the gate post-merge.

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Scope + plan schema | `FIELD_CATALOG`, `ScopeState`, `FieldChange`, `StatChange`, `StoryPlan`, `AgentEditEvent` | `web/backend/app/schemas/storyline_edit.py` |
| Dynamic schema + diff guard | `response_schema_for`, `writable/readable_keys`, `changed_fields`, `diff_guard` | `web/backend/app/agents/storyline_edit/scope.py` |
| Editor + creation agents | Shared `core.converse` + two system prompts / entry functions | `web/backend/app/agents/storyline_edit/{core,editor,creation}.py` |
| Converse/plan stream | Two NDJSON-from-POST endpoints (plan phase, no writes) | `web/backend/app/routes/storylines.py` |
| Apply endpoint + service | Diff guard + transactional validated writes + stale-read reconcile | `web/backend/app/routes/storylines.py`, `web/backend/app/services/storyline_apply.py` |
| Frontend types + API client | Scope/plan/message types; stream + apply client fns | `web/frontend/lib/types.ts`, `web/frontend/lib/api.ts` |
| Reducers + hook | Pure fold + `useStorylineAgent` (client-session memory + reset) | `web/frontend/features/library/{storylineAgent.ts,useStorylineAgent.ts}` |
| Assistant panel | Scope selector + chat + plan renderer + approve/refine/new-chat | `web/frontend/components/feature/StorylineAgentPanel.tsx` (+ `ScopeSelector.tsx`) |
| Creator integration | Segmented `[Assistant|Context]` right pane; build hero removed | `web/frontend/features/library/StorylineCreatorView.tsx` |
| Build removal | `WorldBuildPanel`, `build_agent`, `extract_agent`, build routes/schemas + tests deleted | see Phases 5–6 |
| Backend tests | Scope/schema/guard, agent stream, apply (byte-identical, guard, clamp, stale, rollback) | `utils/tests/backend/{agents,api,services,data}/` |
| Frontend tests | Reducers, hook, panel, creator integration | co-located `*.test.ts(x)` |
| Docs | routes, component-map, api-contract, data-flow, design-system, structure, documentation, checklist, CLAUDE.md | `docs/*.md`, `CLAUDE.md` |

---

## 5. Acceptance / Validation Gate (feature-level)

- A scoped edit with **one** field writable leaves the other five **byte-identical** (verified by diff).
- The dynamic-schema builder omits non-scoped keys for **every subset** of the field set (unit-tested).
- The diff guard **rejects a hand-crafted plan** touching an out-of-scope field even when the schema layer
  is bypassed.
- A statistics edit routes through stat-service validation (an out-of-range value is clamped/rejected, not
  written raw); schema-altering stat changes are flagged distinctly in the plan.
- A World-Primer edit shows full **before/after** in the plan and requires explicit approval.
- An apply against a **stale baseline** is rejected (409), never a silent overwrite.
- **In-chat memory** works across turns (the agent references earlier messages), and **New chat** resets it.
- "Build the whole world" is gone with **no dead references** (backend + frontend), full suites green.
