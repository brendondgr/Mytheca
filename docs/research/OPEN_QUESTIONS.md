# Open Questions

Unresolved threads, known weaknesses, and reviewer-bait. This becomes the paper's
future-work section and pre-empts objections that would otherwise arrive in review.

Two sources feed this file: **field-level gaps** (audit §4 — things nobody has
answered) and **project-level weaknesses** (audit §6.4 — things wrong with this
repository specifically). Every follow-up from every `RESULTS.md` §7 is appended here
in the same change that writes it.

---

## Field-level gaps (audit §4)

These are open in the literature, not just in Mytheca. Each names whether this
project is positioned to close it.

### G1 — Cast-level voice distinctness in live multi-character narrative is unmeasured
Persona-drift work is either agent-to-agent *task* dialogue (Echoing, arXiv:2511.09710)
or isolated per-character benchmarks. SocialBench (arXiv:2403.13679) measures group
*sociality*, not voice separation in a played scene. Persona Collapse
(arXiv:2604.24698) proposes population-level Coverage/Uniformity/Complexity metrics
but not in a narrative-play setting.
**Why it stayed open:** needs long multi-party generation logs plus a blinded
attribution protocol, and no engine was instrumented to emit them.
**Mytheca:** *incidentally positioned.* `session_export.py` already dumps exactly the
needed record — full transcript, private thinking, graph writes, RAG activity.
Nothing measures it. → `C-001`

### G2 — No ablation isolating multi-agent scaffolding vs. a single strong prompt, in the narrative setting
Wang et al. (ACL 2024) establish the result for *reasoning*, not narrative. MAST
(arXiv:2503.13657) shows specification failures dominate. Cross-component
interference (arXiv:2605.05716) found the best proper subset matched or beat a
five-component system in every setting tested, with Planning carrying a **negative**
Shapley value.
**Why it stayed open:** requires building both arms in one comparable system, and
almost nobody keeps the superseded arm.
**Mytheca:** *incidentally, and uniquely well positioned* — it still contains both
arms, both tested, never compared. → `C-005`, EXP-2026-08-001

### G3 — Interior monologue is evaluated for quality, never for causal influence on the next line
Turpin et al. (NeurIPS 2023) and Lanham et al. (arXiv:2307.13702) establish CoT
unfaithfulness generally; Mannekote et al. (arXiv:2507.02197) find belief–behavior
inconsistency; Drama Machine ran an Ego/Superego ablation but on 2 scenarios.
**Why it stayed open:** needs a perturbation harness over a generation pipeline, not
a static benchmark.
**Mytheca:** *not addressed at all* — and it **displays** the thinking to the player
as a first-class UI element, which raises rather than lowers the stakes on whether
it is faithful. → `C-002`

### G4 — POV switching as an interaction technique is unstudied
No verified paper found. Wu et al. (ACL 2025) premise the user *as* a character but
do not study switching. Elsewise (arXiv:2601.15295) frames the authorial-intent gap
but not POV.
**Why it stayed open:** genuinely under-explored; needs a working system with the
mechanism plus an HCI-style study, and such systems are rare.
**Mytheca:** *directly positioned, and this is the strongest unclaimed surface.* POV
is implemented end to end in `turn_engine`. Gated on human-subjects work.

### G5 — Retrieval gating is studied for QA cost/quality, never for narrative grounding
Self-Route (EMNLP 2024) and AdaRankLLM (arXiv:2604.15621) study QA. ConvoMem
(arXiv:2511.10523) argues the small-corpus regime "deserves dedicated research
attention rather than simply applying general RAG solutions."
**Why it stayed open:** narrative grounding has no accepted metric — the same
evaluation problem that blocks the whole area.
**Mytheca:** *partially* — the gate exists and is **model-free**, making it an
unusually clean object of study. Nothing measures it. → `C-004`

### G6 — Story graphs lack valid-time, and nobody has quantified what that costs a narrative system
Zep (arXiv:2501.13956) and AriGraph (arXiv:2407.04363) add temporality and show it
helps in general agent memory; NWM (arXiv:2607.05577) shows narratological typing
helps. Neither isolates the temporal dimension in interactive play.
**Why it stayed open:** requires long played sessions with continuity ground truth.
**Mytheca:** *not addressed.* `graph_writer.upsert_node` uses `SET n += $metadata` —
it overwrites, so "what was true at turn N" is unanswerable.

### G7 — Human evaluation in interactive narrative is systematically underpowered, and no position paper says so
Verified sample sizes across the recent corpus: n=12, n=12, n=15, 5 prompts. The
audit's literature search found no paper making this argument.
**Why it stayed open:** unglamorous, and criticising methodology in a small field is
socially costly.
**Mytheca:** *not addressed* — but it is a cheap, real, unclaimed contribution for
someone with a system that can generate the material. See `paper/OUTLINE.md` P4.

### G8 — No open, runnable environment for evaluating multi-character interactive narrative agents
TALES covers single-agent text games; SOTOPIA covers dyadic/small-group social goals;
Open-Theatre is a toolkit, not a benchmark. NARRA-Gym (arXiv:2605.08503) asserts
existing evaluations "focus on static prompts, isolated story generations, or post-hoc
ratings."
**Why it stayed open:** requires a full engine *plus* an evaluation design — two
different skill sets.
**Mytheca:** *incidentally* — roughly 80% of the engine, 0% of the evaluation design,
**and no license**.

---

## Project-level weaknesses (audit §6.4)

Six of eight hard disqualifiers are present. Five are *absences*, fixable by doing
work; one is not.

| # | Weakness | State | Fixable by working harder? |
| --- | --- | --- | --- |
| 1 | No falsifiable claim is *constructed* | The seven claims exist now in `CLAIMS.md`, so this is closing | Yes — days |
| 2 | No baseline of any kind | One non-strawman baseline already implemented and tested (one-shot director); a second (single-prompt multi-speaker) is small work | Yes |
| 3 | **Scooped on multiple claims** | C-003 by PANGeA and MAGNET/ATLAS; C-002 by Drama Machine; the architecture itself by IBSEN | **No.** Only fixable by changing which claim is made |
| 4 | Evaluation data cannot be shared | There is no evaluation data; worlds are original, so a releasable corpus is straightforward — but **there is no LICENSE file**, which blocks releasing anything | Yes — W1 is a 5-minute fix |
| 6 | No ablation separating mechanism from confounds | Structurally severe: model choice, per-agent reasoning effort, three sampler overrides, `context_beats` (5–100), `turn_max_beats`, `TURN_REFLECTION_ENABLED`, `TURN_ASYNC_FINALIZE`, prompt overrides at three levels, the retrieval gate | Yes, but per-component attribution is **mandatory**, not optional |
| 7 | Human eval with a single unblinded rater | Prospective — the default path for a solo developer is exactly the disqualified design. Any eval needs ≥2 raters, blinding, and chance-corrected agreement. Norman et al. (arXiv:2606.19544): raw agreement overstates chance-corrected by 33–41 points | Yes, by designing it right from the start |

**Absent (and worth protecting):** #5 test-data contamination. Characters and worlds
are user-authored originals, not famous fictional figures, so the memorisation
pathway that Peng & Chen (SIGDIAL 2026, arXiv:2603.03915) show inflates published
role-play scores does not apply. **This is Mytheca's single strongest methodological
asset.** Two things could destroy it: committing a fixed evaluation world to a public
repo, and reporting absolute rather than relative scores (genre conventions —
maritime intrigue, guilds, a drowned harbour — are heavily represented in training
data even when the specific characters are not). See `DECISIONS.md` D-006.

---

## Standing follow-ups

- [ ] **Read the 2025 Wordplay accepted-paper list.** ~30 papers on exactly this
  topic, published nine months before the audit, individual PDFs never read. The
  audit names this as **the most likely place for a scoop it missed**, and the POV
  and stat-arbitration novelty claims rest on absence of evidence.
  https://wordplay-workshop.github.io/modern/#accepted_papers
- [ ] **Add a LICENSE.** 0.1 weeks, blocks every artifact track, and the repository
  is all-rights-reserved by default until it exists.
- [ ] **Write POV switching and stat-arbitrated turn behavior as falsifiable claims**
  so they can enter `CLAIMS.md`. They are the only defensible novelty surface and
  neither is currently stated as a proposition.
- [ ] **Confirm the route to ethics review.** Any human study (G4, G7) needs it; the
  owner's institutional affiliation was not determinable from the repository.
- [ ] **Decide the fate of `director_agent.who_is_up` / `rerank`.** Dead on the turn
  path, called only from tests, with prompt keys still editable in Options → Prompts
  where they silently do nothing. **Do not delete them until EXP-2026-08-001 is
  finished** — they are the baseline arm.
- [ ] **Log the consistency guard's firing rate.** C-006 cannot be evaluated while
  the guard's best-effort design means failures pass silently and unmeasured.
- [ ] **Verify whether the GitHub remote is public.** Determines forward
  contamination risk for any world committed to the repository.

## Follow-ups from experiments

Appended as each `RESULTS.md` §7 is written.

### From EXP-2026-08-001 (`failed` — no LLM endpoint reachable)

- [ ] **Re-run the C-005 protocol once a model endpoint is configured.** The harness
      is built and the protocol is pre-registered; this is a re-run, not a rebuild.
      → `experiments/EXP-2026-08-001-planner-vs-oneshot-director/PROTOCOL.md`
- [ ] **Reconcile the degradation mismatch on the turn path.**
      `planner_agent.next_beat` catches `APIError` and falls back to a heuristic;
      `director_agent.who_is_up` propagates it. Both docstrings promise "best-effort;
      never raises". One of them does raise. Found incidentally, not by a test.
- [ ] **Make the runner assert LLM reachability before the first turn** and refuse to
      start, rather than emitting rows that have to be interpreted afterwards.
- [ ] **Decide whether a zero-LLM-call run should be a hard validator error.** An
      experiment whose manifest carries an `llm` block but records 0 calls is
      structurally suspect, and the current validator accepts it.
