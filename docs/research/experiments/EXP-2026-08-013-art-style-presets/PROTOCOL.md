# PROTOCOL — EXP-2026-08-013 Art style presets

> **Not pre-registered.** The renders were produced before this file was written, at the
> owner's request mid-implementation. Recorded honestly in `ISSUES.md`. Read the
> hypothesis below as what was *checked*, not as what was predicted.

## Question

Does the three-style art pipeline (`app/content/art_styles.py` + the LoRA patch/bypass in
`services/comfyui.py`) actually emit three different looks — and does the graph it queues
carry the LoRA state and tag set the chosen style intends, on every image surface?

## Hypothesis

Exploratory on the visual half — no prior hypothesis about *how* different the three looks
would be; that was for the owner to judge.

Falsifiable on the mechanical half: for every (style × surface) condition, the queued graph
should carry exactly the intended LoRA state and this style's complete tag set with **none**
of the other two styles' tags. Any condition failing that is a defect.

## Setup

- Real ComfyUI 0.28.0 at `http://localhost:8199`, workflow `utils/workflows/ZiT-Workflow.json`,
  base checkpoint `zit_intorealism_zitV60.safetensors`.
- Three arms — `painted` (LoRA `zit_watercolor.safetensors` @ 0.8), `anime` (LoRA node
  bypassed), `photoreal` (LoRA node bypassed) — from `app.content.art_styles.catalog()`.
- Two surfaces: `portrait` (832×1216) and `scene` (1024×576). `scene` is the one used by
  **both** settings and scenarios, so it covers two product surfaces.
- Prompts built by `art_styles.apply_style(...)`; graphs by `comfyui.build_prompt(...)`.
  No LLM is involved: the subject strings are fixed by hand so the **only** thing that
  varies between arms is the style.

## Data

Two hand-written subject strings (one character, one place), fixed in
`render_samples.py`. They ship with this experiment and are not held out from anything.

## Metrics

| Metric | Definition | Direction |
| --- | --- | --- |
| `lora_state_correct` | Conditions (of 6) where the queued graph's LoRA node holds the intended file, **or** no input in the graph still reads the LoRA node's output when the style intends none. | higher is better |
| `own_tags_complete` | Conditions where every comma phrase of the style's tag string for that surface is present in the positive prompt. | higher is better |
| `no_foreign_tags` | Conditions where **zero** phrases belonging only to the other two styles survive in the positive prompt. This is the one that catches a style switch that does not switch. | higher is better |

## Baselines

The pre-change behaviour is the `painted` arm by construction: its tag strings were moved
verbatim out of the four agent modules, so `painted` **is** the baseline and a difference
there would be a regression, not a result.

## Procedure

```bash
# 1. mechanical conformance (offline, deterministic, no GPU)
cd web/backend && ../../.venv/bin/python \
  ../../docs/research/experiments/EXP-2026-08-013-art-style-presets/conformance.py

# 2. visual samples (needs ComfyUI at :8199) — seed fixed at 20260822 across arms
cd web/backend && ../../.venv/bin/python \
  ../../docs/research/experiments/EXP-2026-08-013-art-style-presets/render_samples.py portrait
cd web/backend && ../../.venv/bin/python \
  ../../docs/research/experiments/EXP-2026-08-013-art-style-presets/render_samples.py scene \
  "fog-bound harbor at dawn, rotting jetties, tide-eaten sea wall, moored hulls, lanterns in the mist, wet timber and brine, cold slack tide"
```

## What would falsify this

Any of the three metrics below 6/6. Concretely: a `photoreal` render whose negative prompt
still pushes `photorealistic` away, or an `anime` render whose graph still routes through
the watercolor LoRA, would each be a condition failed and a defect to fix — not a result to
report.
