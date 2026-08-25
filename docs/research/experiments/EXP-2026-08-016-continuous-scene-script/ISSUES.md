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

## 2026-08-25 — GPU contention changed mid-run

The endpoint came back and the run started. Part way through, a **GPU-using application
(Minecraft) was closed by the owner**, between `continuous` turn 3 and `voiced` turn 4.
Turns 1–3 of both arms therefore ran with the GPU shared; turns 4–6 did not.

**What this invalidates, and what it does not.**

- **Timing is not comparable across the run.** `seconds` per turn for turns 1–3 was measured
  under contention and turns 4–6 were not, so the cost metric has a step change in it that
  has nothing to do with `sceneFlow`. Per-turn seconds are still reported; the run-level mean
  is not a measurement of the arms.
- **The primary metrics are unaffected.** `cross_speaker_rate`, `misattribution_rate` and
  `voice_distinctness` are properties of the text. A slower GPU produces the same tokens,
  just later. The decision rule in PROTOCOL § 6 rests on these three and is intact.
- **Beat counts are unaffected.** `voiced` turn 3 produced 18 beats and `continuous` turn 3
  produced 3. That is the planner's decision about how long a turn should be, taken before a
  single prose token is generated, and GPU load cannot move it.

Interleaving turn by turn (PROTOCOL § 4) is what limits the damage: both arms straddle the
change rather than one arm sitting entirely on either side of it. It does not remove it.

This is recorded because this repository has a case on file — see
`mytheca-verify-the-environment-before-concluding` — of a 66x latency swing that was a
disconnected GPU rather than the code. An unrecorded environment change is exactly how that
happens twice.

## 2026-08-25 — the planner still does not reliably end a turn

`voiced` turn 3 produced **18 beats in 4524 s**, against 3–8 beats for every other turn
measured so far. `TURN_MAX_BEATS` (24) was not reached, so this was the planner choosing to
keep going, not a backstop firing.

This is the failure mode `_pressure()` was added to address after removing the `maxTurns`
cap, and it shows the fix **reduced the problem without closing it**. It is out of scope for
this experiment — recorded here so it is not mistaken for a `sceneFlow` effect, and carried
to `docs/checklist.md` as its own open item.

## 2026-08-25 — the runaway backstop does not cover the continuous path (defect found by this run)

`continuous` turn 4 produced **38 beats**. `TURN_MAX_BEATS` is 24, floored at
`2 x cast + 6` = 12, so 38 is above the backstop the engine is supposed to enforce.

Verified in code, not inferred from the number. `turn_engine.py:311`:

```python
scripted, planned = yield from beat_runner.continuous_turn(...)
while not scripted and beats < max_beats:
```

The `max_beats` guard is a condition of the **per-speaker loop**. When the script comes back
scripted, that loop never runs, and the segments parsed out of the script are emitted with no
ceiling at all. The backstop protects the path that is no longer the default.

`voiced` turn 4 hit exactly **24** beats the same turn — the backstop doing its job — which is
what makes the comparison legible: the same player line ran away in both arms, and only one
arm had a brake.

**Not fixed during the run.** Changing the engine mid-experiment would mean the six turns
share no single build and the arms stop being comparable. Carried to `docs/checklist.md`.

Noted alongside it: this is the **first turn in the run with a non-zero `cross_speaker_rate`**
(0.0789, continuous). A 38-segment script losing track of who is speaking is a plausible
mechanism, but with one occurrence that is a hypothesis, not a finding.

## 2026-08-25 — run abandoned at 10 of 12 turns, by owner decision

Stopped deliberately after `continuous` turn 5. Turns completed: 5 `voiced`, 5 `continuous`.
Recorded rather than deleted, per the research contract.

**Status stays `failed`, and no aggregate is computed.** Ten of twelve turns is not
five-and-five drawn at random: the run was stopped *because* the `voiced` arm was producing
18-24 beat turns, so the arm that was slow is the arm whose last turn is missing. Averaging
the survivors would report the arms as more similar than the data supports. Per-turn rows
only — `EXP-2026-08-001` is the worked example.

**The run is still worth what it cost.** It was not a null result: it found two bounding
defects (above) and the reason both arms are slow (below), none of which were visible before.

## 2026-08-25 — why a single turn takes so long (measured, not inferred)

Direct measurement against the same endpoint, one character-style beat, 2048-token allowance:

| reasoning_effort | completion tokens | reasoning chars | prose chars | waste |
| --- | --- | --- | --- | --- |
| (default) | 1243 | 5161 | 320 | **94 %** |
| `low` | 884 | 3132 | 561 | 85 % |
| `none` | 759 | 2851 | 384 | 88 % |

**94 % of every generated beat is reasoning the player never sees.** A 320-character
paragraph cost 1243 tokens. `reasoning_effort` reduces it by roughly half and **cannot turn
it off** — the endpoint runs with `--reasoning-budget -1`, a server-side setting outside this
repository.

Multiply that by the turn loop: `turn_planner_lookahead` is **1**, so the planner is called
once per beat, on top of the prose call and the checks. A 24-beat turn is therefore ~24
planner calls plus ~24 prose calls, each paying the same 94 % overhead, which is how one
player message became 1899 s.

The slowness is not the scene flow and not the model being slow — measured throughput was
31-78 tok/s. It is **beat count x calls per beat x reasoning overhead**, and all three are
addressable.
