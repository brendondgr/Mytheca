# RESULTS — EXP-2026-08-013 Art style presets

**Status:** complete · **Date:** 2026-08-22 · Numbers below come from
[`data/metrics.json`](data/metrics.json), written by [`conformance.py`](conformance.py).

## Headline

All 6 conditions (3 styles × 2 surfaces) queue the graph their style intends.

| Metric | Result |
| --- | --- |
| `lora_state_correct` | **6 / 6** |
| `own_tags_complete` | **6 / 6** |
| `no_foreign_tags` | **6 / 6** |

## Per condition

| Surface | Style | LoRA intended | LoRA in graph | LoRA node still wired | Own tags | Foreign tags |
| --- | --- | --- | --- | --- | --- | --- |
| portrait | painted | `zit_watercolor.safetensors` | `zit_watercolor.safetensors` | yes | 7 / 7 | 0 |
| portrait | anime | *(none)* | — | **no** | 8 / 8 | 0 |
| portrait | photoreal | *(none)* | — | **no** | 8 / 8 | 0 |
| scene | painted | `zit_watercolor.safetensors` | `zit_watercolor.safetensors` | yes | 8 / 8 | 0 |
| scene | anime | *(none)* | — | **no** | 9 / 9 | 0 |
| scene | photoreal | *(none)* | — | **no** | 8 / 8 | 0 |

"LoRA node still wired" is the bypass check: for the two LoRA-less styles, **no** input
anywhere in the queued graph still reads node `72`'s output, so the render runs on the base
checkpoint. The node itself remains in the graph, orphaned — the workflow file on disk is
treated as a read-only template.

## What the `no_foreign_tags` column is actually protecting

It is the only one of the three that catches the failure this feature is most likely to
have shipped with. `apply_style` **drops** competing style phrases before appending its own,
because a prompt stored while the entity was `painted` still ends in `watercolor portrait,
soft washes` — and, worse, `painted` and `anime` both push `photorealistic` away in the
*negative* prompt, which would flatly contradict a `photoreal` render. Appending alone
would have passed `own_tags_complete` while producing muddled images.

## The visual half (qualitative, no number)

Six renders at a fixed seed (20260822), one per condition, with the subject string held
identical across arms so the style is the only variable. Reviewed by the owner; not checked
in (see `ISSUES.md`). Regenerate with `render_samples.py`.

The three arms were visually distinct and each matched its label — the painted arm reading
as watercolor-over-ink with paper showing through, the anime arm as flat cel shading with
bold linework, the photoreal arm as a photograph with natural skin and lens character. This
is a demonstration, not a measurement: no rater, no rubric, n = 1 per condition. **Nothing
in a paper should cite this paragraph as evidence of style quality** — only that the
pipeline produces three separable looks.

## Limitations

- One subject per surface. Style separation on a *hard* subject (a non-human species, a
  crowd, an abstract place) is untested.
- `anime` and `photoreal` are prompt-only here because no LoRA for either is installed.
  Both are one Options change away from carrying one, and that path is untested with a real
  LoRA file — only with the graph patch, which `test_comfyui_lora.py` covers.
- The `moment` surface (the in-play scene image) was not rendered. Its tags are covered by
  the same catalog and by `utils/tests/backend/api/test_play_moment_style.py`, but it has no
  sample in this experiment.
