# Restructure plan — Mytheca

**Against:** [`repo-audit-report.md`](repo-audit-report.md) · **Profile:** [`repo-profile.yaml`](repo-profile.yaml)
**Date:** 2026-08-31 · **Baseline commit:** `3dd8438` (clean tree, branch `main`)

**APPLIED 2026-08-31**, on branch `repo-audit-restructure`, after owner approval. Phase-by-phase
outcomes are recorded at the foot of this file; the plan text above them is left as written so the
plan and what happened can be compared. Destructive steps are named
individually with their consequence, never bundled into a "cleanup" line.

Owner decisions already taken (2026-08-31): licence **MIT**; GitHub repository **renamed to
Mytheca**; screenshots **captured from the running app**; **no hosted demo** — self-host only.

---

## Sequencing rule

The stages are dependency-ordered and the order is not cosmetic:

- **Truth before presentation.** Every README claim is corrected *before* the README is restyled.
  A polished false claim is worse than an unpolished one.
- **Assets before links.** No image or link is written into the README until the file exists and
  resolves. `check_links.py` runs before the README is committed, not after.
- **Propagation inside the same commit as the move.** A structural change that leaves
  `CLAUDE.md`, `docs/structure.md` or `CONTRIBUTING.md` describing the old tree is an incomplete
  change, not a finished one plus a follow-up.
- **`docs/research/experiments/` and `docs/plans/archive/` are exempt from every rename.** They are
  historical records. Sweeping a path change through them would turn a true record into a claim
  that a command was run at a commit where it did not exist.

Each phase is one commit, and the validation gate from `CONTRIBUTING.md` runs before each.

---

## Phase 1 — Licence  *(blocker L-1)*

**Additive. No risk.**

| Action | Detail |
|---|---|
| Add `LICENSE` | MIT, root, `Copyright (c) 2026 Brendon` — **owner to confirm the exact name string** |
| Edit `pyproject.toml` | add `license = "MIT"` as a PEP 639 SPDX string (not the older table form) |
| Edit `README.md` | one Licence line at the foot |

**Verify:** `ls LICENSE && grep '^license' pyproject.toml`

---

## Phase 2 — Truth  *(blockers T-1, T-2, T-3; major R-2)*

**Edits to prose and one config default. No moves.** This is the phase that matters most and the
one with the least visible result.

| File | Change |
|---|---|
| `README.md` "How it works" | Replace the ReAct paragraph. The turn is planned **once**, at HIGH reasoning effort, and that plan is a contract the loop executes without re-planning. Name the two exceptions that outrank it (undelivered player direction; the scene-opening narration emitted before the plan exists). Keep the per-speaker isolation claim; **drop** "a visible in-voice deliberation". |
| `README.md` Mermaid diagram | Update the `Planner` edge label — it currently reads "who acts next, one beat at a time". |
| `README.md` "Key features" | "per-beat ReAct planner" → the bound plan. LLM bullet → four providers, **with** the checklist's own caveat that only `openai-compatible` has made a live request. |
| `README.md` "Tech stack" | AI row → provider-dispatched adapters, four named. |
| `.env.example` | `TURN_PLANNER_LOOKAHEAD=1` → `0`, matching `core/config.py:91`. Rewrite the comment above it and the `TURN_MAX_BEATS` comment, both of which still describe the ReAct loop. |

**New material this phase adds** (currently absent from the README entirely, and all of it true):
the two turn engines (`structured` / `freetext`) and that `sceneMode` chooses between them; plan
mode; the narrative style guide; the three art styles. Kept to a few lines each — the README is a
front page, not the manual.

**Verify:** `grep -n "ReAct\|deliberation" README.md` returns nothing in the architecture prose;
`.env.example` defaults diffed against `core/config.py` field defaults.

---

## Phase 3 — Runnable  *(blocker R-1; major R-3)*

**Depends on the GitHub rename, which only the owner can perform.**

| Action | Detail |
|---|---|
| **Owner, on github.com** | rename `brendondgr/Velora` → `brendondgr/Mytheca`. GitHub redirects the old URL, so no existing clone or link breaks. |
| Rewrite the Quickstart | real clone URL, `cd Mytheca`, and the command block run verbatim in an empty directory before it is committed |
| Add "What you need to bring" | the LLM endpoint as a **first-class prerequisite**, not a parenthetical: an OpenAI-compatible endpoint, a capability floor, and the honest note about the other three providers. **Needs the owner** — I can describe the shape but not state a hardware floor I have not measured. |
| Disclose the slow steps | first `uv sync`, first `npm install`, and the Docker image pulls, so a stranger can tell a slow step from a hang |

**Verify:** run the Quickstart block verbatim from an empty directory on this machine, and record
what it does not cover (not a container, not macOS, not Windows, LLM settings row already primed).

---

## Phase 4 — Showcase  *(major S-1)*

**Additive. Repo-size cost stated below.**

Captured during the audit and ready:

| Asset | What it shows | Verdict |
|---|---|---|
| story player, Parchment | a four-character scene mid-turn: multi-speaker prose, stat rails, scene state, turn order, the direction composer | **hero** — clean, and it is the product |
| story player, Slate | the same scene, default theme | second image, carries the theming claim |
| library shell, Parchment | scenarios / characters / settings columns | **hold** — S-2 text overlap is visible |
| story graph, Parchment | node and edge types, live counts | **hold** — the graph clusters small in a large empty canvas; it reads as sparse |

| Action | Detail |
|---|---|
| Create `docs/assets/` | the default location: ships with clones, survives host changes, relative links work |
| Commit 2 PNGs | captured at 2× device scale, constrained with the HTML `width` attribute |
| Alt text on both | describing what the reader is looking at, not what the file is |
| Hero above the fold | first screen must answer what this is, what it looks like, whether it is alive, and why it exists |

**Repo-size cost, stated because it is permanent:** two PNGs, roughly 1.5 MB combined at 2×. Git
keeps every version of every binary forever, so re-shooting these ten times is 15 MB of permanent
history. Re-shoot deliberately, not casually.

**Not doing:** a GIF. It is the better format for showing a turn stream in, but a good one needs a
recorded play-through, and the turn latency this repo has already measured and written eight pages
about would make a truthful recording a slow watch. Worth revisiting; not worth guessing at now.

**Verify:** `audit_assets.py .` then `check_links.py . --rendered` against the **published** page —
local preview renders things GitHub does not.

---

## Phase 5 — Why, When, and the writing  *(major D-1, W-1)*

**Needs the owner. I will not invent a motivation.**

| Action | Detail |
|---|---|
| Write the **Why** | The answer already exists in the owner's own words at `docs/briefings/storyline-chat-briefing.md` §3: *"The AI generates validated story events; the UI renders them. The AI never decides UI layout."* I will draft two paragraphs from that plus the multi-character premise, and the owner corrects it. It is a claim they may be asked to defend, so it has to be theirs. |
| Write the **When** | One line: active, solo, started June 2026, self-host only, no authentication, no deployment target chosen. Drawn from `docs/checklist.md`, which already says all of it. |
| Move the PDF | `reports/mytheca-latency-report.pdf` → `docs/research/mytheca-latency-report.pdf`, via `git mv` so history follows |
| Link it | from the README's research section — an eight-page analysis nobody can find is worth nothing |
| **Delete `reports/`** | *(destructive — named individually)* the directory is empty after the move. Consequence: none; nothing references the path, verified by grep across `README.md`, `CLAUDE.md`, `CONTRIBUTING.md` and `docs/*.md`. |

**Verify:** `grep -rn "latency-report" README.md docs/` resolves; `audit_readme.py . --sections`
reports why and when present.

---

## Phase 6 — Layout and hygiene  *(minor H-1, H-2, H-3)*

Three destructive or structural steps, each named with its consequence.

| Action | Consequence |
|---|---|
| **Delete `libs/`** *(destructive)* | Contains only `.gitkeep`; empty for the full ten weeks of the project. Referenced in `docs/structure.md:19` and `:137` as "currently empty" — both lines are rewritten in this commit to say the intent in prose instead. No code imports it. |
| **Move `line_counter.py` → `utils/scripts/`** *(structural)* | `git mv`, so history follows. Referenced in `CLAUDE.md` and `docs/structure.md`; **both updated in this same commit**. Not referenced by any code — it is a standalone utility, which is why it does not belong beside `app.py`. |
| Fix the three placeholder links | Substitute real figure names in EXP-2026-08-015 and EXP-2026-08-016. **This is substitution, not revision** — the token was never a fact, so the historical-record rule is not engaged. In `docs/research/templates/experiment/RESULTS.md`, turn the token into a fenced example so the next copy cannot inherit a broken link. |
| Add `.github/workflows/ci.yml` | `uv run pytest`, `npm test`, `npm run typecheck` on push and PR to `main`. `permissions: contents: read`. **Recommended for what it does — it would have caught R-1 and R-2 — not because a green badge signals anything.** No matrix, no coverage gate. |

**Propagation is the work here, not the moves.** `audit_docs.py . --governing` must exit 0 as the
last step; a non-zero exit is a failed migration, not a follow-up ticket.

**Explicitly not doing:** CHANGELOG, SECURITY.md, CODE_OF_CONDUCT.md, issue templates, CODEOWNERS.
On a single-owner repo with no releases these are decoration a reader recognises as decoration.

---

## Phase 7 — Re-audit

Run every instrument again and diff against this baseline.

```
audit_structure.py . --json      # expect: no LICENSE finding
audit_docs.py . --governing      # expect: exit 0
audit_readme.py . --sections     # expect: why + when present, funnel intact
check_links.py . --rendered      # expect: 0 broken, images resolve on the PUBLISHED page
audit_assets.py .                # expect: no orphans, no missing referents
audit_experiments.py .           # expect: unchanged — nothing above touches the record
```

Then update `repo-profile.yaml`: `entrypoints.verified`, `showcase.assets_dir`,
`showcase.showable`, and `repo.name` if the rename has landed.

---

## Out of scope, and why

| Item | Reason |
|---|---|
| **H-4** first-boot migration error | Needs reproduction on a fresh database before anyone knows what the fix is. Diagnosis, not restructure. |
| **S-2** character-card text overlap | A frontend defect. It belongs in the frontend's own change, with the accessibility and responsive pass `CONTRIBUTING.md` requires. It gates the library screenshot, which is why Phase 4 holds that shot. |
| Anything in `docs/research/experiments/` | Historical record. Nothing in this plan may edit it except the placeholder substitution in Phase 6. |
| A hosted demo | Impossible: the app needs a local LLM endpoint and four data stores. This is the one showcase item with employer-written scoring behind it, and it is genuinely unavailable — which is why Phase 4 puts the effort into in-repo assets instead. |
| Code quality, tests, types | Not audited. No finding here claims anything about how well the engine is built. |

---

## Rollback

Every phase is one commit on a branch off `main`; nothing is pushed. `git revert` restores any
phase independently. No history rewrite is proposed — `history_rewrite_allowed: false` in the
profile, and nothing found in this audit requires one. No secret was ever committed, so there is
no rotation obligation hiding behind a rewrite.

---

## Approval

Sign-off needed on the three destructive or externally-visible items before anything is applied:

1. **Delete `reports/`** after moving the PDF into `docs/research/` (Phase 5).
2. **Delete `libs/`**, replacing it with a sentence in `docs/structure.md` (Phase 6).
3. **Move `line_counter.py`** to `utils/scripts/`, updating `CLAUDE.md` and `docs/structure.md` in
   the same commit (Phase 6).

And two things only the owner can supply:

4. The **GitHub rename** (Phase 3) — Phase 3's Quickstart is not true until it lands.
5. The **Why**, the **LLM capability floor**, and the **copyright name string** (Phases 1, 3, 5).

---

# What actually happened

Recorded after the fact. Where reality diverged from the plan, the divergence is the useful part.

## Delivered as planned

**Phase 1 — Licence.** MIT at the root, `license = "MIT"` + `license-files` in `pyproject.toml`.
The copyright line reads `brendondgr`; **replace it with your legal name** if you want it to be
enforceable as written.

**Phase 2 — Truth.** All four false claims corrected. One extra was found while verifying them:
`CLAUDE.md` named `voiced` as the `sceneFlow` default when `turn_settings.DEFAULT_SCENE_FLOW` has
read `continuous` since 2026-08-24. Being wrong in a governing-rules file outranks being wrong on
the front page, since agents and contributors act on it.

**Phase 3 — Runnable.** Quickstart rewritten against a real URL. "You need to bring a model" now
leads the prerequisites instead of hiding in a comment. Slow first-run steps disclosed.
**Still owed by the owner: the GitHub rename.** Until `brendondgr/Velora` becomes
`brendondgr/Mytheca`, the clone command in the README is a claim the remote does not honour.

**Phase 4 — Showcase.** Two screenshots at `docs/assets/`, Slate theme per the owner's preference.
Three deviations from the plan, all improvements:
- The cast had no portraits, so ComfyUI was started and all six were generated through the app's
  own agent → render → persist path. Setting art followed, because five cards reading
  "setting plate" is what an unfinished screenshot looks like.
- The library shot was **un-held** — see the S-2 withdrawal below.
- Format is JPEG, not PNG. WebP was 7× smaller and tempting; GitHub's own documentation lists
  PNG, GIF, JPEG and SVG and **does not list WebP**, so it was not used. Verified by fetching the
  docs, not by assuming. 904 KB total against 3 MB for equivalent PNGs.

**Phase 5 — Why / When / the writing.** Written from the owner's own briefing. `reports/` deleted,
the latency report moved into `docs/research/` and linked from the README.

**Phase 6 — Layout and hygiene.** `libs/` deleted, `line_counter.py` moved, every inbound
reference updated in the same commit. CI added. The plan named three doc-gate scripts for CI and
one of them — `check_doc_links.py` — **did not exist**; writing a workflow step that referenced a
missing script would have been the same class of error this audit exists to find. It was written
(stdlib only, skips historical directories) and found two broken links and one bug in itself on
its first run.

## The finding that changed shape

**X-1 was resolved, not just recorded.** The quoted "18, 22 and 24 beats" traced to nothing in the
record — and then the world holding the evidence appeared on the deletion list. The event log was
recovered first: 139 events proving EXP-2026-08-016 ran on 2026-08-25 and was simply never
written up. Two things the citations had missed:

1. The figure was the **milder half**. Those are the `voiced` arm's worst turns; `continuous`
   produced a **38-beat** turn, above `TURN_MAX_BEATS`, appearing in none of the citing documents.
2. The arms **are** identifiable — `ISSUES.md` records them in passing, which my first pass
   claimed was impossible and got wrong.

The experiment now has data, a metrics script, a filled RESULTS, manifest and INDEX row.
`make validate-research` passes. **The `status: failed` I assigned is the owner's to revise** —
assigning a status is a judgement about your own work, not an inference from the text.

## The finding that was wrong

**S-2 is withdrawn.** I claimed the character-card badge overlapped the name; measuring the DOM
gives a 4 px gap and no overlap. I had read it off a downscaled screenshot. It is kept in the
report as withdrawn rather than deleted, because a retracted finding is part of the record, and
because it cost a real decision — the library screenshot was held back for it.

## Still open

| Item | Owner action |
|---|---|
| GitHub rename `Velora` → `Mytheca` | Only you can do it. The README's clone URL is wrong until then. |
| LICENSE copyright name | Currently `brendondgr`; a legal name is conventional. |
| The **Why**, and the LLM capability floor | Drafted from your briefing. Correct them — they are claims you would have to defend. |
| EXP-016 `status` | I set `failed` with reasoning. Yours to revise. |
| H-4, first-boot migration error | Needs reproduction on a genuinely fresh database. |
| 301 orphaned media files, 72 MB | From the deleted worlds. `media/` is gitignored so this is disk, not repo weight. `POST /api/options/media/cleanup` clears it. Not run — deleting more of your data unasked was not mine to decide. |
