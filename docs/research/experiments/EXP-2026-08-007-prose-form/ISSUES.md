# ISSUES — EXP-2026-08-007 Prose form

## A pilot was run before the protocol was written

Three samples per arm, two arms (`shipped` and `off`), one scene prompt, run directly
against the relay before `PROTOCOL.md` existed. It is what motivated this experiment and
it is disclosed here because the contract requires it: pre-registration after seeing
results is not pre-registration.

The pilot's numbers are **not** carried into `manifest.yaml`, `data/metrics.json` or
`RESULTS.md`, and the recorded run repeats the measurement from scratch with a written
protocol, three arms, five prompts and n = 10 per arm. The pilot is why the hypothesis is
stated in a direction rather than as "exploratory" — treat the recorded run as a
confirmation of a pre-existing suspicion, not as an independent discovery of it.

For the record, the pilot observed (n = 3 per arm, one prompt, **not** to be quoted as a
result): the `shipped` arm produced passages of 1295/780/331 characters with 2/5/5
sentence terminators and 0/6/3 quote characters; the `off` arm produced 403/521/446
characters with 8/10/10 terminators and 4/6/4 quote characters.

## Known limitations of the recorded run

- One model only (`skynet`, upstream `qwen38-27B-awq`). Nothing here transfers to another
  model without re-running.
- The five scene prompts ship in `utils/scripts/research/run_prose_form.py` and are
  therefore contaminated for any held-out use.
- No significance test. See `PROTOCOL.md` § Analysis for why, and read the standard
  deviations rather than the means alone.

## Incidental observation: `thinking_token_budget` is a hint, not a hard stop

Not a metric of this experiment and not in `manifest.yaml` — recorded here because it was
measured during the same session and a number that is stated anywhere has to be traceable.

Two direct probes against the same endpoint, with `thinking_token_budget: 1024` and the
shipped character contract, returned **4,193** and **3,121** characters of reasoning
(`max_tokens` 3072 and 8192 respectively). Reasoning therefore hovers around the requested
budget and can pass it. n = 2, one prompt, no arms — an observation, not a finding.

It matters because thinking and answer share one `max_tokens`: an overshooting scratchpad
eats the room the passage needs, and a beat in the live verification run came back as
reasoning with no prose for exactly that reason. `character_turn_agent._SCRATCHPAD_HEADROOM`
pays for twice the budget as a result. Establishing the actual distribution would need its
own experiment.
