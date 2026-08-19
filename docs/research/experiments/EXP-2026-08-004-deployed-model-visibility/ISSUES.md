# ISSUES — EXP-2026-08-004

## 2026-08-19 — One exploratory call preceded the pre-registration

**Impact:** none on the recorded numbers.
**Cause:** a single streamed call to `skynet` was timed while diagnosing why the reasoning
disclosure never appeared in the browser (first answer 11.73 s of an 11.89 s total, no
reasoning channel). That observation is what prompted this experiment, and it happened
before PROTOCOL.md was written.
**Resolution:** none — accepted and disclosed. It is stated as the hypothesis's source in
PROTOCOL.md rather than folded in as a result.
**Paper implication:** none, provided the exploratory number is not reported. It is not.

## 2026-08-19 — `blocking-uncapped` is dominated by one outlier

**Impact:** its aggregate (19.84 ± 19.35 s) is not a usable central estimate.
**Cause:** run 1 took 47.2 s against 6.17 s and 6.14 s for runs 2 and 3 — consistent with a
cold route or a queued upstream on the first call of the session.
**Resolution:** none. The aggregate is reported (no run failed, so the contract permits it)
but RESULTS.md states explicitly that no tail claim is drawn from it.
**Paper implication:** do not cite `blocking-uncapped` wall clock from this experiment.

## 2026-08-19 — Arm order confound, inherited

**Impact:** as EXP-2026-08-003 — cross-arm comparisons are confounded with run order.
**Cause:** the same runner, unchanged, executes arms in a fixed order.
**Resolution:** none — inherited and disclosed. The finding here (`first_reasoning_s` null
in every run) does not depend on arm ordering at all.
**Paper implication:** same as EXP-2026-08-003.

## 2026-08-19 — The routed upstream can change between calls

**Impact:** runs are not guaranteed to hit the same model.
**Cause:** `skynet` declares `upstream_model: auto`. Observed upstream during this run was
`qwen38-27B-awq`, but the relay may route elsewhere.
**Resolution:** none — this IS the deployed condition and is what the experiment set out to
characterise. Recorded in the manifest's `nondeterminism_note`.
**Paper implication:** results describe "the deployed skynet route on 2026-08-19", not a
named model.
