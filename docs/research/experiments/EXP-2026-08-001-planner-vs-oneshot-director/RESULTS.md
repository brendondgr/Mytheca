# RESULTS — EXP-2026-08-001 ReAct per-beat planner vs. the one-shot speaker-set director

**Status: `failed`.** Written from `templates/negative_result.md` because this
experiment did not return a null result — it failed to test its hypothesis at all.
Those are different things and the distinction is the entire content of this file.

## 1. Headline

No LLM endpoint was reachable, so every agent in the turn loop took its best-effort
fallback path and the experiment could not test C-005. **12 of 18 turns raised
`APIError: Configure a model endpoint in Options first.`; the 6 that "succeeded"
produced one narrator beat each and zero character beats, in one arm only.** The
hypothesis is neither supported nor refuted; `C-005` remains `unsupported`.

## 2. Results table

`metrics.values` is deliberately **empty**. There is a number that could have gone
here, and this section exists to explain why it did not.

The first run of this experiment aggregated over the turns that did not raise, and
produced:

```
beats = 1.0 ± 0.0  (n=6)
```

That is clean-looking, reproducible, and worthless. The six surviving rows are **not
a random subsample**: they are the planner arm's non-LLM fallback, which emits a
single narrator beat and stops. The director arm contributed **zero** usable rows,
because its `who_is_up` call raises before any beat is emitted. So the "aggregate"
was one arm's heuristic, reported as though it were a two-arm comparison, with a
standard deviation of exactly zero that looked like consistency and was actually the
same fallback firing six times.

The runner was changed to refuse this (`run_scene.py`: if any turn fails, publish
per-run rows and totals, publish no aggregate). The raw rows are in
`data/metrics.csv` and remain fully inspectable.

| Arm | Turns run | Turns raising | Character beats | Distinct speakers |
| --- | --- | --- | --- | --- |
| `planner` | 9 | 3 | 0 | 0 |
| `director` | 9 | 9 | 0 | 0 |

LLM calls: **0.** Input tokens: **0.** Output tokens: **0.** Wall clock: 1.2 s across
all 18 turns — which is itself the tell. A real two-arm run of this protocol would
take minutes, not a second.

## 3. Figures

None. Every figure in this record must be generated from `data/metrics.json`, and
there is nothing in `metrics.values` to plot. A figure of the failure would be a
figure of the absence of an endpoint, which is a sentence, not a chart.

## 4. Interpretation

**For C-005: nothing.** The claim stays `unsupported` with the same evidence it had
before — none. The pre-registered `PROTOCOL.md` named this exact outcome in advance
under "Two ways this experiment can produce a number that is not evidence", case 1,
and it is the reason that section was written before the run rather than after.

**For the record itself: this was the more useful failure to hit first.** The
structure was exercised end to end — `make new-experiment` scaffolded it, the
protocol was pre-registered and committed before any run, write-time capture
populated the manifest and `data/`, the validator accepted a `failed` folder with
empty metrics, and `INDEX.md` regenerated. Acceptance criterion #7 asked for one
experiment recorded end to end; this is one, along the path that records most often
get wrong.

**One finding worth keeping** — not about C-005, but about the system: the two arms
degrade *differently* when the LLM is absent. `planner_agent.next_beat` catches
`APIError` and falls back to a heuristic, so the turn completes with a narrator beat.
`director_agent.who_is_up` does not, so the turn raises. Both are documented as
"best-effort; never raises". One of them is not. That is a real inconsistency in the
turn path, discovered incidentally, and it is now in `../../OPEN_QUESTIONS.md`.

## 5. Threats to validity

Listed even though there is no result to threaten, because these apply to the *next*
run of this protocol and would otherwise be rediscovered:

- **Under-powering.** 3 turns × 3 seeds on one world is far below the audit's §7
  minimum of 3 private worlds × 25 scenes × 3 seeds. Even a clean separation here
  could move `C-005` no further than `partial`.
- **Contaminated world.** Embergate ships with this repository. `../../DECISIONS.md`
  D-006 restricts committed worlds to structural experiments; **no number from this
  protocol is paper-eligible** until it runs on fresh private worlds.
- **Non-production environment.** In-memory SQLite, `NEO4J_URI=""`, `QDRANT_URL=""`.
  Graph relationship context and retrieved lore are absent from both arms equally, so
  the comparison stays internally valid, but absolute values would not transfer to a
  production run.
- **Survivorship bias in aggregation.** Realised, not hypothetical — §2. Any future
  run with excluded seeds must report the reduced `n` per cell, not a mean over
  whatever survived.
- **Single model family.** When this does run, it will run against one local model,
  and the result will not generalise across providers.

## 6. What surprised us

That the run **exited successfully the first time.** 18 turns, no crash, a populated
`metrics.json`, a plausible mean with a tight standard deviation. Nothing in the exit
code said "this measured nothing." Had the aggregate been copied into a summary — or
into a chat message — it would have read as a finding.

The protocol caught it, not the tooling. That is backwards from how it should work,
and it is why the runner now refuses to aggregate over a partial run: the record
should not depend on someone remembering to be suspicious of a clean number.

## 7. Follow-ups

- [ ] Re-run this protocol once an OpenAI-compatible endpoint is configured. The
      harness is built and pre-registered; this is a re-run, not a rebuild.
- [ ] Reconcile the degradation mismatch: `director_agent.who_is_up` raises where
      `planner_agent.next_beat` falls back, though both are documented as never
      raising.
- [ ] Have the runner assert LLM reachability **before** the first turn and refuse to
      start, rather than producing 18 rows that have to be interpreted afterwards.
- [ ] Decide whether a zero-LLM-call run should be a hard validator error. Arguably
      any experiment whose manifest claims an `llm` block but records 0 calls is
      structurally suspect.

## 8. Reproduction

```bash
uv run python -m utils.scripts.research.run_scene \
    --arm both --seeds 0,1,2 \
    --experiment docs/research/experiments/EXP-2026-08-001-planner-vs-oneshot-director
make validate-research && make research-index
```

Reproduces the failure exactly on a machine with no model endpoint configured. On a
machine with one, it runs the actual experiment — and this file must then be replaced
by a new experiment folder, not edited. A completed experiment is immutable.
