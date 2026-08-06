# Plan — Establish `docs/research/` as the Single Research Record

## 1. Introduction

Mytheca is a working engine with **zero evaluation**. The one research artifact in
the repository — `docs/research/mytheca-research-audit.md` (904 lines) — establishes
this as a verified finding and then does something more useful: it pre-writes almost
every ledger the target structure asks for. Its §1.6 is a claims table of seven
falsifiable propositions; §4 is an eight-entry gap inventory; §9 is a full
bibliography; §7 is an evaluation design detailed enough to serve as a `PROTOCOL.md`.

This plan retrofits `docs/research/` into the structure defined by
`RESEARCH_RECORD_INSTRUCTIONS.md` — ledgers, templates, an experiment contract,
scaffolding and validation tooling — seeds every ledger from the audit rather than
from invention, and records **one real experiment end to end**: the C5 planner
ablation, chosen because both arms already exist in the codebase
(`planner_agent.next_beat` vs. the dead-code `director_agent.who_is_up`) and both
are already tested, making it the cheapest genuine experiment available.

It also trims `docs/plans/`, which is 892 KB across 76 files — 63% of all of `docs/`
— of which only four are referenced by any live document.

**Mode: A (worktree).** Work happens in the existing worktree
`.claude/worktrees/research-record-planning-6032a7` on branch
`claude/research-record-planning-6032a7`, merges to `main` at the end, and the
worktree is removed. Per `docs/checklist.md`, eleven stale worktrees are already
outstanding — this one does not become the twelfth.

**Scope discipline.** §5 of the instruction set makes this a *retrofit*: no `src/`
restructuring, no module renames, no README rewrite. Phase 4's baseline arm is built
by calling `director_agent.who_is_up` **from the runner**, so no production code
under `web/backend/app/` is modified anywhere in this plan.

---

## 2. Gaps & Unanswered Questions

### Resolved by the user at planning time

| Question | Decision |
| --- | --- |
| How far does enforcement go (§7.4/7.5 mandate CI + pre-commit on a repo with no `.github/`)? | **Scripts + Makefile only.** No GitHub Actions, no pre-commit hook. Recorded as a deliberate deferral in `docs/checklist.md`, not silently skipped. |
| What happens to `docs/plans/`? | **Archive the unreferenced files** to `docs/plans/archive/`. Nothing deleted. |
| Which experiment satisfies acceptance criterion #7? | **C5 planner ablation, executed for real** — not scaffolded. |

### Assumptions taken (simple gaps)

- **A1 — Research tooling tests get a new folder.** `docs/skills/global-project-rules/SKILL.md` fixes backend tests to
  `utils/tests/backend/{api,agents,services,rag,data}/`. Research tooling is not
  backend app code and fits none of the five. Assumption: create
  `utils/tests/tools/` for it. `[tool.pytest.ini_options] testpaths = ["utils/tests"]`
  already collects it with no config change. `docs/structure.md` and `CLAUDE.md`
  are updated in the same phase that creates it.
- **A2 — The audit file stays where it is.** §2 of the instruction set says "do not
  invent sibling directories" and does not list a home for a meta-document.
  `mytheca-research-audit.md` is not an experiment and must not be forced into an
  experiment folder. It stays at `docs/research/` root and
  `docs/research/README.md` names it as the provenance source for every seeded ledger.
- **A3 — Claim IDs are renumbered, not renamed.** The audit uses `C1`–`C7`; the
  instruction template uses `C-001`. `CLAIMS.md` uses `C-001`…`C-007` mapped 1:1,
  with the audit's original label preserved in a Notes column so §1.6 stays greppable.
- **A4 — Basename matching produced one false positive.** `docs/plans/archive/comfyui-image-generation.md`
  appears referenced only because `docs/comfyui-image-generation.md` shares its
  basename. Phase 0 must match on the **path prefix `docs/plans/`**, not the
  basename, and re-derive the keep-list at execution time rather than trusting
  the list below verbatim.
- **A5 — Two new Python dependencies.** `pyyaml` (the manifest format is YAML; the
  validator and index generator must parse it) and `matplotlib` (§4 requires every
  figure to have a committed generator producing `.svg` **and** `.pdf`).
  `pydantic` is already a dependency, so the manifest schema needs nothing new.
  Both go in a `research` dependency group so the runtime backend is unaffected,
  and both are recorded in `docs/workflow.md` + `docs/architecture.md` per the
  "every dependency needs a defined job" rule.

### Complex gaps — flagged

- **G-A — LLM availability at Phase 5 is not guaranteed.** The C5 ablation needs a
  reachable OpenAI-compatible endpoint, and per project memory the local model is a
  reasoning model requiring ≥8000 max tokens and ≥3 minute timeouts or it 502s.
  Phase 5 cannot be verified as green until it actually runs.
  **Handling — no human intervention needed to proceed:** Phases 0–4 are entirely
  independent of the LLM and land first. If Phase 5 finds no reachable endpoint or
  the run does not complete, the experiment is recorded with `status: failed`, an
  honest `ISSUES.md` naming exactly what could not be obtained, and empty
  `metrics.values`. That is the behaviour §3.4 explicitly mandates, and the
  validator is built in Phase 3 to accept it. The claim ledger then keeps
  `C-005` at `unsupported`. **This will be reported plainly, not papered over.**
- **G-B — Data-store requirements for a headless run.** `turn_engine` reads and
  writes Postgres; Redis, Neo4j and Qdrant are best-effort and degrade to no-ops.
  Assumption: the runner uses the same Postgres the app uses (via `python app.py`
  owning Docker — never `docker compose` directly). If Postgres proves unavailable,
  fall back to the in-memory SQLite path the test suite already uses and record
  that substitution in the manifest's `environment` block and `ISSUES.md`, since
  it is a genuine deviation from the production configuration.
- **G-C — Scene corpus is synthetic and small.** The audit's §7 minimum viable
  contribution calls for 3 private worlds × 25 scenes × 3 seeds. That is a
  10–14 week study, not this plan. EXP-2026-08-001 uses the shipped **Embergate**
  seed world at a deliberately small N. **This is a deliberate under-powering** and
  `RESULTS.md` §5 "Threats to validity" must say so in those words. The experiment
  proves the *record structure* works end to end and produces a real preliminary
  number; it does not settle C-005. **Human intervention is needed** before any of
  this is treated as a publishable result.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 0 — Context reduction: archive `docs/plans/`

- **Locations:** `docs/plans/` → new `docs/plans/archive/`; `docs/plans/archive/README.md` (new);
  `CLAUDE.md:58` (the "Feature plans / handoffs" routing row); `docs/structure.md`.
- **Rationale:** `docs/plans/` is 892 KB / 10,590 lines across 76 files — 63% of
  `docs/` — and `CLAUDE.md` instructs every agent to `ls docs/plans/` for routing.
  Cutting the routing surface from 76 entries to 5 is the single largest context
  win available, and archiving rather than deleting preserves the design provenance
  the audit repeatedly cites.
- **Steps:**
  1. Re-derive the keep-list by grepping for the literal string `docs/plans/<name>`
     (path prefix, **not** basename — see A4) across `CLAUDE.md`, `README.md`,
     `docs/*.md`, `docs/skills/`, `docs/briefings/`. Expected result, to be
     confirmed not assumed: `rag-first-ingestion.md` (cited by `docs/checklist.md`
     as the one genuinely open item), `mytheca-rag-implementation.md`
     (`docs/rag.md:10`), `story-graph-neo4j-substrate.md`
     (`docs/story-graph-neo4j.md:7`), `turn-loop-runtime.md`
     (`docs/api-contract.md:677`).
  2. `git mv` every non-keep plan into `docs/plans/archive/`. `.gitkeep` stays at
     `docs/plans/`. This plan file stays at `docs/plans/` — it is active work.
  3. Write `docs/plans/archive/README.md`: these are historical handoffs for shipped
     features, retained for provenance, **not to be read during routing**; the
     commit series in git history is the authoritative record.
  4. Fix intra-archive cross-links. Several archived plans reference each other by
     `docs/plans/<name>.md` (e.g. `build-extract-stage-fix.md` → `rag-first-ingestion.md`,
     `pov-character-switching.md` → `turn-loop-runtime.md`). Rewrite each to its new path.
  5. Amend `CLAUDE.md:58` to route active plans to `docs/plans/` and mark
     `docs/plans/archive/` explicitly as historical. Update the `docs/plans` entry
     in `docs/structure.md`.
- **Validation:** grep the whole tree for `docs/plans/` and confirm every hit
  resolves to a file that exists. Docs-only change, but run the full gate once as a
  baseline so later phases have a known-green starting point.
- *Action: Run `uv run pytest` and `cd web/frontend && npm test`. Once green, commit locally:*
  `[Research Record] (1/7) Complete: Archived 72 shipped-feature plans to docs/plans/archive/ and repointed routing.`

---

### Phase 1 — Skeleton, agent contract, and templates

- **Locations:** all new under `docs/research/` — `README.md`, `AGENT_INSTRUCTIONS.md`,
  `templates/experiment/{manifest.yaml,PROTOCOL.md,RESULTS.md,figures/.gitkeep}`,
  `templates/DECISION.md`, `templates/negative_result.md`,
  `experiments/.gitkeep`, `figures/sources/.gitkeep`, `tables/.gitkeep`,
  `datasets/{DATASETS.md,cards/.gitkeep}`,
  `paper/{OUTLINE.md,venue-targets.md,checklists/.gitkeep}`.
  Plus root `.gitattributes` (new) and an addition to `.gitignore`.
- **Rationale:** §2's structure and §3's experiment contract must exist before
  anything can be seeded into them or validated against them. `AGENT_INSTRUCTIONS.md`
  is installed first because every later phase — and every future agent — is
  supposed to be reading it as the contract.
- **Steps:**
  1. `AGENT_INSTRUCTIONS.md` — install `RESEARCH_RECORD_INSTRUCTIONS.md` as the
     in-repo contract, with a short Mytheca-specific preamble recording the three
     deliberate deviations: no CI (§7.4) and no pre-commit (§7.5) by decision;
     the audit lives at `docs/research/` root (A2); `make` is introduced here as a
     new root entrypoint alongside `app.py`.
  2. `README.md` — what the directory is, how to add an experiment, and the pointer
     to `mytheca-research-audit.md` as the provenance source for every seeded ledger.
  3. `templates/experiment/manifest.yaml` — the full §3.1 schema, every field
     present with placeholder values and the LLM block included (Mytheca is an LLM
     system; that block is never omitted here).
  4. `templates/experiment/PROTOCOL.md` — the eight §3.2 headings in order.
     `templates/experiment/RESULTS.md` — the eight §3.3 sections in order.
  5. `templates/DECISION.md` (Appendix B shape), `templates/negative_result.md`,
     and an `ISSUES.md` template stub (Appendix C shape) inside the experiment template.
  6. `.gitattributes` — mark `*.svg` as text/diffable, `*.pdf` binary. `.gitignore` —
     exclude raw run artifacts over the §7.6 threshold from `docs/research/`
     (checkpoints, large parquet, untrimmed logs) while keeping `.svg`, `.json`, `.csv` tracked.
- **Validation:** `tree docs/research` matches §2 exactly, with no invented siblings.
- *Action: Run `uv run pytest` and the frontend suite (no behavioural change expected; confirms nothing regressed). Once green, commit locally:*
  `[Research Record] (2/7) Complete: Created the docs/research skeleton, agent contract, and experiment templates.`

---

### Phase 2 — Seed the ledgers from the audit

- **Locations:** `docs/research/{CLAIMS.md,OPEN_QUESTIONS.md,RELATED_WORK.md,DECISIONS.md}`,
  `docs/research/paper/{OUTLINE.md,venue-targets.md}`,
  `docs/research/paper/checklists/{artifact-evaluation.md,minimum-viable-contribution.md}`,
  `docs/research/datasets/DATASETS.md`.
  Source for all of it: `docs/research/mytheca-research-audit.md`.
- **Rationale:** §9.7 says seeding `CLAIMS.md` "immediately surfaces the real
  experiment backlog". Here the backlog already exists in analysed form — every
  entry below is a transcription with a citation back to an audit section, never an
  invention. This is the phase that makes the directory worth having.
- **Steps:**
  1. `CLAIMS.md` — the Appendix A table. `C-001`…`C-007` transcribed from audit
     §1.6 (C1 voice distinctness · C2 think→speak · C3 stat clamping · C4 retrieval
     gate · C5 ReAct planner · C6 consistency guard · C7 reflection/disposition).
     **All seven start `unsupported`** — that is the honest state, and §5.2's
     "the research novelty, as currently framed, is close to zero" is why. Evidence
     and Artifact columns are `—`. Notes column carries the audit's original label
     and the "evidence that would establish it" summary.
  2. `OPEN_QUESTIONS.md` — G1–G8 from audit §4, each with its why-it-stayed-open
     rationale and whether Mytheca addresses it. Plus the §6.4 disqualifiers that
     are still present, and the missing LICENSE noted in `docs/checklist.md`.
  3. `RELATED_WORK.md` — audit §9's five bibliography subsections, with the
     one-line "how it differs from us" per entry drawn from §3 (Closest Prior Work).
     A **scoop watch** section seeded with the five systems §0 names as already
     publishing this architecture: IBSEN, MAGNET/ATLAS, PANGeA, Narrative World
     Model, Open-Theatre. Carry the audit's ⚠ markers for citations it could not
     verify (§10.2) — do not silently launder unverified references into a clean list.
  4. `DECISIONS.md` — dated ADRs in the Appendix B shape, each traceable to an audit
     section: D-001 `docs/research/` is the single research record (this retrofit);
     D-002 P1 (voice distinctness) is the chosen path over P2/P3/P4 (§7 ranking);
     D-003 the primary metric is **not** an LLM-as-judge (§7, PersonaEval
     arXiv:2508.10014); D-004 no famous fictional characters in evaluation
     (§7, arXiv:2603.03915); D-005 no CI/pre-commit enforcement in this retrofit
     (user decision, this session); D-006 evaluation worlds stay private and
     uncommitted for contamination hygiene (§6.4 #5).
  5. `paper/OUTLINE.md` — audit §7 P1's structure: research question, what carries
     over, what must be built (W3/W4/W6/W8), evaluation design, limitations.
     `paper/venue-targets.md` — §8's Tier 3/2/1 with constraints and the shared-task list.
  6. `paper/checklists/minimum-viable-contribution.md` — §7's MVC checklist verbatim
     as a live to-do. `paper/checklists/artifact-evaluation.md` — §8's badge
     requirements, including that GitHub alone does not satisfy *Available* and an
     archival DOI is required.
  7. `datasets/DATASETS.md` — state plainly that **no evaluation dataset exists yet**;
     record the Embergate seed world (`web/backend/app/core/seed.py`) as the only
     currently available scene source and note it is shipped-with-the-repo, hence
     contaminated for any held-out use. Add one `cards/` datasheet template.
- **Validation:** every claim, gap and bibliography entry carries a back-reference
  to an audit section; no number, citation or claim appears that is not in the audit.
- *Action: Run the full gate. Once green, commit locally:*
  `[Research Record] (3/7) Complete: Seeded CLAIMS, OPEN_QUESTIONS, RELATED_WORK, DECISIONS and paper/ from the research audit.`

---

### Phase 3 — Scaffolding, validation, and index tooling

- **Locations:** new `utils/scripts/research/` — `__init__.py`, `manifest_schema.py`,
  `new_experiment.py`, `validate_research.py`, `gen_index.py`, `make_figures_lib.py`.
  New root `Makefile`. New `utils/tests/tools/{__init__.py,test_research_validator.py,test_research_scaffold.py}`.
  `pyproject.toml` (new `research` dependency group).
- **Rationale:** §7 opens with "convention without enforcement decays". The user
  scoped enforcement to scripts + Makefile, so these three scripts *are* the whole
  enforcement layer and have to be genuinely strict. Building them before the first
  experiment means the experiment is validated by the same tool everything else will be.
- **Steps:**
  1. `uv add --group research pyyaml matplotlib`. Nothing is added to the runtime
     `dependencies` list — the backend must not gain weight from this.
  2. `manifest_schema.py` — a Pydantic model of the §3.1 schema. Required blocks:
     `code`, `config`, `data`, `environment`, `compute`, `metrics`. Status enum
     `planned|running|complete|failed|superseded`. Optional `llm` block.
  3. `new_experiment.py` (`make new-experiment SLUG=x`) — allocates the next
     `EXP-<YYYY>-<MM>-<NNN>` from `experiments/`, copies `templates/experiment/`,
     pre-fills date, `git rev-parse HEAD`, current branch, and a real
     `git status --porcelain` dirty check.
  4. `validate_research.py` (`make validate-research`) — every §7.3 failure
     condition: missing `manifest.yaml`/`PROTOCOL.md`/`RESULTS.md`; schema failure;
     `status: complete` with empty `metrics.values`; a manifest-listed figure with
     no file, or a figure file not listed; a figure folder with no generating
     script; a `data/` pointer without a hash; a `supports_claims` ID absent from
     `CLAIMS.md`; a stale `INDEX.md`. Non-zero exit on any.
     **`status: failed` and `status: planned` must be allowed to have empty metrics**
     — §3.4 requires failures to stay recorded, and G-A depends on this.
  5. `gen_index.py` (`make research-index`) — walks `experiments/*/manifest.yaml`,
     emits the §5 table (ID · date · title · status · primary metric · claims · link)
     into `INDEX.md` with a "generated, do not hand-edit" header.
  6. `Makefile` — `new-experiment`, `validate-research`, `research-index`, `figures`,
     plus a `help` default. It wraps `uv run`; it does **not** replace `app.py`,
     which keeps owning Docker and the dev servers.
  7. Tests in `utils/tests/tools/`: the validator passes on a well-formed fixture and
     **fails on a deliberately broken one** (acceptance criterion #3 — assert the
     failure, don't just assert the pass); the scaffolder produces a validator-passing
     folder (criterion #2); the index generator is idempotent.
- **Validation:** `uv run pytest utils/tests/tools/` green; `make validate-research`
  passes on the templates; manually break a fixture and confirm a non-zero exit.
- *Action: Run `uv run pytest` (full suite, confirming the new folder is collected and the existing 784 still pass) and the frontend suite. Once green, commit locally:*
  `[Research Record] (4/7) Complete: Added research scaffolding, validator and index generator with a Makefile and tool tests.`

---

### Phase 4 — Headless runner and EXP-2026-08-001 protocol

- **Locations:** new `utils/scripts/research/run_scene.py` and
  `utils/scripts/research/record.py` (the §7.2 auto-capture helper);
  new `docs/research/experiments/EXP-2026-08-001-planner-vs-oneshot-director/`.
  Reads only: `web/backend/app/services/turn_engine.py`,
  `web/backend/app/agents/planner_agent.py`,
  `web/backend/app/agents/director_agent.py`,
  `web/backend/app/services/session_export.py`.
- **Rationale:** C-005 is the cheapest real experiment in the repository because
  both arms already exist and are already tested (audit §1.6: "Mytheca is one of
  the very few systems that still contains both arms of the comparison in working,
  tested form"). §3.2 requires `PROTOCOL.md` to be written and committed **before**
  the run — that is what this phase delivers, and it is why running is Phase 5, not here.
- **Steps:**
  1. `run_scene.py` — drives a scenario headlessly for N beats across S seeds,
     selecting the arm by CLI flag. **Arm A** calls the shipped turn loop
     (`planner_agent.next_beat`). **Arm B** calls `director_agent.who_is_up` from
     the runner to produce the one-shot speaker set, then voices those speakers
     through the same `character_turn_agent`. Per §11 and §5, **no file under
     `web/backend/app/` is edited** — the runner reaches in, it does not rewire.
  2. `record.py` — §7.2 auto-capture: on every run, write git commit/branch/dirty,
     config hash, seeds, environment lockfile reference, hardware, wall-clock,
     LLM model + sampling params + token counts, and final metrics straight into the
     experiment's `manifest.yaml` and `data/metrics.json`. Capture happens at
     write-time, never reconstructed afterwards (§1.6 of the instruction set).
  3. `make new-experiment SLUG=planner-vs-oneshot-director` to scaffold the folder —
     dogfooding the Phase 3 tooling rather than hand-creating it.
  4. Write `PROTOCOL.md` in full, before any run. **Question:** does the ReAct
     per-beat planner produce better multi-party turn structure than the one-shot
     speaker-set decision? **Hypothesis:** stated ahead, per §3.2.
     **Metrics — defined, not merely named:** turn-length distribution;
     addressed-character response rate (does every directly addressed character
     respond); bystander-interjection rate (does an unaddressed character answer a
     directed question); beats-per-turn; LLM calls, tokens and wall-clock per turn.
     **Baselines:** Arm B. **Procedure:** the exact commands.
     **What would falsify this:** no separation beyond seed variance.
  5. Set `status: planned`, `supports_claims: [C-005]`, and fill `env/hardware.md`.
     Add the `C-005` → `EXP-2026-08-001` link in `CLAIMS.md` with status still
     `unsupported` (evidence pending, not evidence obtained).
- **Validation:** `make validate-research` passes with the experiment at
  `status: planned` and empty metrics; `make research-index` lists it; a smoke run
  of `run_scene.py` at 1 seed / 2 beats completes or fails with a clear diagnostic.
- *Action: Run `uv run pytest` and `make validate-research`. Once green, commit locally:*
  `[Research Record] (5/7) Complete: Added the headless scene runner and pre-registered EXP-2026-08-001 (planner vs one-shot director).`

---

### Phase 5 — Execute EXP-2026-08-001 and record results

- **Locations:** `docs/research/experiments/EXP-2026-08-001-planner-vs-oneshot-director/`
  — `manifest.yaml`, `RESULTS.md`, `ISSUES.md`, `data/{metrics.json,metrics.csv,POINTERS.md}`,
  `figures/{make_figures.py,fig-turn-structure.svg,fig-turn-structure.pdf}`,
  `tables/`, `env/`, `logs/`. Plus `docs/research/{CLAIMS.md,OPEN_QUESTIONS.md,INDEX.md}`.
- **Rationale:** acceptance criterion #7 — at least one real experiment recorded end
  to end as a worked example. Everything before this phase is scaffolding; this is
  the phase that proves the scaffolding holds a real result.
- **Steps:**
  1. Bring up the stack via `python app.py backend` (it owns Docker — never
     `docker compose` directly) and confirm the LLM endpoint responds within the
     ≥3 min / ≥8000-token envelope the local reasoning model needs.
  2. Run both arms over the Embergate seed scenario, ≥3 seeds each, and set
     `status: running` while it executes.
  3. `figures/make_figures.py` — reads `data/metrics.json`, **never hardcoded
     numbers** (§4), emits `.svg` **and** `.pdf`, colour-blind-safe palette, no
     font below 7pt, one command regenerates everything in the folder.
  4. `RESULTS.md`, all eight §3.3 sections in order: Headline (two sentences, the
     number and whether the hypothesis survived) · Results table, generated, mean ±
     std across seeds and never a single run · Figures with captions naming the
     generating script · Interpretation · **Threats to validity — which must state
     in plain words that N is far below the audit's §7 minimum and that the
     Embergate world ships with the repository and is therefore contaminated
     (G-C)** · What surprised us · Follow-ups · Reproduction command.
  5. `ISSUES.md` — every anomaly, aborted run, and excluded seed, with its effect on
     n, in the Appendix C shape.
  6. Update `CLAIMS.md` for `C-005` to the status the evidence actually supports —
     `partial` at best given the sample size; **`supported` is not available from a
     run this small** and must not be claimed.
  7. Append every Follow-up from `RESULTS.md` §7 into `OPEN_QUESTIONS.md`.
     Regenerate `INDEX.md`.
  8. **If the run cannot complete (G-A):** set `status: failed`, write `RESULTS.md`
     describing exactly what broke, fill `ISSUES.md`, leave `metrics.values` empty,
     keep `C-005` at `unsupported`, and **say so directly in the session report**.
     The folder is never deleted (§3.4).
- **Validation:** `make validate-research` passes; `make figures` regenerates with
  no diff; `make research-index` produces no diff; every number in `RESULTS.md`
  traces to `data/metrics.json`.
- *Action: Run `uv run pytest`, `make validate-research`, `make figures`. Once green, commit locally:*
  `[Research Record] (6/7) Complete: Executed and recorded EXP-2026-08-001 end to end with generated figures.`

---

### Phase 6 — Documentation amendments, final gate, merge, cleanup

- **Locations:** `README.md` (one added section), new `CONTRIBUTING.md`,
  `CLAUDE.md` (one added section + one routing row), `docs/structure.md`,
  `docs/workflow.md`, `docs/architecture.md`, `docs/checklist.md`,
  `docs/documentation.md`, `docs/skills/global-project-rules/SKILL.md`.
- **Rationale:** §6 permits **minimal diffs only** — "do not rewrite existing docs".
  Every edit here is additive except the `docs/plans` routing row from Phase 0.
  §6's do-not-touch list (licence, citation, install instructions, API docs,
  changelog) is respected: `docs/api-contract.md` is not modified in this phase.
- **Steps:**
  1. `README.md` — add the §6 "## Research record" section near the top, after
     "What is Mytheca?". The project description, stack line, mermaid diagram,
     features and install steps are **not touched** (§11 non-goal).
  2. `CONTRIBUTING.md` — new stub carrying the §6 "### Running an experiment"
     five-step block, plus a pointer to `docs/skills/global-project-rules/SKILL.md`
     for the existing validation gate.
  3. `CLAUDE.md` — add the §6 "## Research record (mandatory)" block verbatim
     (record every experiment; never report a metric without writing it to
     `manifest.yaml` + `RESULTS.md`; never hand-edit a figure or hardcode a number
     in a plotting script; failed runs are recorded not deleted; "just quickly
     check" still creates the folder). Add a `docs/research/` row to the "Docs — go
     straight to the file" table. Add `make` to the Fast command reference.
  4. `docs/structure.md` — `docs/research/`, `utils/scripts/research/`,
     `utils/tests/tools/`, `docs/plans/archive/`, root `Makefile`.
  5. `docs/workflow.md` — the four `make` targets and the `research` dependency
     group. `docs/architecture.md` — `pyyaml` and `matplotlib` with their defined jobs.
  6. `docs/skills/global-project-rules/SKILL.md` — one line adding the research
     record to Documentation Maintenance: an experiment or evaluation run means
     `docs/research/` is updated in the same change.
  7. `docs/checklist.md` — record the **deliberate** deferrals so they are not
     mistaken for oversights: §7.4 CI and §7.5 pre-commit not implemented (user
     decision); EXP-2026-08-001 is under-powered relative to audit §7; the audit's
     P1 study (10–14 weeks) is not started; six of seven claims have no experiment.
  8. Verify acceptance criteria §10 one by one and record the result of each.
  9. Merge to `main`, resolve any conflicts, then **remove this worktree and its
     branch** (`git worktree remove` + `git branch -d`) so it does not become the
     twelfth stale worktree named in `docs/checklist.md`.
- **Validation — full gate:** `uv run pytest` · `cd web/frontend && npm test` ·
  `npm run typecheck` · `npm run lint` · `make validate-research` · `make figures`.
  No UI is touched anywhere in this plan, so the accessibility/responsive pass does
  not apply; `utils/scripts/check_contrast.py` is not required as no theme token changes.
- *Action: Run the full gate. Once green, commit locally, merge to `main`, and delete the worktree:*
  `[Research Record] (7/7) Complete: Amended README, CONTRIBUTING and CLAUDE.md to point at docs/research, and closed out the retrofit.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Plans archive | 72 shipped-feature plans moved out of the routing path | `docs/plans/archive/` |
| Research skeleton | Full §2 structure, no invented siblings | `docs/research/` |
| Agent contract | The installed instruction set + Mytheca deviations | `docs/research/AGENT_INSTRUCTIONS.md` |
| Experiment templates | §3.1/3.2/3.3 manifest, protocol, results, issues | `docs/research/templates/experiment/` |
| Decision + negative-result templates | Appendix B and §3.4 shapes | `docs/research/templates/` |
| Claims ledger | C-001…C-007 from audit §1.6, all `unsupported` | `docs/research/CLAIMS.md` |
| Open questions | G1–G8 from audit §4 + disqualifiers | `docs/research/OPEN_QUESTIONS.md` |
| Related work | Audit §9 bibliography + §3 deltas + scoop watch | `docs/research/RELATED_WORK.md` |
| Decisions log | D-001…D-006 ADRs traceable to audit sections | `docs/research/DECISIONS.md` |
| Paper scaffolding | P1 outline, venue targets, two checklists | `docs/research/paper/` |
| Dataset record | No dataset yet, stated honestly + card template | `docs/research/datasets/` |
| Manifest schema | Pydantic model of the §3.1 contract | `utils/scripts/research/manifest_schema.py` |
| Scaffolder | Allocates IDs, copies templates, captures git state | `utils/scripts/research/new_experiment.py` |
| Validator | All nine §7.3 failure conditions | `utils/scripts/research/validate_research.py` |
| Index generator | Regenerates `INDEX.md` from manifests | `utils/scripts/research/gen_index.py` |
| Auto-capture helper | §7.2 write-time record of commit/config/seeds/compute/LLM | `utils/scripts/research/record.py` |
| Headless runner | Two-arm scene driver; touches no app code | `utils/scripts/research/run_scene.py` |
| Make targets | `new-experiment` · `validate-research` · `research-index` · `figures` | `Makefile` |
| Worked experiment | C-005 planner ablation, recorded end to end | `docs/research/experiments/EXP-2026-08-001-planner-vs-oneshot-director/` |
| Generated figure | `.svg` + `.pdf` from `metrics.json`, with generator | `…/EXP-2026-08-001-…/figures/` |
| Generated index | Auto-generated experiment table | `docs/research/INDEX.md` |
| Tool tests | Validator passes-and-correctly-fails, scaffolder, index idempotence | `utils/tests/tools/` |
| Doc amendments | Additive sections only, per §6 | `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`, `docs/*.md` |

## 5. Acceptance Criteria Mapping (§10)

| Criterion | Phase |
| --- | --- |
| `docs/research/` has the full §2 structure | 1 |
| `make new-experiment SLUG=x` scaffolds a validator-passing experiment | 3 (asserted by test), 4 (used for real) |
| `make validate-research` passes, and fails on a deliberately broken folder | 3 |
| `make figures` regenerates every promoted figure with no diff | 5 |
| `INDEX.md` generated and current | 3, regenerated 5 |
| `CLAIMS.md` lists every intended claim with evidence status | 2, updated 5 |
| At least one real experiment recorded end to end | 5 |
| Pre-existing results back-filled or noted unrecoverable | 2 — **there are none**; the audit (line 20) establishes zero prior evaluation, and `datasets/DATASETS.md` records this explicitly rather than leaving it inferred |
| README, CONTRIBUTING, agent file point at `docs/research/`, nothing else rewritten | 6 |
| CI enforces validation on every PR | **Not met — deliberately.** User-scoped to scripts + Makefile; recorded in `docs/checklist.md` and `AGENT_INSTRUCTIONS.md` as a known, chosen gap |
