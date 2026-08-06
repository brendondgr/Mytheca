# Checklist — Artifact Evaluation

Most ACM/USENIX venues award three badges. AIIDE offers **optional artifact
evaluation after acceptance**, which is a good fit for a working codebase.

Source: `../../mytheca-research-audit.md` §8 and the research-record contract §8.

## The three badges

### Available — artifact deposited in a public archival repository

- [ ] **⚠️ GitHub alone does not satisfy this.** An archival DOI is required —
      Zenodo, Figshare, or Dryad.
- [ ] **LICENSE file added.** Currently absent; the repository is all-rights-reserved
      by default, which blocks this badge outright and is a ~5-minute fix.
- [ ] Release corpus generated and separately licensed. Evaluation worlds are private
      by decision (`../../DECISIONS.md` D-006), so the released artifact cannot simply
      be the eval set.
- [ ] Confirm whether the GitHub remote is public.

### Functional — documented, consistent, complete, exercisable

- [ ] Headless runner released and documented
- [ ] One-command bring-up documented for a clean machine (`app.py` owns Docker)
- [ ] Every experiment reproducible from its `PROTOCOL.md` §Procedure and
      `RESULTS.md` §8 Reproduction
- [ ] `make validate-research` passes on the released tree
- [ ] `make figures` regenerates every promoted figure with no diff
- [ ] Environment pinned: `uv.lock` + Python version + container digest if used

### Results Reproduced — an independent committee re-obtains the main results within tolerance

- [ ] Tolerance stated explicitly in the paper (LLM outputs are nondeterministic even
      at temperature 0 — every manifest carries a `nondeterminism_note` for this reason)
- [ ] Seeds recorded and re-runnable
- [ ] Model **and version/date** pinned — a provider silently rotating a model alias
      breaks reproduction with no error
- [ ] Wall-clock and cost stated so a committee can budget the re-run
- [ ] Raw per-seed numbers shipped (`data/metrics.csv`), not just aggregates

## Artifact appendix

- [ ] `ARTIFACT_APPENDIX.md` drafted — **start it early.** It is typically ~2 pages
      and **mostly assembles from `manifest.yaml` + `PROTOCOL.md`**, which is why the
      manifest schema carries those fields.

## Venue-specific requirements

- [ ] **NeurIPS E&D** — data hosted at submission; **Croissant metadata with
      Responsible AI fields**; **code release required at submission** for executable
      artifacts. Non-compliance justifies desk rejection.
- [ ] **EMNLP demos** — a live demo link or downloadable package is **required** or
      the submission is desk-rejected.
- [ ] **ACL Rolling Review** — Responsible NLP Checklist and a Limitations section are
      both mandatory.
- [ ] **AIIDE** — Limitations section required; artifact evaluation optional, post-acceptance.
- [ ] **CHI** — all supplementary material and video figures must also be anonymised.

## The end state

A single container holding the article, the analysis, the data, and the environment —
a **research compendium**. The point of this directory is that reaching that state is
**one archival push, not a restructuring project.**
