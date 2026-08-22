# ISSUES — EXP-2026-08-013

## 2026-08-22 — The protocol was written after the renders

The owner asked for visual samples mid-implementation ("please try to generate images…
and I will judge the output"), and the six renders were produced before `PROTOCOL.md`
existed. `PROTOCOL.md` says so at the top.

**Impact on the recorded numbers: none.** The three metrics are computed by
`conformance.py`, which builds the graphs offline and deterministically and never looks at
a rendered image. It was written and run *after* the protocol, over the same fixed subject
strings and seed. The visual half is explicitly labelled exploratory and produced no number.

**Paper implication:** do not present this as a pre-registered result. It is an
implementation-conformance check plus a qualitative demonstration.

## 2026-08-22 — Rendered PNGs are not checked in

The six sample renders (~8 MB total) were reviewed by the owner and are **not** committed.
`render_samples.py` regenerates them from the recorded seed (20260822) against a ComfyUI
server with the same checkpoint and LoRA; the mechanical metrics do not depend on them.

## 2026-08-22 — `code.dirty: true`

The run was made from the `art-style-presets` working tree with the phase-8 documentation
edits uncommitted. The code paths under test (`art_styles.py`, `comfyui.py`) were committed
at `063ac0a` / `88d98cb` and unmodified since; only docs and the world-build wiring were
dirty.

## 2026-08-22 — n_runs = 1, and why there is no ± here

The three metrics are properties of a **deterministic** graph transform — same inputs, same
graph, every time — so repeating the run cannot produce a distribution. `n_runs: 1` is the
correct number, not an under-powered one. The *images* are nondeterministic in the usual
diffusion sense, but no number is computed from them.
