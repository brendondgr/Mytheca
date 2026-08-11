# Long-Generation Connection Resilience

## 1. Introduction

"Could not reach the server." appears while the local LLM is demonstrably still
generating. That string comes from exactly two places — `lib/api.ts:81` (`request`)
and `lib/api.ts:126` (`postNdjson`) — and **only** when the `fetch()` promise itself
rejects, i.e. when *no response headers ever arrived*. Every backend-side failure
(unconfigured model, upstream 502, scope violation, read timeout) arrives instead as a
normal error envelope or an in-band `error` frame with its own wording. So the failure
is at the transport layer, not in the agent.

Measured on this checkout:

| Path | Time to first byte | Behaviour during generation |
| --- | --- | --- |
| `POST /storylines/agent/create/stream` | 4–16 ms | headers immediately, then **zero bytes for the entire generation** (24 489 ms in one run), then the whole body in a single burst |
| `POST /storylines/primer` (blocking) | **7 112 ms — equal to the total** | **no bytes at all** until generation completes |

Both leave a TCP connection **completely silent for the whole generation** — seconds
here, minutes on a large local reasoning model. Anything in the path that reaps idle
sockets kills it. On the blocking endpoints no headers have arrived yet, so the browser
surfaces that as a rejected `fetch()` → *"Could not reach the server."* — while the LLM
server is still working, exactly as reported. The backend's own `_GEN_TIMEOUT` is 300 s
and uvicorn runs single-process with `reload=True` and the default
`timeout_keep_alive=5`.

This plan removes the silence rather than lengthening a timeout: the agent streams emit
periodic keep-alive frames while the LLM thinks, and the non-mutating generation calls
retry once on a fresh connection when the request provably never reached the server.

## 2. Gaps & Unanswered Questions

- **Which control does the user press when it fails?** The Assistant's **Send** (a
  streaming call) and **❖ Generate primer** (a blocking call) fail through different
  mechanisms and need different remedies. Phase 1 fixes the streaming path completely;
  Phase 2 makes the blocking path survive a *sporadic* drop. If the drop is a hard idle
  timeout at a fixed interval, the blocking endpoints must be converted to streams too
  (`/storylines/primer/stream`, mirroring the existing `/triage` + `/triage/stream`
  pair). **Ask the user before building that**, since it is a new endpoint plus UI work
  and is unnecessary if the failure is the Assistant path.
- **Is a retry safe?** Only for endpoints that write nothing. The agent streams
  explicitly perform no writes (approval is a separate `…/agent/apply` POST), and
  `/primer`, `/draft`, `/triage` are pure generation. `POST /storylines` (create) must
  **never** be retried — a duplicate world. So retry is opt-in per call, not global.
- **Is running the LLM call on a worker thread safe?** Yes, sequentially: the request
  thread blocks on the queue while the worker owns the `Session`, so the two never touch
  SQLAlchemy concurrently.
- **Why not just raise the timeouts?** Nothing is timing out on the backend — the 300 s
  gen timeout was never reached in any measured run. Raising a timeout cannot fix a
  socket that an intermediary closed for being idle.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Stop the agent streams going silent

#### Step 1.1: A reusable keep-alive wrapper
- **Locations:** `web/backend/app/events/stream.py` — a new `with_keepalive(source,
  keepalive, interval)` generator: run `source` on a daemon worker thread feeding a
  `queue.Queue`, and on the request thread emit `keepalive()` every `interval` seconds
  that passes without an item. Exceptions from the worker are re-raised in order, so
  `_agent_stream`'s existing `APIError` → `error`-frame handling is unchanged.
- **Rationale:** The silence is structural — `core.converse` runs the whole LLM call
  before its first `yield`. Only a concurrent producer can keep the socket warm, and
  putting it in `events/stream.py` keeps it available to the other NDJSON streams.

#### Step 1.2: Emit keep-alives on both agent streams
- **Locations:** `web/backend/app/routes/storylines.py` — `_agent_stream` wraps its
  iterator in `with_keepalive`, emitting `AgentStatusFrame(message="Thinking…")`.
- **Rationale:** `AgentStatusFrame` already exists and the client already folds `status`
  to a no-op (`foldAgentFrame`), so this needs no contract change and no UI change.

#### Step 1.3: Tests
- **Locations:** `utils/tests/backend/services/test_stream_keepalive.py` (ordering,
  interval, exception propagation, no keep-alive when the source is fast),
  `utils/tests/backend/api/test_storyline_agent_stream.py` (a slow agent stream emits
  `status` frames before its `message` frames, and the frames still parse).
- **Action:** `uv run pytest utils/tests/backend`. Commit:
  `[Connection Resilience] (1/3) Complete: Agent streams emit keep-alive frames instead of holding a silent socket for the whole generation.`

### Phase 2 — Survive a dropped connection on the client

#### Step 2.1: Opt-in retry for non-mutating calls
- **Locations:** `web/frontend/lib/api.ts` — `request` and `postNdjson` take a
  `retry?: boolean`; when the *initial* `fetch()` rejects they retry once on a fresh
  connection, then throw. Enable it on `storylineAgentCreateStream`,
  `storylineAgentEditStream`, `generateWorldPrimer`, `draftStoryline`,
  `triageDocuments`, `triageDocumentsStream`. Never on the CRUD writers.
- **Rationale:** A rejected `fetch()` means no response was ever received; for a
  write-free endpoint the worst case of a second attempt is a second generation. This
  is the standard remedy for a stale pooled connection (RFC 7230 §6.3.1).

#### Step 2.2: Make the two failures distinguishable
- **Locations:** `web/frontend/lib/api.ts` — keep `network_error` for a request that
  never connected, and report a mid-stream drop as its own message rather than letting a
  bare `TypeError: network error` reach the panel.
- **Rationale:** The user could not tell "the server is down" from "the connection died
  while the server was working". Those have different remedies and the message should say
  which happened.

#### Step 2.3: Tests
- **Locations:** `web/frontend/lib/api.test.ts` — retry-once-then-succeed,
  retry-once-then-fail, no retry when not opted in, and that a mid-stream drop reports
  the connection-lost message.
- **Action:** `npm test` + `npm run typecheck` in `web/frontend`. Commit:
  `[Connection Resilience] (2/3) Complete: Non-mutating generation calls retry once on a fresh connection and name the failure precisely.`

### Phase 3 — Docs, gate, merge

- **Locations:** `docs/api-contract.md` (keep-alive `status` frames on the agent
  streams; clients must ignore unknown frame types), `docs/data-flow.md` (the silent-
  socket measurement and why the keep-alive exists), `docs/checklist.md` (the blocking
  generation endpoints still hold a silent socket — the open item, pending the user's
  answer on which control fails).
- **Action:** `uv run pytest`, `npm test`, `npm run typecheck`, `npm run lint`; live
  re-run of a long Assistant generation confirming `status` frames arrive during the
  wait. Commit + merge to `main`:
  `[Connection Resilience] (3/3) Complete: Documented the keep-alive contract and the remaining blocking-endpoint gap.`

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Keep-alive wrapper | Emits a frame every N idle seconds while a blocking producer works | `web/backend/app/events/stream.py` |
| Agent stream wiring | Both storyline agent streams emit `status` keep-alives | `web/backend/app/routes/storylines.py` |
| Client retry | Opt-in single retry on a connect-time failure | `web/frontend/lib/api.ts` |
| Error clarity | Connect failure vs. mid-stream drop reported distinctly | `web/frontend/lib/api.ts` |
| Backend tests | Wrapper semantics + stream-level keep-alives | `utils/tests/backend/services/test_stream_keepalive.py`, `utils/tests/backend/api/test_storyline_agent_stream.py` |
| Frontend tests | Retry + error-message behaviour | `web/frontend/lib/api.test.ts` |
| Docs | Frame contract, the measurement, the remaining gap | `docs/api-contract.md`, `docs/data-flow.md`, `docs/checklist.md` |
