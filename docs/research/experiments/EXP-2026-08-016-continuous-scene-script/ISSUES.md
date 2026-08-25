# ISSUES — EXP-2026-08-016

Bugs, anomalies, aborted runs, excluded seeds, and anything that could not be
recovered. One entry per issue, newest last. If nothing went wrong, write
"No issues recorded." — do not delete the file.

## YYYY-MM-DD — <one-line summary>

**Impact:** what this does to the numbers. If a seed was dropped, state the new n.
**Cause:** what actually happened.
**Resolution:** what was done about it, or "none — accepted".
**Paper implication:** what the paper must state because of this. Often "none".

## 2026-08-24/25 — blocked: the local model never came back

**Status stays `planned`, not `failed`.** Nothing ran, so there is nothing to report as a
result; recording it as a failed run would put an empty row in the ledger and imply the
design was tried and did not work. It was not tried.

What happened, so nobody repeats the diagnosis:

- The relay (`DashLLM`, `:4000`) reported `local` → `gemma-4-26B-it` as **`failed`** for a
  continuous four-hour watch (`60 s` poll). `skynet` stayed healthy throughout.
- **`local` was not starved — it was absent.** There was no `llama-server` process at all.
  The relay only *registers* endpoints; it does not own the upstream process, so nothing on
  the relay side could bring it back.
- **ComfyUI was holding 18 GB of VRAM** (PID on GPU 1, `main.py --port 8199`) and was stopped
  to give the model room. That freed the memory — `rocm-smi` then showed only
  `linux-whisper` at 1.7 GB — and did **not** bring `local` back, which is what established
  that the model was missing rather than out of memory. ComfyUI needs restarting from the
  owner's launcher; it is unrelated to prose and nothing here needs it.
- This machine is **AMD** (`rocm-smi`), not NVIDIA. `nvidia-smi` does not exist. Worth
  knowing before diagnosing a GPU problem here again.

**`skynet` was deliberately not substituted.** It is healthy and would have produced numbers,
but the owner has stated it is not suited to this kind of generation — so a prose-quality
result measured on it would be a fact about `skynet`, not about the change under test. A
number from the wrong model is worse than no number, because it gets quoted.

Both runners, both protocols and the pre-fix worktree for EXP-2026-08-015's baseline arm are
complete and were verified up to the point of generation. The runs are one healthy endpoint
away.
