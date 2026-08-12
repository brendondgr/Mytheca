# PROTOCOL — EXP-2026-08-002 In-narrative moment prompts: appearance-first, landscape

> Pre-registered before the recorded run. Two ad-hoc generations were made earlier while
> the feature was being built (one via `curl`, one by clicking **Go** in the browser);
> those are **not** part of the n below and are noted in `ISSUES.md`.

## Question

When a player asks the story player to picture the moment they are in, does the emitted
ComfyUI prompt describe the people in the shot — appearance and action — instead of
naming them, and does the image come out wider than it is tall?

## Hypothesis

Across every run: no cast name survives into the positive prompt, every in-frame
character is described using at least one token from their own authored appearance, and
the rendered frame is landscape.

## Setup

The shipped pipeline, unmodified:

- `web/backend/app/services/scene_moment.py` — `prepare_moment` gathers the recent beats,
  the present in-frame cast, the place and the world; `generate_moment` calls the prompt
  writer, renders through `services/comfyui.py` at a pinned **1216×832**, converts to WebP.
- `web/backend/app/agents/moment_agent.py` — the system prompt that forbids names and
  demands appearance + action per figure, plus `strip_names`, the deterministic guard that
  rewrites any leaked name as that character's own visual tag.

Single arm. The **LLM and ComfyUI are real** (`localhost:4000` relay, model `skynet`;
ComfyUI 0.28.0 on `localhost:8199`). Neo4j and Qdrant are disabled — neither reaches the
moment prompt today, so the measurement is unaffected, but it is stated rather than
assumed.

## Data

One fixed scene built in memory by the entrypoint (`utils/scripts/research/run_moment.py`):
a three-character tavern standoff (a harbor-mistress, a captain, an informant), each with
authored `appearance` prose and a `portrait_positive`, over a five-beat transcript. It
ships with the repository as source code, so it is **contaminated for any held-out use** —
it exists to exercise the pipeline, not to estimate performance on unseen worlds.

## Metrics

| Metric | Definition | Direction |
| --- | --- | --- |
| `name_leak` | 1 if any cast name — full name, or any token of it ≥4 characters — appears word-bounded and case-insensitively in the positive prompt; else 0. Denominator: runs. | lower (0) |
| `appearance_coverage` | Per run: the fraction of in-frame characters for whom ≥1 distinctive token (≥5 characters, excluding generic art words like "watercolor"/"portrait"/"human") from *their own* `appearance` + `portrait_positive` appears in the positive prompt. | higher (1.0) |
| `landscape` | 1 if the rendered WebP's width exceeds its height; else 0. | higher (1.0) |
| `phrases` | Count of comma-separated phrases in the positive prompt — a shape check against the agent's stated 14–24 range, not a quality measure. | descriptive |
| `wall_clock_seconds` | Per run: prompt write + ComfyUI render + WebP write + persist. | descriptive |

`appearance_coverage` is a **lower bound on grounding**, not a measure of image fidelity:
it proves the character's authored look reached the prompt, not that the model painted it.

## Baselines

None. This is a single-arm verification of a shipped path, not a comparison. The obvious
baseline — the same pipeline with the name guard and the appearance instruction removed —
was **not** run; nothing here licenses a claim that the guard is what made the difference.

## Procedure

```bash
# ComfyUI on :8199 and the LLM relay on :4000 must be reachable.
uv run python -m utils.scripts.research.run_moment --runs 3 \
  --experiment docs/research/experiments/EXP-2026-08-002-moment-prompt-style
```

## What would falsify this

Any run whose positive prompt still contains a character name, whose coverage is below
1.0 (a figure invented rather than described from the record), or whose rendered image is
portrait-orientation.
