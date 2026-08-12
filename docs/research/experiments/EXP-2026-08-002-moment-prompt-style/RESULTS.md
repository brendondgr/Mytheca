# RESULTS — EXP-2026-08-002 In-narrative moment prompts: appearance-first, landscape

## 1. Headline

Across 3 runs on one fixed scene, no cast name reached the positive prompt
(`name_leak` = 0.0), every in-frame character was described from their own authored
appearance (`appearance_coverage` = 1.0), and every render came out landscape at
1216×832. The hypothesis survived on this scene — with n = 3, one scene and no baseline
arm, that is a **functional verification, not evidence that the design is better than an
alternative**.

## 2. Results table

<!-- from data/metrics.json — per-run rows, since n = 3 is too small to hide behind a mean -->

| Run | `name_leak` | `appearance_coverage` | `landscape` | frame | figures in frame | `phrases` | seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | 0 | 1.0 | 1 | 1216×832 | 3 | 25 | 38.96 |
| 1 | 0 | 1.0 | 1 | 1216×832 | 3 | 30 | 34.24 |
| 2 | 0 | 1.0 | 1 | 1216×832 | 3 | 26 | 42.15 |
| **mean ± std (n=3)** | **0.0 ± 0.0** | **1.0 ± 0.0** | **1.0 ± 0.0** | — | 3 | 27.0 ± 2.16 | 38.45 ± 3.25 |

Total wall clock 115.4 s for 3 runs (3 LLM calls, 3 ComfyUI renders) on an AMD Ryzen AI
MAX+ 395. Prompts, captions and the rendered WebPs are in `data/` — `metrics.json`
carries the full prompt text of every run, and `data/images/` the images themselves.

## 3. Figures

None. Three runs of a single arm, where every metric is 0.0 or 1.0 with zero variance,
give a bar chart nothing to say that the table above does not; a figure here would be
decoration standing in for evidence. The rendered images in `data/images/` are the
artifact worth looking at.

## 4. Interpretation

The design claim behind the feature — *name the look, not the person* — holds end to end
on the real model and the real renderer: the prompt writer produced phrases like
"middle-aged human woman, silver-streaked dark hair, salt-stained indigo coat" rather
than "Maerin Voss", and the rendered figures are recognisably the authored cast. No entry
in `CLAIMS.md` moves; nothing here is a paper claim. What it licenses is narrow: the
shipped path works, on this scene, with this model.

## 5. Threats to validity

- **Under-powered and single-arm.** n = 3, one scene, one model, no baseline. The
  ablation that would attribute the result to the design (same pipeline with
  `strip_names` and the no-names instruction removed) was **not run**. It is entirely
  possible this model would have avoided names unprompted.
- **`name_leak` = 0 does not isolate the guard.** The metric is measured *after*
  `strip_names` has run, so it cannot distinguish "the model never wrote a name" from
  "the model wrote one and the guard removed it". The unit tests prove the guard removes
  names; this run proves only the end state.
- **Contaminated data.** The scene ships in the repository (`run_moment.py`), so it is
  unusable as a held-out set and may be easier than a real player's world — its cast have
  clean, distinctive `portrait_positive` text, which many authored characters will not.
- **`appearance_coverage` is a lower bound on grounding, not fidelity.** It reads the
  prompt, not the image. Whether the painted figure *looks* like the character is not
  measured here at all, and would need human judgement or a VLM to measure.
- **Temperature 0.7.** The app's saved authoring default, deliberately not lowered. Run
  variance is real and only 3 samples of it were taken.

## 6. What surprised us

Two things. First, `appearance_coverage` hit 1.0 on every run including the third figure
(a bystander who only *acted* in the window and never spoke) — the in-frame selection is
more inclusive than expected, which is the behaviour wanted but was not obviously going
to happen. Second, the first ad-hoc generation (see `ISSUES.md`) exposed a real defect
that the metrics here would never have caught: the keep-alive heartbeat announced the
*render* stage while the prompt was still being written. Watching the stream found it;
no metric in this protocol would have.

## 7. Follow-ups

- [ ] Run the ablation arm (guard + instruction removed) so `name_leak` can be attributed
      rather than merely observed.
- [ ] Measure on characters with **no** `portrait_positive` (appearance prose only), which
      is the common case for hand-authored casts.
- [ ] Judge image fidelity (does the painted figure match the authored look?) — needs a
      VLM judge or human raters; out of scope for a functional verification.

## 8. Reproduction

```bash
# Requires ComfyUI on :8199 and the LLM relay on :4000.
uv run python -m utils.scripts.research.run_moment --runs 3 \
  --experiment docs/research/experiments/EXP-2026-08-002-moment-prompt-style
make validate-research && make research-index
```
