# Checklist — Minimum Viable Contribution

The smallest complete package that would constitute a credible submission. **A live
to-do, not a description.** Source: `../../mytheca-research-audit.md` §7.

Roughly 10–14 weeks. Would be a credible **EXAG** or **ICIDS** submission, and a
plausible **AIIDE** or Wordplay-successor submission if the human study is added.

## Claim

- [ ] "In multi-character LLM narrative scenes of ≥15 beats with ≥3 characters,
      per-speaker prompt isolation with per-beat planning yields higher blinded
      speaker-attribution accuracy than a single prompt rendering all speakers, at
      comparable narrative quality."

## Data

- [ ] 3 fresh, private, user-authored worlds (4–6 characters each)
- [ ] 25 scenes each, ≥15 beats per scene, 3 seeds → **225 transcripts per arm**
- [ ] **Never committed to the public repository** — contamination hygiene, `../../DECISIONS.md` D-006

## Arms

- [ ] Full loop
- [ ] Single prompt rendering all speakers
- [ ] The existing one-shot director with the 3-speaker cap

## Metrics

- [ ] **Primary** — blinded human speaker-attribution accuracy on label-stripped
      transcripts, ≥2 raters, **Krippendorff's α reported**
- [ ] **Secondary** — held-out stylometric classifier attribution accuracy (cheap,
      scalable, no judge-validity problem)
- [ ] **Tertiary** — Coverage / Uniformity / Complexity (arXiv:2604.24698) for
      population-level collapse

## Ablations — minimum two, isolating the claimed mechanism

- [ ] Think→speak removed
- [ ] Consistency guard removed
- [ ] *Ideally also:* stats removed
- [ ] *Ideally also:* reflection removed (`TURN_REFLECTION_ENABLED=false` — already a flag)

## Cost reporting

- [ ] LLM calls, prompt tokens and wall-clock per turn per arm.
      **A quality win at 5× cost is a different paper than a quality win at parity.**

## Statistics

- [ ] ≥3 seeds per condition
- [ ] Confidence intervals
- [ ] Explicit statement of the model, version and sampling parameters used

## Explicitly NOT used

- [ ] No LLM-as-judge for the primary metric — PersonaEval, arXiv:2508.10014
- [ ] No famous fictional characters — arXiv:2603.03915
- [ ] No single unblinded rater

## Positioning

- [ ] A related-work section engaging IBSEN, MAGNET/ATLAS, PANGeA, Open-Theatre,
      Wu et al. (ACL 2025), Drama Machine, Echoing, SocialBench and Wang et al.
      (ACL 2024) — **with an explicit statement of the delta**

## Artifact

- [ ] LICENSE added
- [ ] Headless runner released
- [ ] Transcripts released
- [ ] Model and version pinned in the paper

## Limitations — state plainly

- [ ] Single developer
- [ ] One model family
- [ ] Synthetic worlds
- [ ] No long-session (>1 hour) data
- [ ] **That the architecture is substantially anticipated by IBSEN and MAGNET**
