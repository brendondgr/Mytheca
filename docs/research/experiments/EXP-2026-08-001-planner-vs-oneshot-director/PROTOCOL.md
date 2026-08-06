# PROTOCOL — EXP-2026-08-001 ReAct per-beat planner vs. the one-shot speaker-set director

> Pre-registered. Written and committed **before** any run — commit
> `[Research Record] (5/7)`. Nothing below was adjusted after seeing a result; any
> change after the first run is recorded as an amendment at the bottom of this file.

## Question

Does the ReAct per-beat planner (`planner_agent.next_beat`) produce different — and
better — multi-party turn structure than the one-shot speaker-set decision it
replaced (`director_agent.who_is_up`)?

This is claim **C-005**. It is the cheapest real experiment available in this
repository, because both arms already exist, both are already tested, and neither has
ever been compared against the other. The one-shot design is not a strawman written
for the occasion: it is the design that actually shipped first and was deliberately
replaced, with no measurement taken either way.

## Hypothesis

The per-beat planner produces **more beats per turn** and **more distinct speakers per
turn** than the one-shot director, because it re-decides after every beat and is
unbounded, whereas the one-shot director commits to a speaker set up front and is
capped at three (`director_agent._MAX_SPEAKERS = 3`).

On **addressed-character response rate** we predict **no difference**, because both
arms short-circuit a directed address: the director has an explicit `addressed` fast
path, and the planner is instructed to honour an explicit target. A null result on
that metric is expected and is not a failure of the experiment.

## Setup

One process, one in-memory database, both arms driven through the identical shipped
turn loop.

- **Arm A — `planner`** — the shipped loop, unmodified.
- **Arm B — `director`** — `planner_agent.next_beat` is substituted at runtime by a
  shim (`utils/scripts/research/run_scene.py::_director_arm`) that calls
  `director_agent.who_is_up` **once** per turn and replays its ordered speaker list
  one beat at a time, then ends the turn.

**No file under `web/backend/app/` is modified by this experiment.** Everything
downstream of beat selection — emission parsing, the validator, the presence fold, the
consistency guard, the narrator, stat clamping — is identical between arms. The
measured difference is therefore attributable to beat-selection policy and nothing
else. This is the one confound the audit's §6.4 #6 warns is usually uncontrolled.

## Data

The shipped **Embergate** seed world (`web/backend/app/core/seed.py`), first scenario.

⚠️ **Embergate is committed to this repository and is therefore contaminated for any
held-out use.** `../../DECISIONS.md` D-006 restricts committed worlds to tooling
shakedowns and structural experiments; this is one. **No number produced here is
paper-eligible.** A paper-eligible run of the same protocol requires fresh private
worlds per `../../paper/checklists/minimum-viable-contribution.md`.

Three scripted player turns, identical across arms, chosen to exercise the structural
properties under test:

1. An open address to the whole group — where an unbounded planner and a 3-capped
   director should diverge most.
2. A directed question to a named character (`wren`) — the addressed-response path.
3. An open follow-up a bystander could plausibly hijack.

## Metrics

Countable from the emitted event stream plus the request. **No LLM judges anything**
(`../../DECISIONS.md` D-003), and no human rates anything — these are structural
counts, which is the whole reason this experiment is cheap.

| Metric | Definition | Direction |
| --- | --- | --- |
| `beats` (**primary**) | Distinct story events emitted per turn, counting `character_dialogue`, `character_action` and `narration`. Delta frames re-emit the same `(id, seq)` and are counted once. | Higher = a longer exchange. Not inherently better; interpreted against cost |
| `character_beats` | The subset of `beats` voiced by a cast member | Higher = more cast participation |
| `distinct_speakers` | Unique `characterId` values in a turn | Higher = broader participation, which is what the 3-cap limits |
| `addressed_responded` | On a directed turn, did the addressed character speak at all? 1/0 | Higher = better. **Predicted equal across arms** |
| `bystander_first` | On a directed turn, did an unaddressed character take the *first* beat? 1/0 | **Lower** = better |
| `wall_clock_seconds` | Per turn | Lower = cheaper. A structural win at 5× cost is a different finding |

Aggregated as mean ± population std across seeds. `std` is omitted, not reported as
0.0, when n=1 — 0.0 would read as "no variance observed" when the truth is "variance
not measurable".

## Baselines

Arm B **is** the baseline: `director_agent.who_is_up`, at
`web/backend/app/agents/director_agent.py:46`, with `_MAX_SPEAKERS = 3`. It is dead on
the production turn path and called only from
`utils/tests/backend/agents/test_director_agent.py`.

**Do not delete this dead code while this experiment is open** — a note to that effect
is in `../../OPEN_QUESTIONS.md`.

## Procedure

```bash
# Smoke test — wires up the harness without spending a run
uv run python -m utils.scripts.research.run_scene --smoke --arm planner

# The experiment
uv run python -m utils.scripts.research.run_scene \
    --arm both --seeds 0,1,2 \
    --experiment docs/research/experiments/EXP-2026-08-001-planner-vs-oneshot-director

make validate-research && make research-index
```

**Environment.** In-memory SQLite with `NEO4J_URI=""`, `QDRANT_URL=""`,
`EMBED_PROVIDER=hash` — mirroring the test harness, not production. Neo4j and Qdrant
degrade to no-ops by design, so the turn loop runs unchanged, but graph relationship
context and retrieved lore are absent from both arms equally. Recorded in the
manifest's `environment` block.

**Prerequisite.** An OpenAI-compatible model endpoint must be configured and
reachable. Every agent in this loop is best-effort: with no endpoint, `resolve_llm`
raises and `planner_agent.next_beat` silently falls back to `_fallback_beat`, a
non-LLM heuristic. **A run in that state measures the fallback path, not the
planner** — it would produce numbers that look valid and mean nothing about C-005.
See "What would falsify this".

## What would falsify this

The hypothesis is falsified if `beats` and `distinct_speakers` are statistically
indistinguishable between arms across seeds. That would mean the per-beat planner's
extra LLM calls buy no structural difference — which, given that the planner replaced
the director on the assumption that it does, is a result worth having.

**A null result here is publishable.** EXAG explicitly solicits "reports on failed
experiments… with insight into what went wrong" (`../../paper/venue-targets.md`).

**Two ways this experiment can produce a number that is not evidence**, both of which
must be checked before any result is interpreted:

1. **No LLM endpoint.** Both arms fall back to non-LLM heuristics and converge
   trivially. The turn loop still completes and still emits beats, so the run looks
   successful. **This does not falsify the hypothesis — it fails to test it.** The
   correct record in that case is `status: failed`, not a null result.
2. **Under-powering.** Three turns on one committed world at three seeds is far below
   the audit's §7 minimum of 3 private worlds × 25 scenes × 3 seeds. Even a clean
   separation here is preliminary, and `C-005` cannot move past `partial`.

## Amendments

None.
