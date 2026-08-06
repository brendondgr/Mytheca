# Claims Ledger

Every claim the paper will make, and the evidence that supports it.

Status: `unsupported` | `partial` | `supported` | `refuted` | `cut`

**Every claim below is `unsupported`.** That is not a placeholder state — it is the
accurate state of this project as of 2026-08-06. Mytheca has no evaluation of any
kind: no benchmark, no baseline, no ablation, no metric, no human study. Each claim
is asserted somewhere in the codebase (usually a docstring) as the justification for
a mechanism, and none has ever been tested.

This table is therefore the experiment backlog. It is meant to look uncomfortable.

**Source.** Transcribed from `mytheca-research-audit.md` §1.6, which derived these
from what the code does and what its docstrings assert — not from README marketing.
Each is stated as a falsifiable proposition of the form *doing X yields Y over Z
under conditions W*. IDs were renumbered `C1`→`C-001` for the contract's format; the
audit's original label is kept in Notes so §1.6 stays greppable.

| ID | Claim | Evidence | Artifact | Status | Notes |
|----|-------|----------|----------|--------|-------|
| C-001 | Voicing each character with an isolated per-speaker LLM call, rather than one prompt rendering all speakers, preserves greater voice distinctness across a multi-turn multi-party scene. | — | — | **unsupported** | Audit C1. **The architecture's load-bearing justification**, asserted verbatim in `character_turn_agent.py` ("so voices stay distinct"). Zero evidence. To establish: blinded human speaker-attribution accuracy on label-stripped transcripts, and/or Coverage/Uniformity/Complexity (arXiv:2604.24698), on matched scenes from (a) the full loop and (b) a single-prompt baseline, ≥20 scenes × ≥3 seeds. |
| C-002 | Requiring a visible in-voice `<thinking>` deliberation before speech produces more in-character spoken lines than speaking directly. | — | — | **unsupported** | Audit C2. Asserted in `character_turn_agent.py`; `TURN_EFFORT = MEDIUM` is set specifically for it. **Already ablated by someone else** — Drama Machine (arXiv:2408.01725) ran the Ego/Superego ablation, on 2 scenarios. To establish: Lanham-style faithfulness perturbation (arXiv:2307.13702) — corrupt the `<thinking>` block, measure whether the spoken line changes — plus an A/B with the block removed. |
| C-003 | Server-side clamping of LLM-proposed numeric stat changes against a declared per-world schema, with Markdown band guidance rendered into the prompt, yields better long-run character-state continuity than letting state live in free text. | — | — | **unsupported** | Audit C3. Mechanism evidence only: `validator.validate_stat` provably cannot emit an out-of-range or undefined stat (`test_validator.py`). Nothing measures continuity. ⚠️ **Scooped** — PANGeA (AIIDE 2024) reports 28%→98% narrative alignment for the comparable mechanism; MAGNET/ATLAS (arXiv:2607.00918) reports −50% hallucinations. To establish: continuity-error rate on long sessions against the ConStory-Bench taxonomy (arXiv:2603.05890). |
| C-004 | A model-free, conservative, skip-by-default retrieval gate loses no grounding quality relative to always-retrieve, while saving retrieval cost. | — | — | **unsupported** | Audit C4. Asserted in `retrieval_gate.py` ("a bad retrieval is worse than none"). To establish: three-arm comparison (never / gated / always) on turns with a known lore-grounded answer, reporting quality *and* tokens. The gate's trigger conditions are enumerable, so a targeted adversarial set is cheap. |
| C-005 | A ReAct per-beat planner produces better multi-party turn structure than a one-shot speaker-set decision. | [EXP-2026-08-001](experiments/EXP-2026-08-001-planner-vs-oneshot-director/) *(pre-registered `planned`; evidence pending, not obtained)* | — | **unsupported** | Audit C5. **Unusually strong provenance evidence:** the one-shot design was built, then explicitly replaced, and *both implementations are still in the repository and tested* (`director_agent.who_is_up` vs `planner_agent.next_beat`). Never compared. **The cheapest ablation available** — the baseline arm already exists. Related transferable evidence: Zhu et al. (arXiv:2505.22809) report removing the ReAct step cost >70% F1 in a closely related setting. |
| C-006 | A pre-emit single-line consistency check with one-shot regeneration reduces within-turn contradictions at acceptable latency, without breaking delta streaming. | — | — | **unsupported** | Audit C6. Mechanism only. Best-effort design means it silently passes on any failure, so **its true firing rate is not even logged as a metric**. To establish: contradiction rate guard-on vs. guard-off on scenes seeded with contradiction opportunities; guard precision/recall against human labels; added latency per turn. |
| C-007 | Carrying a per-character disposition across turns via an off-hot-path reflection step improves stance continuity relative to reconstructing stance from the transcript alone. | — | — | **unsupported** | Audit C7. Inherited from Generative Agents (UIST 2023), whose own contribution has never been cleanly ablated in downstream systems. To establish: A/B with `TURN_REFLECTION_ENABLED=false` — **the ablation arm is already a config change** — scored on stance-continuity across a scene boundary. |

## The meta-claim

C-001, C-002, C-005 and C-007 are all instances of one proposition: **the multi-agent
scaffolding earns its cost.** That meta-claim is under active attack in the literature
from three independent directions — Wang et al. (ACL 2024, arXiv:2402.18272: a single
agent with a strong prompt rivals multi-agent discussion), the MAST taxonomy
(NeurIPS 2025 D&B, arXiv:2503.13657), and cross-component interference
(arXiv:2605.05716, where the best proper *subset* matched or beat a five-component
system in every setting tested, with Planning carrying a **negative** Shapley value).

It is the single most testable and most interesting thing about this repository, and
it is untested. See `paper/OUTLINE.md`.

## What is defensibly novel

Of everything Mytheca does, a good-faith search across three research areas found a
2023–2026 primary source for **eight** components. **Two** could not be located in
any verified paper (audit §3):

- **POV switching** — the player speaks *as* a cast member, the AI is locked out of
  that character, and branch proposals become first-person in-voice line suggestions.
- **Stat-arbitrated turn behavior** — numeric bounded state rendered as prose bands
  that condition generation and are updated via clamped model proposals.

Neither is currently framed as a claim, isolated, or measured. Neither appears in the
table above, because a claim has to be *stated* before it can be listed — writing
them is open work (`OPEN_QUESTIONS.md`). ⚠️ Both rest on *not finding* prior work,
which is weaker than finding it, and the audit flags the 2025 Wordplay accepted-paper
list as the most likely place for a missed scoop.

## Refuted / cut claims

None yet. When one lands here, it stays — that is what stops a settled question from
being re-litigated.
