# Live Agentic Streaming — watch worlds build in real time

## 1. Introduction

Today every agentic operation on the **New Storyline** page is a single blocking
HTTP call: `POST /storylines/build` runs ~`2 + 1 + N + M` LLM calls and returns a
finished `ProposedWorld` all at once; `POST /storylines/triage` runs one LLM call and
returns every classification at once. The author stares at a "Building the world…"
button for a minute with no feedback. This plan turns those processes into **live,
progressively-rendered** experiences: as the LLM drafts the storyline, the **Title /
Genre / Tagline / Premise / World Primer** fill into the left pane in front of you,
and a **right-hand column shows each Character and Setting being built one at a time**,
with **image previews appearing** as they render during *Create World*. Triage runs
**per file, live**, each document's category + Draft/RAG filling in as it's classified.

The approach uses **NDJSON over a streaming `POST` response** (`StreamingResponse` on
the backend, `fetch` + `ReadableStream` reader on the frontend). This fits the existing
authoring endpoints (which need a request body, so `EventSource`/SSE-GET is unsuitable)
and matches the project's documented "NDJSON event stream" direction. The blocking LLM
calls stay synchronous — a FastAPI sync generator streams progress events *between*
them, run in Starlette's threadpool with the request-scoped DB session held open for the
duration. No new runtime dependencies.

**Scope.** Primary: the New Storyline **build** + **triage**. The standalone Character
Creator / Setting Creator modal drafts are single JSON-returning LLM calls (no clean
field-by-field stream without fragile partial-JSON parsing) — they keep their existing
working-spinner and are **out of scope** for v1 live field-streaming (noted as deferred).

**Confirmed decisions (from the user):**
- **Triage** runs **per-file** (one LLM call each, genuinely live) — accepts N calls.
- **Images** render **during the *Create World* commit** (review-then-commit kept; only
  kept entities are rendered; previews pop into the right column as each finishes).

## 2. Gaps & Unanswered Questions

- **Transport = NDJSON streaming POST** (not SSE/WebSocket). *Assumption:* authoring is
  request/response with a body and needs no fan-out pub/sub; a streamed POST body is the
  simplest correct fit. No session id / Redis channel is introduced.
- **DB session lifetime under streaming.** *Assumption (verified by design):* FastAPI
  keeps the `get_db` dependency open until the `StreamingResponse` body generator is
  exhausted, so synchronous ORM reads inside the generator are valid. Agents only *read*
  settings/world context during build/triage — no writes — so this is safe.
- **Mid-stream errors.** Once a `200` + NDJSON headers are sent we cannot change status,
  so errors mid-stream are emitted as a terminal `{"type":"error"}` event. *Pre-flight*
  failures (no context provided, LLM unconfigured) are validated **before** the stream
  starts and returned as a normal `400`/`502`, exactly as today.
- **Back-compat.** The existing non-streaming `build_world` / `triage_documents`
  functions and their `/build` + `/triage` routes are **kept** (collectors over the new
  generators) so current tests and any non-streaming caller keep working.
- **Right-column composition.** *Assumption:* triage (on dropped docs) and build run
  sequentially, so the right pane is **state-driven** — it shows the **Context/Triage**
  panel by default and the **live World-build** panel while `building || proposed`.
  Discarding the proposal returns to the Context panel. No third column is added.
- **Per-file triage cost.** Genuinely live, but N LLM calls. *Assumption:* acceptable
  per the user's choice; each call is a small, single-doc prompt; a per-doc failure
  falls back to "Other / RAG-on" without aborting the run.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend: streaming build endpoint

- **Locations:** `web/backend/app/schemas/build.py` (add `BuildEvent` discriminated
  union: `MetaEvent`, `PrimerEvent`, `PlanEvent`, `CharacterEvent`, `SettingEvent`,
  `StatusEvent`, `DoneEvent`, `ErrorEvent`); `web/backend/app/agents/build_agent.py`
  (extract `iter_build_world(...) -> Iterator[BuildEvent]` generator; rewrite
  `build_world(...)` as a thin collector over it so behavior is unchanged);
  `web/backend/app/routes/storylines.py` (new `POST /storylines/build/stream` returning
  `fastapi.responses.StreamingResponse` of `event.model_dump_json() + "\n"`, media type
  `application/x-ndjson`, with up-front 400/502 pre-checks for missing-context and
  unconfigured-LLM before streaming begins).
- **Rationale:** The build is the centerpiece of the request and is naturally staged
  (metadata → primer → blueprint → per-character → per-setting); emitting an event at
  each boundary is the live backbone. Keeping `build_world` as a collector preserves all
  existing tests and the non-streaming route.
- **Events:** `status{stage,message}`, `meta{title,genre,tagline,premise}`,
  `primer{worldPrimer}`, `plan{stats[],characters[]/*concepts*/,settings[]/*concepts*/}`,
  `character{index,total,character}`, `setting{index,total,setting}`, `done{world}`,
  `error{message}`. The `plan` event lets the UI render skeleton cards immediately.
- **Tests:** `utils/tests/backend/agents/test_build_agent.py` — assert
  `iter_build_world` yields the event sequence (mock the agent calls), `build_world`
  collector still returns an equivalent `ProposedWorld`; `utils/tests/backend/api/` — a
  `TestClient` POST to `/storylines/build/stream` yields NDJSON lines ending in `done`,
  and unconfigured-LLM / no-context return `400`/`502` pre-stream.
- **Action:** Run `uv run pytest` for `utils/tests/backend/{agents,api}` (+ ruff/mypy).
  Once green, commit: `Live Agentic Streaming (1/7) Complete: NDJSON streaming build endpoint + iter_build_world generator.`

### Phase 2 — Backend: streaming, per-file triage endpoint

- **Locations:** `web/backend/app/schemas/context_document.py` (add `TriageEvent` union:
  `TriageStatusEvent{name,index,total}`, `TriageItemEvent{item}`, `TriageDoneEvent`,
  `TriageErrorEvent`); `web/backend/app/agents/triage_agent.py` (add
  `classify_document(...)` single-doc helper and `iter_triage_documents(...) ->
  Iterator[TriageEvent]` that resolves the LLM once then loops per doc, yielding a
  `status` then an `item` per file, falling back to "Other/RAG-on" on a per-doc error;
  keep the batched `triage_documents` for the non-streaming route + tests);
  `web/backend/app/routes/storylines.py` (`POST /storylines/triage/stream`).
- **Rationale:** Per-file classification is the only way to show triage genuinely live
  (the batched call returns everything at once). One call per doc, streamed.
- **Tests:** `utils/tests/backend/agents/test_triage_agent.py` — `iter_triage_documents`
  yields a `status`+`item` per doc and a final `done` (mock per-doc LLM); a per-doc LLM
  error yields the fallback item, not an abort; batched `triage_documents` unchanged.
- **Action:** Run `uv run pytest` (+ ruff/mypy). Once green, commit:
  `Live Agentic Streaming (2/7) Complete: per-file streaming triage endpoint + iter_triage_documents.`

### Phase 3 — Frontend data path: NDJSON consumer, API, types, hook wiring

- **Locations:** `web/frontend/lib/types.ts` (mirror `BuildEvent` + `TriageEvent`
  unions; add a `LiveEntity<T>`/`LiveWorld` shape for in-progress cast/settings);
  `web/frontend/lib/api.ts` (add `postNdjson<T>(path, body, signal?)` async-generator
  helper over `fetch` + `res.body.getReader()` + line-buffered `TextDecoder`, reusing
  `API_BASE` and the error-envelope decode of `request`; export `buildWorldStream(...)`
  and `triageDocumentsStream(...)` async generators);
  `web/frontend/features/library/storylineCreator.ts` (a `liveWorldFromEvents` reducer
  helper + `LiveWorld` model: skeleton entries from `plan`, filled from
  `character`/`setting`); `web/frontend/features/library/useStorylineCreator.ts`
  (rewrite `build()` and `triage()` to consume the streams, updating `fields`, `stats`,
  and a new `liveWorld` / `proposed` state incrementally; keep an `AbortController` so
  navigating away cancels).
- **Rationale:** A single reusable NDJSON reader unblocks both build and triage; the hook
  is where incremental state lands so the existing reactive views re-render live.
- **Tests:** `web/frontend/lib/api.test.ts` — `postNdjson` parses a mocked
  `ReadableStream` of NDJSON (incl. a chunk split mid-line) and surfaces error envelopes;
  `web/frontend/features/library/useStorylineCreator.test.ts(x)` — `build()` consuming a
  mocked event stream fills fields then appends each character/setting; `triage()`
  applies each streamed item.
- **Action:** `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`. Once
  green, commit: `Live Agentic Streaming (3/7) Complete: NDJSON stream consumer + streaming build/triage wired into useStorylineCreator.`

### Phase 4 — Frontend UI: live World-build right-column panel

- **Locations:** `web/frontend/components/feature/WorldBuildPanel.tsx` (new — the
  right-column live world: a stage/progress header, **Characters** and **Settings**
  sections rendering `liveWorld` entries as cards with a "drafting…" shimmer for pending
  concepts and filled cards once drafted; portrait/scene-art `<img>` slots that fill in
  Phase 5; absorbs `ProposedWorldReview`'s edit/remove/discard + image-toggle controls,
  shown once the build completes); `web/frontend/features/library/StorylineCreatorView.tsx`
  (right pane becomes state-driven: `building || proposed` → `WorldBuildPanel`, else
  `TriagePanel`; the left fields already bind to `c.fields` and so fill live);
  retire `web/frontend/components/feature/ProposedWorldReview.tsx` (only consumer is the
  creator view) — or keep it composed inside `WorldBuildPanel` if cleaner.
- **Rationale:** The user explicitly wants the cast/settings building in a column to the
  right of the New Storyline fields; this is that column. Cards keyed by index animate in
  as `character`/`setting` events arrive.
- **A11y:** section landmarks + `aria-label`s; live region (`aria-live="polite"`) on the
  stage header; cards keyboard-reachable; portrait `<img>` `alt`; reduced-motion-safe
  shimmer (respect `motion-reduce`).
- **Tests:** `web/frontend/components/feature/WorldBuildPanel.test.tsx` — renders pending
  skeletons from a plan, filled cards after entity events, and the review controls when
  done; `StorylineCreatorView.test.tsx` — right pane swaps Triage↔WorldBuild by state.
- **Action:** `npm test` + typecheck + lint + build; structural a11y/responsive
  reasoning at 320/375/768/1024 (live in-browser pass deferred per the standing
  shared-dev-server constraint — see checklist). Once green, commit:
  `Live Agentic Streaming (4/7) Complete: WorldBuildPanel live right column + state-driven creator pane.`

### Phase 5 — Commit-phase live image previews

- **Locations:** `web/frontend/features/library/storylineCreator.ts` (extend
  `commitWorld` with an optional `onEntity({type,index,patch})` callback — after a
  portrait/scene-art renders, emit the `{portrait}`/`{image}` patch; keep the
  string `onProgress` for the footer status);
  `web/frontend/features/library/useStorylineCreator.ts` (on `onEntity`, patch the
  matching `proposed`/`liveWorld` entry so its preview appears);
  `WorldBuildPanel.tsx` (render the portrait/scene-art once present, with a "rendering…"
  state while the commit is on that entity).
- **Rationale:** Per the user's choice, images render at commit; surfacing each finished
  render into the already-displayed cards delivers "a preview of the image that was
  created" without rendering art for discarded entities.
- **Tests:** `storylineCreator.test.ts` — `commitWorld` invokes `onEntity` with the
  portrait/image patch after each render (api mocked, `generateImages: true`); hook test
  — an `onEntity` patch updates the displayed entity.
- **Action:** `npm test` + typecheck + lint + build. Once green, commit:
  `Live Agentic Streaming (5/7) Complete: live image previews during Create World commit.`

### Phase 6 — Triage live UI

- **Locations:** `web/frontend/components/feature/TriagePanel.tsx` (consume the streamed
  triage state: show a per-file "classifying…" indicator on the in-flight doc and fill
  each row's category + Draft/RAG as its `item` event arrives; the existing flat→grouped
  layout updates live); thread any new `triaging`/`triageProgress` state from
  `useStorylineCreator`.
- **Rationale:** Completes the explicit "see it triaging live" ask in the panel that owns
  the dropped docs.
- **A11y:** `aria-live="polite"` on the triage status; per-row state not color-only.
- **Tests:** `TriagePanel.test.tsx` — rows reflect incremental triage; the in-flight doc
  shows the working state.
- **Action:** `npm test` + typecheck + lint + build. Once green, commit:
  `Live Agentic Streaming (6/7) Complete: live per-file triage in TriagePanel.`

### Phase 7 — Docs sweep, full validation, merge

- **Locations:** `docs/api-contract.md` (the two `/stream` endpoints + NDJSON event
  shapes), `docs/data-flow.md` (the live build/triage flow), `docs/component-map.md`
  (`WorldBuildPanel`; `ProposedWorldReview` status), `docs/documentation.md` (status
  line), `docs/checklist.md` (new entry + deferred in-browser a11y pass), this plan.
- **Rationale:** Docs are part of "done"; the checklist records the deferred live a11y
  pass and any follow-ups (standalone modal streaming, token-level prose streaming).
- **Action:** Run the **full** suites — `uv run pytest` (+ ruff/mypy) and `npm test` +
  typecheck + lint + build. Once all green, commit:
  `Live Agentic Streaming (7/7) Complete: docs sweep + full validation.` Then merge the
  feature branch into `main` (no push), resolving any conflicts.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Build event schema | NDJSON `BuildEvent` discriminated union | `web/backend/app/schemas/build.py` |
| Build generator | `iter_build_world` + collector `build_world` | `web/backend/app/agents/build_agent.py` |
| Build stream route | `POST /storylines/build/stream` (StreamingResponse) | `web/backend/app/routes/storylines.py` |
| Triage event schema | `TriageEvent` union | `web/backend/app/schemas/context_document.py` |
| Triage generator | `iter_triage_documents` + `classify_document` | `web/backend/app/agents/triage_agent.py` |
| Triage stream route | `POST /storylines/triage/stream` | `web/backend/app/routes/storylines.py` |
| NDJSON consumer | `postNdjson` + `buildWorldStream`/`triageDocumentsStream` | `web/frontend/lib/api.ts` |
| Live types | `BuildEvent`/`TriageEvent`/`LiveWorld` | `web/frontend/lib/types.ts` |
| Live state | streaming `build()`/`triage()` + `liveWorld` | `web/frontend/features/library/useStorylineCreator.ts`, `storylineCreator.ts` |
| Live world panel | Right-column live cast/settings + image previews | `web/frontend/components/feature/WorldBuildPanel.tsx` |
| Creator view | State-driven right pane (Triage ↔ WorldBuild) | `web/frontend/features/library/StorylineCreatorView.tsx` |
| Live triage UI | Per-file live classification in the panel | `web/frontend/components/feature/TriagePanel.tsx` |
| Backend tests | build/triage generators + stream routes | `utils/tests/backend/{agents,api}/` |
| Frontend tests | NDJSON parser, hook streaming, panels | `web/frontend/lib/api.test.ts`, `web/frontend/features/library/*.test.ts(x)`, `web/frontend/components/feature/*.test.tsx` |
| Docs | contract, data-flow, component-map, status, checklist, plan | `docs/` |

## 5. Deferred / Follow-ups

- **Standalone Character/Setting modal drafts** stay on their working-spinner (single
  JSON-returning call; field-by-field streaming needs fragile partial-JSON parsing).
- **Token-level prose streaming** (the World Primer "typing out" char-by-char) — would
  need a `stream=true` primitive in `services/llm.py`; not required for staged liveness.
- **Live in-browser a11y/responsive pass (320/375/768/1024)** — the shared working dir's
  dev server (3346) runs under the user's `python app.py`; a second Turbopack server
  clashes on `.next`. Verified structurally + via the suites; run the in-browser pass
  once the dir is free.
