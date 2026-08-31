# Repository audit — Mytheca

**Date:** 2026-08-31 · **Archetype:** mixed (web-app + ml-research) · **Purpose:** portfolio + public product · **Reader:** hiring manager, then a stranger who wants to run it
**Profile:** [`docs/audit/repo-profile.yaml`](repo-profile.yaml) · **Commit:** `3dd8438`
**Method:** the `repo-audit` protocol, stages 0–11. Every finding states what was observed and how it was checked.
**Instruments:** `audit_structure.py`, `audit_docs.py`, `audit_readme.py`, `check_links.py`, plus the app run locally and screenshotted.

This is the **repository** audit — layout, documentation, README, hygiene, showcase, publishability.
It is a different pass from [`audit-report.md`](audit-report.md), which audits the **running website**
(accessibility, responsiveness, motion, SEO).

---

## The thirty-second verdict

What a stranger currently learns in thirty seconds:

> A wordmark, a paragraph of genuinely good prose about what Mytheca is, a Mermaid diagram,
> a feature list, and a Quickstart. The writing is well above average for a personal repo —
> specific, unhyped, and clearly written by someone who knows the system.

What they wrongly conclude:

> That the engine works the way the README says it does. It does not: the README describes a
> **ReAct planner that decides one beat at a time**, which was deliberately replaced five days
> ago by a bound single-call plan, and a **visible in-voice deliberation** that was deliberately
> switched off. It also undersells the LLM layer by three providers.
>
> And — because there is not one screenshot of the running application anywhere in the repository —
> they have no reason to believe any of it runs at all. For a web app, that is the default assumption.

The gap this audit closes is not "make it look nicer." It is that a reader currently cannot tell that
the best parts of this repo exist: a working, good-looking application, and a 19-experiment research
record with negative results honestly reported.

---

## Gates

| Gate | Result | Evidence |
|---|---|---|
| **TRUTH** — does the documentation describe the repo that exists? | **FAIL** | Four claims in `README.md` contradict the code. T-1 … T-4 below. |
| **RUNNABLE** — clean clone to working state on documented steps? | **FAIL** | The first command in the Quickstart cannot execute as written (R-1). Full clean-clone container verification was **not** run — see *What this audit cannot tell you*. |

Both gates failed, so every cosmetic finding below is provisional on them being fixed first.
Prettifying a false claim makes the repo worse, not better.

---

## What this audit cannot tell you

Stated up front, because an audit that overclaims is worse than one that is narrow and honest.

- **The clean-clone run was not verified in a container.** The app was verified working *on this
  machine* — both servers healthy, a seeded scene rendered, four themes and the graph view
  screenshotted. That is not the same claim. It says nothing about a machine without the Docker
  images cached, without an LLM endpoint already configured in the settings row, or on macOS or
  Windows. `entrypoints.verified` stays `false` in the profile for exactly this reason.
- **No reader has been observed.** Everything about "what a hiring manager concludes" is inference
  from the evidence ledger, not from watching anyone read this repo.
- **Two script findings were dismissed as false positives**, recorded here so they do not come back:
  `junk.env` flagged `.env`, which is untracked and correctly gitignored (`git ls-files` confirms);
  `junk.log` flagged 18 `run.log` files, which are deliberate experiment artifacts required by the
  research contract, not stray output.
- **Code quality is out of scope.** This audit reads structure and documentation. It has not
  assessed whether the engine is well built.

---

## Findings

### Blockers

```
[BLOCKER · LEGAL] L-1  No LICENSE file
  where:    repository root
  observed: no LICENSE / LICENCE / COPYING / COPYRIGHT in .github/, root, or docs/.
            pyproject.toml carries no `license` field either.
  why:      without a licence the work is under exclusive copyright by default. Nobody
            may copy, modify or redistribute it; GitHub's terms grant viewing and forking
            and nothing more. This is not a polish item — it is the difference between a
            portfolio piece and an artifact nobody may legally use, and it directly
            contradicts the stated goal of "a public product for others to use".
  fix:      add MIT at the root (owner's decision, 2026-08-31), and declare it in
            pyproject.toml as the PEP 639 SPDX string `license = "MIT"`.
  effort:   5 minutes
  verify:   ls LICENSE && grep '^license' pyproject.toml
```

```
[BLOCKER · FUNCTIONAL] T-1  README describes a ReAct planner the engine no longer uses
  where:    README.md:47 ("How it works"), and README.md:53 ("Key features")
  observed: README: "Each turn runs a ReAct loop: a planner decides one beat at a time —
            who speaks, whether the narrator cuts in […]".
            web/backend/app/services/turn_plan.py:17: "An approved plan is executed, never
            re-planned." turn_plan.py:343: "There is no re-plan on a bound turn."
            core/config.py:91: turn_planner_lookahead defaults to 0 = plan the whole turn.
  why:      this is the single most load-bearing architectural claim on the front page and
            it describes the design that was deliberately replaced on 2026-08-26, because
            re-planning was measured producing 18-, 22- and 24-beat turns (EXP-2026-08-016).
            A reader who opens the code finds the opposite of what they were told. Worse,
            the change is a *good* decision with a measurement behind it, and the README is
            currently hiding it.
  fix:      describe the bound plan: one planner call per turn, at HIGH effort, whose output
            is a contract the loop executes without re-planning. Name the two documented
            exceptions (undelivered player direction; the pre-plan scene-opening narration).
  effort:   30 minutes
  verify:   grep -n "ReAct" README.md   # expect no hits in the architecture prose
```

```
[BLOCKER · FUNCTIONAL] T-2  README advertises a deliberation channel that was switched off
  where:    README.md:47
  observed: README: "Each chosen character gets its own isolated LLM call (a visible in-voice
            deliberation, then speech), so voices stay distinct."
            web/backend/app/agents/character_turn_agent.py:60: TURN_EFFORT = ReasoningEffort.NONE
  why:      the deliberation was removed on 2026-08-26 after the prose call was measured
            spending 91% of its output on hidden reasoning (2646 reasoning characters for 247
            of prose). The isolated-call-per-speaker part is still true and still the reason
            voices stay distinct; the deliberation half is not.
  fix:      keep the isolation claim, drop the deliberation claim. If the reasoning budget is
            worth mentioning, the honest version is that deliberation moved to the planner
            (PLANNER_EFFORT = HIGH, paid once per turn) — which is a more interesting claim.
  effort:   10 minutes
  verify:   grep -n "deliberation" README.md
```

```
[BLOCKER · FUNCTIONAL] T-3  README understates the LLM layer by three providers
  where:    README.md:60 ("Key features"), README.md:69 ("Tech stack")
  observed: README: "one OpenAI-compatible interface serving cloud OpenAI, vLLM, or llama.cpp".
            web/backend/app/services/llm_providers/ contains four adapters:
            openai_compatible.py, anthropic.py, gemini.py, ollama.py.
  why:      this one undersells rather than oversells, which is the rarer failure but still a
            truth failure — the front page does not describe the system that exists. It also
            omits the caveat the repo's own checklist carries, which is the part that makes
            the claim honest: only openai-compatible has ever made a live request.
  fix:      state four providers AND state plainly that three are unproven against a live
            endpoint. docs/checklist.md already has the wording; the README should not claim
            more than the checklist does.
  effort:   15 minutes
  verify:   grep -n "anthropic\|gemini\|ollama" README.md
```

```
[BLOCKER · FUNCTIONAL] R-1  The first Quickstart command cannot run
  where:    README.md:78
  observed: `git clone <this-repo> && cd Mytheca`.
            `<this-repo>` is an unfilled placeholder, and `git remote -v` resolves to
            git@github.com:brendondgr/Velora.git — so even with the URL filled in, the
            clone produces a directory named Velora and `cd Mytheca` fails.
  why:      onboarding.md's standard is one documented command for setup, one to run. The
            very first one is a placeholder that fails. A stranger tries once.
  fix:      write the real clone URL. The owner has decided to rename the GitHub repository
            to Mytheca (2026-08-31); write the command against the new name, and note that
            the rename is a prerequisite for the README being true.
  effort:   2 minutes, after the GitHub rename
  verify:   run the block verbatim in an empty directory
```

### Major

```
[MAJOR · SURVEY-DATA] D-1  README answers neither Why nor When
  where:    README.md — whole file
  observed: audit_readme.py classifies sections as what / how / reference / other.
            No purpose section and no status section. Funnel: "what" answered at line 10,
            "status" not until line 109, "why" never.
  why:      purpose appears in 25.7% of READMEs and status in 21.4% (Prana et al., 393 repos
            hand-annotated). They are the two sections a hiring manager most needs and the two
            most repos skip — which makes them the cheapest differentiators available.
            Honest complication, which must not be dropped: Venigalla & Chimalakonda found
            neither is associated with popularity in any of ten languages. These are
            legitimacy signals for a human evaluator, not growth levers.
  fix:      Why — two short paragraphs on the problem and why the obvious approach (one
            chatbot playing every part) was insufficient. The briefing at
            docs/briefings/storyline-chat-briefing.md §3 already contains the answer in the
            owner's own words: "The AI generates validated story events; the UI renders them.
            The AI never decides UI layout." That is the Why, and it is unusually good.
            When — one honest line: active, solo, started June 2026, self-host only, no auth.
  effort:   45 minutes, and it needs the owner — an invented motivation is a claim they would
            have to defend in an interview and could not
  verify:   audit_readme.py . --sections
```

```
[MAJOR · PRACTITIONER-CONSENSUS] S-1  No screenshot of the running application exists anywhere
  where:    repository-wide
  observed: the only images in the repo are four brand SVGs in images/ and 12 experiment
            figures under docs/research/experiments/*/figures/. `find` over docs/ and images/
            for png/jpg/gif/webp returns no application screenshot.
  why:      this is the largest single gap for this archetype. A web app with no visual is a
            web app the reader assumes does not work, and no amount of prose substitutes.
            The application is genuinely good-looking — verified by running it — and the
            repository currently contains no evidence of that fact.
  fix:      commit 2–4 screenshots to docs/assets/ and lead the README with one. Captured
            during this audit and available: the story player mid-scene in the Parchment
            theme (the hero), the same scene in Slate, the library shell, the story graph.
  effort:   1 hour including capture, crop and caption
  verify:   audit_assets.py . && check_links.py . --rendered
```

```
[MAJOR · FUNCTIONAL] R-2  .env.example ships a value that contradicts the code default
  where:    .env.example:62 and the comment block above it
  observed: .env.example sets TURN_PLANNER_LOOKAHEAD=1 under a comment describing per-beat
            planning. web/backend/app/core/config.py:91 defaults it to 0.
            .env.example:53 also calls TURN_MAX_BEATS a "runaway backstop for the ReAct
            planner loop" — the same retired terminology as T-1.
  why:      the documented setup path is `cp .env.example .env`. Anyone who follows it gets a
            *different turn engine* from the code's default, silently, with no error and no
            way to know. This is the characteristic "undocumented environment" failure, and
            here the environment is not merely undocumented but actively wrong.
  fix:      set TURN_PLANNER_LOOKAHEAD=0 (or comment it out so the code default governs) and
            rewrite the two comment blocks that still describe the ReAct loop.
  effort:   15 minutes
  verify:   diff the .env.example defaults against core/config.py field defaults
```

```
[MAJOR · FUNCTIONAL] R-3  The documented Quickstart never says what LLM you need
  where:    README.md:76 ("Prerequisites")
  observed: prerequisites list Python 3.13 + uv, Node.js, and Docker. The LLM appears only as
            a parenthetical in `cp .env.example .env   # then fill in values (LLM endpoint,
            secrets)`. Nothing states what endpoint, what model class, what hardware, or that
            the app is inert without one.
  why:      undocumented prerequisites are the characteristic failure of this archetype: the
            reader gets everything running and then hits a dead app with no indication why.
            Mytheca is an LLM engine — the model is not a configuration detail, it is the
            single prerequisite that decides whether anything happens.
  fix:      a short "What you need to bring" block: an OpenAI-compatible endpoint (verified
            path), a rough capability floor, and the honest note that the other three
            providers are untested live. Say what this install runs on.
  effort:   30 minutes, needs the owner for the capability floor
  verify:   hand the Quickstart to someone who has never run it
```

```
[MAJOR · PRACTITIONER-CONSENSUS] W-1  An eight-page written analysis is invisible
  where:    reports/mytheca-latency-report.pdf
  observed: an 8-page PDF titled "Why Mytheca turns take as long as they do", committed at the
            repo root in a directory referenced by no document — grep across README.md,
            CLAUDE.md, CONTRIBUTING.md and docs/*.md returns nothing.
  why:      writing beats demos beats code is the most consistent practitioner finding in the
            portfolio corpus, and this repo has the writing and does not link it. A
            latency analysis that names its own numbers is exactly the artifact a technical
            reader would find persuasive, and right now it is a mystery file in an
            unexplained top-level directory.
  fix:      move it under docs/research/ (where the rest of the research record lives) and
            link it from the README's research section. Delete the now-empty reports/.
  effort:   15 minutes
  verify:   grep -rn "latency-report" README.md docs/
```

### Minor

```
[MAJOR · FUNCTIONAL] X-1  A quoted measurement traced to an experiment with no write-up
  status:   RESOLVED during this restructure. The number is real; the record was not.
  where:    CLAUDE.md, docs/plans/binding-plan-and-execution-arms.md:11 and :133,
            docs/research/experiments/EXP-2026-08-017-.../PROTOCOL.md:12, :61, :125
  observed: three documents cited EXP-2026-08-016 for "turns of 18, 22 and 24 beats on a
            three-character scene". That folder read `status: planned`, held zero data
            files, carried an unfilled template RESULTS.md, and its INDEX row still had
            `<one line, specific enough to read in a table>`. From the record alone the
            number traced to nothing.
  why:      the research contract forbids exactly this in its own words — "Never report a
            metric without also writing it to the corresponding manifest.yaml and
            RESULTS.md" — and the record's whole value is that its numbers can be checked.
            Three documents had already inherited authority the source did not have.
  what it turned out to be: the run HAPPENED, on 2026-08-25, and was never written up. Its
            event log was still in the dev Postgres and was recovered on 2026-08-31,
            minutes before the throwaway storyline holding it was deleted at the owner's
            request. Two things then fell out that the citations had missed:
              1. The quoted figure was the MILDER half. 18/24/22 are the `voiced` arm's
                 worst turns; the `continuous` arm produced a 38-beat turn that appears in
                 none of the three citing documents.
              2. The arms are identifiable after all — ISSUES.md records in passing that
                 "voiced turn 3 produced 18 beats and continuous turn 3 produced 3", which
                 matches exactly one session each in the log.
            ISSUES.md was doing the real record-keeping the whole time: its first entry
            says "nothing ran" (true when written, 08-24/25) and the two entries below it
            describe the run that then happened. A reader stopping at the first entry
            concludes the experiment never ran.
  fix applied: data/events.json (raw, 139 events) + make_metrics.py (computes every
            reported number from it) + a filled RESULTS.md, manifest and INDEX row.
            `status: failed`, following EXP-017's reading — the run could not produce what
            the protocol asked for, since all three primary metrics were never computed.
            `make validate-research` passes: 19 experiments, 0 warnings.
            **The status is the owner's to revise** — assigning one is a judgement about
            their own work, not an inference from the text.
  residual: the `continuous` vs `voiced` question this experiment existed to answer is
            still open, and so is EXP-2026-08-017's. Recorded in both RESULTS files.
            Two process follow-ups are logged in EXP-016 §7: whether
            `make validate-research` should fail when a document cites a `planned`
            experiment, and whether the harness should persist an event log for every run
            so an unwritten experiment is recoverable by design rather than by luck.
  verify:   make validate-research && python3 docs/research/experiments/EXP-2026-08-016-continuous-scene-script/make_metrics.py
```

```
[MINOR · CONVENTION] H-1  No .github/ directory, and no CI
  where:    repository root
  observed: no .github/ at all. No workflow runs the validation gate that CONTRIBUTING.md
            defines as the definition of done.
  why:      recommend CI for what it does, not how it looks — there is no hiring-side
            evidence that a green badge influences anything, and claiming otherwise is
            folklore. The real reason applies squarely here: the highest-value job a
            portfolio repo can run is the one that executes the documented setup path on a
            clean runner, which is precisely the check that would have caught R-1 and R-2.
  fix:      one workflow: `uv run pytest` + `npm test` + `npm run typecheck` on push and PR
            to main, `permissions: contents: read`. Skip matrix builds and coverage gates —
            disproportionate at this scale.
  effort:   1 hour
  verify:   the workflow goes green on a push
```

```
[MINOR · CONVENTION] H-2  Root-level layout carries three items that are not the project
  where:    libs/, reports/, line_counter.py
  observed: libs/ contains only .gitkeep and is documented in docs/structure.md:19 as
            "currently empty". reports/ holds one unreferenced PDF (see W-1).
            line_counter.py is documented in CLAUDE.md as "standalone LOC utility, not part
            of the app" and sits beside app.py at the root.
  why:      the top-level tree is the second thing a reader looks at, and each of these costs
            a moment of "what is this, and do I need it?" before they reach web/ and docs/.
            This is a legibility finding, not a correctness one.
  fix:      delete libs/ (a reserved-for-later directory that has been empty for ten weeks is
            a note, not a directory — say it in docs/structure.md instead); move
            line_counter.py to utils/scripts/; move the PDF per W-1 and delete reports/.
            All three are named in docs/structure.md and CLAUDE.md and must be updated in the
            same change.
  effort:   30 minutes including propagation
  verify:   audit_docs.py . --governing   # must exit 0 after the move
```

```
[MINOR · FUNCTIONAL] H-3  Three broken internal links, all the same placeholder
  where:    docs/research/templates/experiment/RESULTS.md:25 and the two experiments that
            copied it (EXP-2026-08-015, EXP-2026-08-016)
  observed: `figures/fig-<slug>.svg` — the template's placeholder token, left unsubstituted.
  why:      broken links are one of very few things an employer has written down as a scored
            penalty. These are deep in the research record rather than on the front page, so
            the severity is low, but they are trivially fixable and `check_links.py` will
            keep reporting them.
  fix:      substitute the real figure names in the two experiments. In the template, make it
            visibly a placeholder (a fenced example rather than a live link) so a copy that
            forgets to substitute does not produce a broken link.
  effort:   15 minutes
  verify:   check_links.py .   # expect 0 internal-broken
```

```
[MINOR · FUNCTIONAL] H-4  First boot prints a migration error
  where:    observed in app.py preflight output, 2026-08-31
  observed: `[!! ] migrations (optional): error ((psycopg.errors.DuplicateColumn) column
            "beat_length" of relation "scenarios" already exists)`
  why:      the schema reconciler creates columns from the models, then Alembic tries to add
            one that now exists. Marked optional and non-fatal, so nothing breaks — but it is
            an error message on the first screen a new user sees, and an error a reader
            cannot distinguish from a real failure erodes trust in everything printed after it.
  fix:      needs diagnosis, not a one-liner: establish whether this reproduces on a genuinely
            fresh database or only on this drifted dev DB. If it reproduces, the reconciler
            and Alembic disagree about who owns new columns and that is worth settling.
  effort:   unknown until reproduced
  verify:   drop the dev database and run `uv run python app.py backend` on an empty volume
```

```
[WITHDRAWN] S-2  Character-card badge overlapping the name — NOT A DEFECT
  status:   withdrawn 2026-08-31. This finding was wrong and is kept rather than deleted.
  claimed:  that at 1600px the "◆ In this scene" badge drew across character names that
            wrap to two lines, in both Parchment and Slate.
  observed: measured directly in the rendered DOM at the same viewport and theme the
            screenshot was taken at. Badge bottom 645.97px, name top 649.97px — a 4px
            gap. Same result on every affected card ("Wren Calloway", "Captain Doran
            Hale"). The band is `position: absolute`, the badge is `display: block`,
            `position: static`, and it stacks normally. There is no overlap.
  cause of the error: read off a 3200px screenshot downscaled to 2000px for review. The
            badge wraps to two lines on a narrow card, which puts four short lines of
            text in a small band and reads as collision at that scale.
  lesson:   a visual defect claimed from a downscaled screenshot is a hypothesis, not an
            observation. This audit's own rule — record the file, the line, the command
            run and the observed result — is what caught it, one measurement later.
  consequence: the library screenshot was held back from the README for this finding.
            It is now cleared and shipped.
```

### Advisory

```
[ADVISORY · CONVENTION] A-1  pyproject.toml has no project URLs and version 0.0.0
  observed: `version = "0.0.0"`, no [project.urls].
  note:     harmless while nothing is published. If Mytheca is ever released, both matter,
            and a documented versioning scheme (SemVer or CalVer, applied consistently)
            matters more than which one is chosen.
```

```
[ADVISORY] A-2  CONTRIBUTING.md is real, not theatre — keep it
  observed: it documents the validation gate, the non-negotiable rules, and the full
            experiment protocol with a worked example.
  note:     recorded because the default advice for a solo portfolio repo is that
            CONTRIBUTING is checkbox theatre and should be removed. That advice does not
            apply here: this file says how to set up, how to validate, and what happens to a
            change — which is what a real one does. No action.
```

```
[ADVISORY] A-3  No CHANGELOG, SECURITY, CODE_OF_CONDUCT, issue templates or CODEOWNERS
  note:     correct as-is. On a single-owner repo with no releases these are decoration a
            reader recognises as decoration. Revisit CHANGELOG only if Mytheca starts
            cutting versioned releases. Explicitly NOT recommended.
```

---

## Experiment log

Audited against the historical-record rule: a write-up describes the repo as it *was*, and is
corrected additively, never rewritten to match the current tree.

- **19 experiments**, all with status, indexed in `docs/research/INDEX.md`, with a stated contract
  in `AGENT_INSTRUCTIONS.md` and a `Makefile` target that validates it. This is stronger than most
  published research code.
- **Supersession is recorded rather than silent.** EXP-2026-08-019 re-ran EXP-2026-08-018's
  unchanged baseline and moved it by more than the effect 018 reported — and the repo says so, in
  CLAUDE.md and in the checklist, rather than leaving the earlier number standing. This is the
  specific failure the experiment checker exists to find, and this repo already caught it.
- **Failed runs are retained**, with EXP-2026-08-001 kept as a worked example of an aggregation
  error caught in review.
- `docs/research/experiments/` and `docs/plans/archive/` are marked `historical_dirs` in the
  profile. **The restructure must not sweep path renames through them** — doing so would convert a
  true record into a claim that a command was run at a commit where it did not exist.

**One correction is owed, and it is the serious finding of this audit: X-1 above.** EXP-2026-08-015
and EXP-2026-08-016 are `status: planned`, correctly labelled and honestly so — but three other
documents quote them as having measured things. The label is right; the citations are wrong.

The three broken links (H-3) are a separate and much smaller matter: unsubstituted `<slug>` tokens
in template scaffolding, which assert nothing. Turning them into fenced examples is a placeholder
change, not a revision of a record.

---

## What is already good, and should not be touched

An audit that only lists faults misrepresents the repo.

- **Documentation discipline is exceptional.** 246 documentation files and the drift detector
  found nothing but three placeholder links. Every relative link, prose path reference, fenced
  command and tree diagram resolves. This is rarer than any polish item on the list above.
- **The prose is good and it is the owner's.** "from *Myth* + the Greek *Bibliotheca*", the
  event-typing explanation, the stat system description — specific, unhyped, and written by
  someone who knows the system. The rewrite keeps this. Replacing accurate personal prose with
  smoother neutral phrasing is a downgrade even when the result reads better.
- **The honesty is already there.** `docs/checklist.md` states plainly that three of four LLM
  providers have never made a real request, that a UI rebuild was verified by tests rather than by
  eye, and that per-role model routing is a product decision the owner has not made. Repos that
  document their own unproven parts are uncommon. The README should inherit this register, not
  smooth it away.
- **The engine works.** Verified by running it: both servers healthy, a four-character scene
  rendering multi-speaker prose with live stat rails, presence tracking, turn order, and a
  populated story graph.

---

## Triage

Ordered by consequence, not by effort. Detail and sequencing in
[`repo-restructure-plan.md`](repo-restructure-plan.md).

| # | Finding | Why it is here |
|---|---|---|
| 1 | L-1 LICENSE | Legal. Blocks the stated goal outright. |
| 2 | T-1 – T-3 truth | Cosmetic work on top of false claims makes the repo worse. |
| 3 | R-1 – R-3 runnable | The documented path fails at step one and hides its real prerequisite. |
| 4 | S-1 screenshots | Largest gap for the archetype; the asset is captured and waiting. |
| 5 | D-1 Why / When | The two sections this specific reader needs; needs the owner. |
| 6 | W-1 surface the writing | Highest-value artifact in the repo, linked from nowhere. |
| 7 | H-1 – H-3 hygiene | Real reasons, modest payoff. |
| 8 | H-4, S-2 | Diagnosis and a UI fix; separate work. |

---

## Framing, stated plainly

This restructure is **downside elimination**, not interview generation. The best evidence in the
ledger says a repository does not win an interview and can lose one: *"we have passed on candidates
because of them."* The goal is that nothing on this front page costs its owner anything — which is
why the truth gate outranks everything cosmetic, and why the four false claims mattered more than
the missing screenshots even though the screenshots are more visible.

The two items with the strongest outside evidence behind them are the ones this repo cannot use: a
working live demo (+10–20%, employer-written) is impossible here — the app needs a local LLM
endpoint and four data stores — and upstream contribution to other projects, which is outside a
repository's scope entirely and outweighs a great deal of repo polish.
