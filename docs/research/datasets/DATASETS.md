# Datasets

Provenance, licence, version, and access instructions for every dataset used or
produced. One datasheet per dataset in `cards/`.

## Current state: there is no evaluation dataset

**Mytheca has never produced or consumed an evaluation dataset.** No annotated data,
no held-out split, no human labels, no released corpus. This is recorded here rather
than left to be inferred, because "no dataset" and "dataset not yet documented" are
very different states and only one of them is honest about the work remaining.

Consequently the contract's back-fill step (§9.3) had nothing to back-fill. No
experiment folder in this repository has an unrecoverable-provenance dataset,
because no experiment predates the record.

## Available scene sources

### Embergate (the shipped seed world)

| Field | Value |
| --- | --- |
| **Name** | Embergate — a maritime-intrigue harbour town |
| **Location** | `web/backend/app/core/seed.py` |
| **Provenance** | Authored for this project. Original — not a licensed IP, not a known fictional setting |
| **Version** | Tracked with the repository; no independent version |
| **Licence** | ⚠️ **None.** The repository has no LICENSE file, so this is all-rights-reserved by default and cannot currently be released |
| **Access** | Ships with the repo; created by the bootstrap seeder |
| **Fit for evaluation** | ⚠️ **Contaminated for held-out use** |

**Why contaminated.** It is committed to a repository with a GitHub remote whose
public/private status could not be determined. If that remote is or becomes public,
Embergate can enter future training corpora. `DECISIONS.md` D-006 therefore restricts
it to tooling shakedowns and structural experiments; anything destined for a paper
runs on private, uncommitted worlds.

`EXP-2026-08-001` knowingly uses Embergate and says so in its `RESULTS.md`.

### The contamination asset — worth protecting

Mytheca's characters and worlds are **user-authored originals, not famous fictional
figures.** Peng & Chen (SIGDIAL 2026, arXiv:2603.03915) show that memorisation of
famous characters inflates published role-play scores; that pathway does not apply
here. The audit calls this the project's single strongest methodological asset.

Two things would spend it:

1. Committing a fixed evaluation world to a public repository.
2. Reporting **absolute** quality scores. Genre conventions — maritime intrigue,
   guilds, a drowned harbour — are heavily represented in training data even when
   the specific characters are not. **Report relative comparisons between arms.**

## Datasets that must be built

| Dataset | For | Status | Blocked by |
| --- | --- | --- | --- |
| 3 private evaluation worlds, 4–6 characters each, 25 scenes × ≥15 beats × 3 seeds | P1 / `C-001` | Not started | W3 headless runner |
| Label-stripped transcript set with speaker ground truth | P1 primary metric | Not started | The above |
| Human speaker-attribution annotations, ≥2 raters | P1 primary metric | Not started | Ethics-review route unconfirmed |
| Adversarial lore-grounded query set | `C-004` retrieval gate | Not started | — (the gate's trigger conditions are enumerable, so this is cheap) |
| Contradiction-opportunity scene set | `C-006` consistency guard | Not started | Guard firing rate is not logged |

## Reference datasets worth measuring against

- **FIREBALL** (ACL 2023, DOI 10.18653/v1/2023.acl-long.229) — ~25,000 real D&D
  sessions with **gold** game state paired to natural language. The structured-state
  format is a template for evaluating `assembler.py`. Mytheca has no comparable gold
  human data.
- **TALES** (arXiv:2504.14128) — pip-installable, unifies TextWorld/ALFWorld/
  ScienceWorld/Jericho. Single-agent, so adjacent rather than directly applicable.

## Rules for anything added here

- A dataset without a `cards/` datasheet does not count as documented.
- Large artifacts never enter `docs/research/` — store a pointer and a hash in the
  experiment's `data/POINTERS.md`.
- Record provenance honestly. Unknown provenance is written as `unknown`, not guessed.
