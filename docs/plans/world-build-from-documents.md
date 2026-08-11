# World Build — build the author's people, and survive the connection

## 1. Introduction

Two defects, reported together after the first live builds.

**It invents instead of reading.** `services/world_populate.py` asks `roster_agent`
to *make up* a cast and a set of places from the premise, and never looks at the
context documents the author uploaded and classified. So an author who drops in six
character files and three setting files — files Triage has already bucketed as
Characters and Settings — gets six strangers instead. The retired world build did
this correctly: `extract_agent.extract_entities` mined each attached document for the
subjects it **explicitly names and profiles**, strictly scoped to the author's own
classification (a Character doc yields only named characters; an Other doc is lore
grounding and yields nothing), and drafted one entity per extracted subject from that
document's own text. That is the behavior to restore.

**It loses the connection.** A build runs for many minutes over one long NDJSON
response. When that socket dies the run dies with it — the client reports "Lost the
connection while the server was still working." and the world is left half-built, with
no way to watch or finish the rest. Keep-alive frames were not enough: the run itself
is tied to the request. The fix is to make the run outlive the connection — a
server-side job with a sequenced frame log, a stream that attaches to it and can replay
from any point, and a client that silently re-attaches when the socket drops.

Together: the build makes exactly what the author asked for, tells them what it is
about to make before it starts, and finishes even if the connection does not.

## 2. Gaps & Unanswered Questions

- **Classification is the opt-in.** A document the author (or Triage) put in the
  Characters bucket is a character source — full stop. The vestigial `includeExtract`
  flag is not consulted; asking for a second opt-in is exactly the friction being
  reported. `other`-bucket docs stay lore-only grounding; uncategorized docs are mined
  for either kind.
- **Files win over invention.** When a world has character/setting source documents,
  the build makes *those* and nothing else. Invention becomes an explicit choice the
  author makes in the dialog, offered as the default only when there are no source
  files at all.
- **No cap on the author's own files.** The `maxCharacters` / `maxSettings` bounds
  apply to invention only — silently dropping the author's seventh character file
  would be the same class of bug as inventing one.
- **Assumption:** a run is keyed by storyline. Re-requesting the stream for a storyline
  that is already building attaches to the run in progress rather than starting a second
  one, so a reconnect can never double-build.
- **Assumption:** the job registry is in-process and non-durable. A backend restart
  still ends a run; the client then reports it honestly. Durable jobs (a table, a
  worker) are out of scope and go to `docs/checklist.md`.

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Restore the extraction agent

- **Locations:** new `web/backend/app/agents/extract_agent.py`;
  `web/backend/app/schemas/world_populate.py` (`ExtractedEntity` / `ExtractedEntities`);
  `utils/tests/backend/agents/test_extract_agent.py`.
- **Work:** `extract_entities(db, doc_text, grounding, *, doc_name, kind)` returns the
  characters and settings a single document **explicitly names and profiles**, each with
  a self-contained `source` paragraph drawn strictly from that document. Strict,
  named-only prompt (no inventing, inferring, or expanding lore into people); `kind`
  scopes it to the author's bucket and the off-kind list is cleared defensively; a
  lore/history/glossary document correctly yields nothing. Runs at LOW reasoning effort.
- **Rationale:** this is the piece whose removal caused the invention; it is restored
  from the retired build rather than reinvented.
- **Validation & commit:** `uv run pytest utils/tests/backend/agents`. Commit:
  `[Build From Documents] (1/5) Complete: Restored strict, classification-scoped entity extraction.`

### Phase 2 — The roster comes from the author's documents

- **Locations:** `web/backend/app/services/world_populate.py`;
  `web/backend/app/schemas/world_populate.py` (`source` on the request; a `plan` frame);
  `utils/tests/backend/services/test_world_populate.py`.
- **Work:** before anything is drafted, read the world's persisted context docs and
  sort them by category. Character/setting/uncategorized docs are mined by
  `extract_agent` (concurrently bounded by `authoringConcurrency`, failure-isolated: a
  doc whose reply won't parse is reported and skipped, and a *classified* doc that names
  nothing still yields one entity from the doc itself so the author's file is never
  silently dropped). `other` docs fold into the grounding only. Each entity is drafted
  from its own extracted `source` paragraph, and the source document is linked to the
  created row (`crud.add_document_link`) so provenance is visible. Invention runs only
  when `source="invent"`. A terminal-before-work `plan` frame names exactly what will be
  built and where each entry came from.
- **Rationale:** the author's files, their classification, and their count are the
  build's input — not a suggestion to a model.
- **Validation & commit:** `uv run pytest utils/tests/backend`. Commit:
  `[Build From Documents] (2/5) Complete: The build reads the author's classified documents instead of inventing a cast.`

### Phase 3 — The run outlives the connection

- **Locations:** new `web/backend/app/services/world_populate_runs.py`;
  `web/backend/app/routes/storylines.py`; `web/backend/app/schemas/world_populate.py`
  (`seq` on every frame); `utils/tests/backend/services/test_world_populate_runs.py`,
  `utils/tests/backend/api/test_storyline_populate.py`.
- **Work:** a run is a background thread with its own Session (bound to the request
  session's engine, so tests exercise the real path), appending **sequenced** frames to
  an in-memory log. `POST …/populate/stream` starts a run — or attaches to the one
  already in flight for that storyline — and streams from `fromSeq`, replaying what was
  missed before following live. Completed runs are retained briefly so a reconnect after
  the last frame still sees `done`.
- **Rationale:** a ten-minute build must not be hostage to one socket; replay-from-seq is
  what makes a reconnect lossless.
- **Validation & commit:** `uv run pytest utils/tests/backend`. Commit:
  `[Build From Documents] (3/5) Complete: The build runs server-side and a reconnect replays what it missed.`

### Phase 4 — The client re-attaches, and the dialog says what it will build

- **Locations:** `web/frontend/features/library/storylineCreator.ts` (reconnect loop),
  `web/frontend/features/library/worldBuild.ts` (seq tracking, plan folding),
  `web/frontend/components/feature/BuildWorldModal.tsx` (the plan + the source choice),
  `web/frontend/features/library/useStorylineCreator.ts`, `web/frontend/lib/{api,types}.ts`;
  co-located tests.
- **Work:** `runPopulate` tracks the last `seq` and, on a dropped stream, re-attaches
  from it (bounded retries, brief backoff) — surfacing a failure only once reconnection
  is genuinely exhausted. The dialog counts the author's classified files up front
  ("6 character files · 3 setting files") and offers *Build from my files* (default when
  files exist) or *Invent from the premise*; during the run it shows the `plan` frame's
  named roster so the author sees what is coming before it arrives.
- **Rationale:** the two complaints meet here — the author is told what will be built,
  and a blip no longer ends the build.
- **Validation & commit:** `npm test`, `npm run typecheck && npm run lint`, plus a
  keyboard / contrast / 320-375-768-1024 pass and a live run. Commit:
  `[Build From Documents] (4/5) Complete: The console names what it will build and survives a dropped connection.`

### Phase 5 — Docs, full gate, merge

- **Locations:** `docs/api-contract.md`, `docs/data-flow.md`, `docs/component-map.md`,
  `docs/checklist.md`, `CLAUDE.md`.
- **Validation & commit:** `uv run pytest` + `npm test` + typecheck + lint. Commit:
  `[Build From Documents] (5/5) Complete: Documented document-driven building and the resumable run.`
  Then merge into `main`.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Extraction agent | Strict, named-only, classification-scoped | `web/backend/app/agents/extract_agent.py` |
| Document-driven roster | Sources, per-entity grounding, provenance links | `web/backend/app/services/world_populate.py` |
| Plan frame | What will be built, and from which file | `web/backend/app/schemas/world_populate.py` |
| Run registry | Background run + sequenced frame log + replay | `web/backend/app/services/world_populate_runs.py` |
| Resumable stream | `fromSeq` attach/replay on the populate route | `web/backend/app/routes/storylines.py` |
| Reconnecting client | Re-attach from the last seq | `web/frontend/features/library/storylineCreator.ts` |
| Dialog plan + source choice | Files vs invention, named roster | `web/frontend/components/feature/BuildWorldModal.tsx` |
| Backend tests | Extraction, document roster, no-invention guard, replay | `utils/tests/backend/{agents,services,api}/` |
| Frontend tests | Reconnect, plan rendering, source choice | `web/frontend/features/library/*.test.ts`, `components/feature/BuildWorldModal.test.tsx` |
