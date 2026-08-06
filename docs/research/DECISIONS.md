# Decisions

ADR-style, dated, **append-only**. One entry per research decision: metric choices,
baseline selection, dataset exclusions, scope cuts. Reviewers ask "why did you use
X?" — this is where the honest answer already lives.

Never edit a past entry. Supersede it with a new one and say which it replaces.

Template: `templates/DECISION.md`.

---

## D-001 — `docs/research/` is the single research record

**Date:** 2026-08-06
**Context:** Mytheca had one research artifact (a 904-line external audit) and no
structure around it. The project has 514 commits and zero recorded evaluation. Any
future result would have landed in a chat log or a commit message — which is to say,
nowhere retrievable.
**Options:** (a) leave results wherever they land and reconstruct at paper time;
(b) adopt an experiment-tracking SaaS (MLflow/W&B) as the record; (c) a git-tracked,
human-readable directory with a fixed per-experiment contract.
**Decision:** (c). External dashboards die; repositories persist. If a tracker is
adopted later it mirrors *into* here, never replaces it.
**Consequences:** Every experiment now costs a folder, a pre-registered protocol, and
a validator pass. That is deliberate friction — the alternative is the reconstruction
problem this exists to prevent. Reconstructing six months of results from memory is
not cheaper, it is just deferred and worse.

## D-002 — P1 (voice distinctness) is the chosen research path

**Date:** 2026-08-06
**Context:** Audit §7 sets out four reframings of the same codebase. The engine
itself is not publishable — its architecture is anticipated by IBSEN (ACL 2024),
MAGNET/ATLAS, PANGeA, NWM and Open-Theatre, and every archival venue surveyed has
CFP language making a zero-evaluation submission desk-rejectable.
**Options:**
- **P1** — does multi-agent scaffolding preserve character voice? 10–14 wk, closes G1/G2/G3/G5.
- **P2** — a trajectory-level evaluation environment. 14–20 wk, highest ceiling, but benchmark papers live or die on adoption and it competes with Open-Theatre.
- **P3** — POV switching as an interaction technique. 14–18 wk, **cleanest novelty**, but gated on human-subjects logistics outside the skill set the repository demonstrates.
- **P4** — human evaluation in this field is underpowered: a methodological audit. 6–9 wk, unclaimed, cheap.
**Decision:** **P1.** Best ratio of new-work to carried-over-work; the only path whose
first experiment is a *falsification* that could save a year; addresses the meta-claim
four separate 2024–2026 papers are actively contesting without anyone having tested
it in the narrative setting; and its null result is publishable at EXAG, which
explicitly solicits failure reports.
**Consequences:** P3 is deferred, and it is the one with the cleanest novelty — that
is a real cost, accepted because P1 must establish the instrument is sound first.
**If P1's first week produces a null result, switch to P4**, for which the null
result is itself evidence. Committing to P1 also means the engine stops being the
contribution, which is a harder narrative shift than it sounds.

## D-003 — The primary metric is not an LLM-as-judge

**Date:** 2026-08-06
**Context:** The obvious cheap evaluation for character-voice distinctness is to ask
a strong LLM to judge it. PersonaEval (arXiv:2508.10014) finds LLM judges cannot
identify the correct speaker in role-play transcripts as reliably as humans, that
role-play fine-tuning does not help and can hurt, and that current role-play studies
rely on **unvalidated** LLM-as-judge paradigms.
**Options:** (a) LLM-as-judge — cheap, scalable, unsound here; (b) blinded human
speaker-attribution on label-stripped transcripts — sound, expensive, needs ≥2 raters
and chance-corrected agreement; (c) a held-out stylometric classifier — cheap,
scalable, no judge-validity problem, but measures surface style rather than
perceived character.
**Decision:** **(b) primary, (c) secondary**, with population-level
Coverage/Uniformity/Complexity (arXiv:2604.24698) tertiary. LLM-as-judge is not used
for any primary metric.
**Consequences:** The evaluation is materially more expensive and slower, and it puts
the project on the human-subjects path earlier than it would otherwise go. In
exchange, the primary result is not vulnerable to the single most likely reviewer
objection in this area. Norman et al. (arXiv:2606.19544) additionally require
chance-corrected agreement — raw agreement overstates it by 33–41 points — so
exact-match percentages are not reportable on their own.

## D-004 — Evaluation uses original characters, never famous fictional ones

**Date:** 2026-08-06
**Context:** Peng & Chen (SIGDIAL 2026, arXiv:2603.03915) show that memorisation of
famous fictional characters inflates published role-play scores. Mytheca's worlds and
casts are user-authored originals, so that pathway does not apply — audit §6.4 #5
calls this the project's **single strongest methodological asset**.
**Options:** (a) use recognisable characters for comparability with prior work;
(b) keep original characters and lose direct comparability.
**Decision:** **(b).** Original characters only.
**Consequences:** Results are not directly comparable to role-play benchmarks built
on known characters, and that limitation must be stated. Accepted, because the
alternative trades away the one contamination-free asset the project has. **Note the
residual:** genre conventions (maritime intrigue, guilds, a drowned harbour) are
heavily represented in training data even when specific characters are not — so
report **relative comparisons between arms, never absolute quality scores.**

## D-005 — No CI or pre-commit enforcement in this retrofit

**Date:** 2026-08-06
**Context:** §7.4 and §7.5 of the research-record contract mandate a GitHub Actions
job and a pre-commit hook. Mytheca has never had a `.github/` directory; its
validation gate is `uv run pytest` + `npm test` run by hand (`docs/workflow.md`).
**Options:** (a) full §7 including CI; (b) scripts + pre-commit hook; (c) scripts and
a Makefile only, run manually.
**Decision:** **(c)**, chosen by the owner. `make validate-research` and
`make research-index` exist and are strict; nothing runs them automatically.
**Consequences:** **This is the one acceptance criterion in §10 deliberately unmet,
and the enforcement gap is real** — the contract's own §7 opens with "convention
without enforcement decays," and a validator nobody runs is a convention. The
mitigation is that the validator is genuinely strict when invoked and the four `make`
targets are documented in `CONTRIBUTING.md`, `CLAUDE.md` and `AGENT_INSTRUCTIONS.md`.
Revisit if a second experiment lands without the validator having been run.

## D-006 — Evaluation worlds are generated fresh and never committed

**Date:** 2026-08-06
**Context:** The repository has a GitHub remote whose public/private status could not
be determined from the repository itself. The shipped **Embergate** seed world
(`web/backend/app/core/seed.py`) is committed, so if the remote is or becomes public,
it can enter future training corpora — destroying the contamination-free property
that D-004 protects.
**Options:** (a) use Embergate for evaluation — convenient, already exists, already
committed; (b) generate fixed evaluation worlds fresh and hold them privately.
**Decision:** **(b) for anything destined for a paper.** Committed worlds may be used
for tooling shakedowns and structural experiments, but any result that appears in a
submission runs on private, uncommitted worlds.
**Consequences:** Evaluation data cannot be released alongside the code as-is, which
complicates the artifact-availability badge (`paper/checklists/artifact-evaluation.md`) —
a release corpus will have to be generated and licensed separately. **EXP-2026-08-001
knowingly violates this** by running on Embergate: it is a structural experiment
proving the record works end to end, its `RESULTS.md` states the contamination, and
its numbers are not paper-eligible.
