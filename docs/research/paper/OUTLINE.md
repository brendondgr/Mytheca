# Paper Outline — P1

> **Does multi-agent scaffolding preserve character voice? A controlled study in
> multi-party LLM narrative.**

Chosen over P2/P3/P4 in `../DECISIONS.md` D-002. Source: `../mytheca-research-audit.md` §7.

**The framing shift this outline encodes:** the engine is not the contribution. The
engine is the instrument. Audit §5.3 puts the reason bluntly — asked "what did you
learn that we did not already know?", the honest answer today is "that this
architecture can be built by one person," which is a statement about the developer,
not about the world.

---

## Research question

In a live multi-character narrative scene, does per-speaker prompt isolation plus
per-beat planning preserve measurably greater voice distinctness than a single prompt
rendering all speakers — and which scaffold components account for the difference?

## Why this question

It is live in the literature and unanswered for the multi-character narrative setting:

- **Echoing** (arXiv:2511.09710) finds up to 70% role abandonment in agent-to-agent
  conversation, with 93% of those conversations completing "successfully" — task
  metrics are blind to it.
- **Wang et al.** (ACL 2024) find a single agent with a strong prompt rivals
  multi-agent discussion, for reasoning.
- **Cross-component interference** (arXiv:2605.05716) finds the best proper subset
  beat a five-component system in every setting, Planning carrying a negative
  Shapley value.
- **SocialBench** finds individual persona competence does not transfer to the group.

Nobody has tested it where several LLM-driven characters share a scene with a human
in the loop. Mytheca is unusually well-instrumented to answer it.

## What carries over

Essentially the whole engine: turn loop, character agent, planner, emission parser,
`session_export.py` — and critically, the superseded one-shot director
(`director_agent.who_is_up`) as a **free second baseline arm**, already implemented
and already tested.

## What must be built

| # | Work item | Effort | Risk |
| --- | --- | --- | --- |
| W3 | Headless scenario runner + deterministic replay + a fixed private eval world (not committed) | 1.5 wk | Low — `session_export.py` gives the record format free |
| W4 | Single-prompt multi-speaker baseline arm | 1 wk | Low |
| W5 | One-shot director restored as a second baseline arm | 0.3 wk | Very low — code exists and is tested |
| W6 | Voice-distinctness metric: blinded human attribution + stylometric classifier + Coverage/Uniformity/Complexity | 1.5 wk | **Medium — metric validity is the hard part** |
| W8 | Component ablations behind flags | 2 wk | Medium — large confound surface |

**Critical path to a minimum credible result:** W2 → W3 → W6 → W4 → W7 → W12 → W13 =
7.5 weeks sequential, **8–11 weeks** allowing for metric-design uncertainty. The full
P1 study including parallel ablations W8–W10 is **10–14 weeks**.

## Evaluation design

**Datasets.** 3 held-out worlds generated fresh and **kept private** (D-006), each
4–6 characters, ~25 scenes of ≥15 beats, 3 seeds.

**Arms.** (a) single prompt rendering all speakers · (b) one-shot director + 3-speaker
cap · (c) the full loop.

**Metrics.**
- *Primary* — blinded human speaker-attribution accuracy on label-stripped
  transcripts, ≥2 raters, Krippendorff's α reported.
- *Secondary* — held-out stylometric classifier attribution accuracy.
- *Tertiary* — population-level Coverage/Uniformity/Complexity (arXiv:2604.24698).
- *Cost* — tokens and wall-clock per turn per arm. **A quality win at 5× cost is a
  different paper than a quality win at parity.**

**Explicitly not used:** LLM-as-judge for any primary metric (D-003); famous
fictional characters (D-004); a single unblinded rater.

**Ablations.** think→speak off · stats off · consistency guard off · reflection off
(`TURN_REFLECTION_ENABLED=false`, already a flag) · gate never/always. Per-component
attribution in the spirit of arXiv:2605.05716.

**Statistics.** ≥3 seeds per condition; confidence intervals; explicit statement of
model, version and sampling parameters. Chance-corrected inter-rater agreement.

## Positioning

A related-work section engaging IBSEN, MAGNET/ATLAS, PANGeA, Open-Theatre, Wu et al.
(ACL 2025), Drama Machine, Echoing, SocialBench and Wang et al. (ACL 2024) — **with
an explicit statement of the delta.** See `../RELATED_WORK.md`. Positioning scored 0
in the audit's readiness scorecard; W12 is 1.5 weeks and lifts it to 3.

## Limitations (state plainly)

Single developer · one model family · synthetic worlds · no long-session (>1 hour)
data · **and that the architecture is substantially anticipated by IBSEN and MAGNET.**

## Risk

The metric may not be sensitive enough to separate the arms, making this a
methods-negative result — **still submittable to EXAG, which invites exactly that.**
Secondary risk: the result is null and the architecture is not earning its cost.
That is information worth far more than the months it saves.

---

## Fallbacks

**If P1's first week produces a null result → switch to P4** (*Human evaluation in
LLM interactive narrative is underpowered: a methodological audit*). 6–9 weeks,
unclaimed, and the null result is itself evidence. The evidence base is already
visible: verified sample sizes across the recent corpus are n=12, n=12, n=15, and
5 prompts.

**P2** (a trajectory-level evaluation environment) is the highest-ceiling path and
fits the renamed NeurIPS Evaluations & Datasets track, but demands sustained
maintenance and adoption. **P3** (POV switching) has the cleanest novelty — it is the
one genuinely unclaimed idea here — but is gated on human-subjects work. It is the
right *second* paper, after P1 establishes the instrument is sound.
