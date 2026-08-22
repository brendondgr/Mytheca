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

### From EXP-2026-08-002 (`complete` — in-narrative moment prompts)

- [ ] **Run the ablation arm** (moment prompt with `strip_names` and the no-names
      instruction removed) so `name_leak = 0` can be *attributed* to the design rather
      than merely observed. As it stands the metric is measured after the guard runs and
      cannot distinguish a model that never named anyone from a guard that cleaned up.
      → `experiments/EXP-2026-08-002-moment-prompt-style/RESULTS.md` §5
- [ ] **Measure on characters with no `portrait_positive`** (authored appearance prose
      only) — the common case for hand-written casts, and the weaker input to
      `moment_agent.visual_tag`.
- [ ] **Judge image fidelity, not just prompt grounding.** `appearance_coverage` reads
      the prompt; nothing yet checks whether the painted figure resembles the authored
      character. Needs a VLM judge or human raters.

### From EXP-2026-08-008 (`complete` — the prose form through the live turn engine)

- [ ] **Measure in-character drift with the penalties off.** EXP-2026-08-007 removed
      `frequency_penalty`/`presence_penalty` because they destroyed sentence structure, but
      those penalties were added to fight drift and neither experiment measures drift. The
      trade was taken on one side of the ledger only. Needs a long-session eval —
      repetition of a character's own phrasings over time, or blinded speaker attribution —
      run with the penalties off and on.
      → `experiments/EXP-2026-08-008-prose-end-to-end/ISSUES.md`
- [ ] **Re-run the sampler arms on a second model.** EXP-2026-08-007 is entirely
      `qwen38-27B-awq`; only the shipped configuration has been observed on
      `gemma4-26B-mtp`. Until the arms are re-run there, the finding does not transfer.
- [ ] **Give the player an identity in the prompt rather than a label.** The transcript
      labelled the human's line `Player:`, and the models reached for that label as a name
      for a person in the room. The fix here is second person plus a guard; a scenario-level
      player name (or a mandatory POV character) would remove the ambiguity at the root
      instead of instructing around it.
- [ ] **Add an opening-gate seam to narration.** The character path can discard a bad
      opening and regenerate; narration delta-streams from its first token by design,
      because it is the first thing a new player sees. That means a narration leak has no
      backstop but the prompt. Worth deciding whether a short hold on the *first* narration
      of a turn is worth its latency.
- [ ] **Score the writing, not only its shape.** Every metric here is a countable shadow of
      "reads like a scene". Nothing measures whether a passage is *good*, and the read that
      says so is unblinded and by the author of the change.

### From EXP-2026-08-009 (`complete` — second person instead of a label)

- [ ] **Find out why passages got 66 % longer** (780 → 1292 chars) when the player's label
      changed, and whether it survives sessions with a different dramatic arc. If the second
      person genuinely lengthens beats that is a finding; if it was this session escalating
      into a forced door, it is noise currently sitting in a results file.
      → `experiments/EXP-2026-08-009-prose-second-person/RESULTS.md` §6
- [ ] **Build a config seam for arm-level prompt tests.** Every prompt comparison in this
      record — EXP-2026-08-009 included — is a before/after across two runs, because the turn
      engine cannot serve two prompt variants inside one session. That is the ceiling on all
      of this evidence, and it is a build task, not a research one.
- [ ] **Widen the leak detector or stop trusting it.** `names_the_player` is two phrases; a
      model that writes "the human" or "whoever is typing" passes it.
- [ ] **Check the `Player:` labels left in `planner_agent`, `director_agent` and
      `intent_agent`.** They were left alone because their outputs are structure, not prose —
      but `director_agent` writes branch labels the player reads, so that is untested rather
      than safe.

### From EXP-2026-08-010 (`complete` — Short/Medium/Long beat length)

- [ ] **Find out why the opening gate released a passage that both `starts_mid_sentence` and
      `names_the_player` flag as bad.** A 2,802-character scratchpad leak was persisted and
      rendered in the `short` arm; the trace records only the runaway stop. Run against the
      guards directly, that text returns `True` from both — so the beat should have been
      discarded and regenerated. The gate judges a passage's *opening* and then releases it,
      and `written` counts the raw stream independently, so a leak arriving after release is
      invisible. **Highest-value item here, and nothing to do with beat length.**
      → `experiments/EXP-2026-08-010-beat-length/RESULTS.md` §6
- [ ] **Decide whether `short` should be relabelled "2–3 ¶".** It never produced a
      one-paragraph beat in 20 tries; its floor is 2. The dropdown promises 1–2.
- [ ] **Document or reconcile the `maxTurns` × `beat_length` interaction.** `maxTurns` caps
      emitted beats, so turning length up quietly turns the number of speakers per turn down
      (20 / 17 / 15 character beats across the arms). Two independent controls that are not
      independent.
- [ ] **Check `beat_length` against `register`.** A `grave` beat is told to be "shorter,
      sharper" while `long` asks for five or six paragraphs; the two directives sit in the
      same TAIL and have never been checked against each other.
- [ ] **Re-run the tiers on a second model.** Everything is `gemma4-26B-mtp`.

### From EXP-2026-08-011 (`complete` — context compaction, and the result is against it)

- [ ] **Fix `maybe_compact`'s trigger and re-run.** The gate tests `fit.dropped_beats < block`
      — beats dropped *in total*, not since the last summary — so once one anchor block has
      fallen out it never closes, and the summary was rewritten 16 times in 30 turns against a
      predicted 4. That is the whole of the prefix-reuse loss (80.3 % → 44.6 %). **The bounded
      design the claim describes has therefore never been run.** Needs a condition on the fresh
      beats plus a unit test that fails on the current one — the existing suite passes because
      it asserts compaction *fires* after a block, never that it fires *only* then, and the
      difference needs a scene long enough for a second block.
      → `experiments/EXP-2026-08-011-context-compaction/ISSUES.md` §6
- [ ] **Teach the recap agent to keep entity-attached specifics.** The summary reduced "owes
      the harbourmaster four hundred crowns, brass key sewn into his collar" to
      `* Rensal: owes 400 crowns.` — it kept the plot state and dropped the creditor and the
      key. The character then answered the probe faithfully from a record that no longer held
      the fact. Continuity is made of exactly the specifics a scene summary is built to drop,
      and a prompt change is the cheapest lever on it.
      → `experiments/EXP-2026-08-011-context-compaction/RESULTS.md` §4
- [ ] **Make the control comparable.** Arm A was a fixed 100-beat window and never dropped the
      plant, so it was "still reading the fact", not "compaction off". Re-run with a smaller
      fixed `contextBeats` or more turns so H1 is an equivalence test rather than one a fixed
      window wins by construction.
      → `experiments/EXP-2026-08-011-context-compaction/ISSUES.md` §1
- [ ] **Answer H3.** Prose quality is **not measured**: a blinded pairwise read of matched
      beats was pre-registered and not performed, and a preference stated by a reader who
      already knows the arms is not evidence. Needs a reader who has not seen them labelled.
- [ ] **Raise n.** One scene per arm, one probe, one model, 140 min of local inference. The
      result is an existence proof and cannot be read as a rate.

### From `docs/plans/steering-the-scene.md` Phase 7 (direction delivery)

- [ ] **Sweep `DIRECTION_COVERAGE_THRESHOLD`.** A scene direction requirement is now confirmed
      delivered from the prose a beat actually emitted, using a lexical coverage check
      (`app/services/direction_check.py`). The default (**0.34**) and the stopword classes
      (abstract subject placeholders; speech-act verbs) were chosen from an *argument* — good
      prose paraphrases a requirement's verbs and keeps its concrete nouns — plus two live
      cases that misfired at the previous settings and are now pinned as regression tests.
      **That is reasoning and anecdote, not a measurement.**

      Protocol sketch: collect direction/beat pairs from real sessions and hand-label each
      *delivered* or *not*, blind to the score. Compute precision and recall per threshold
      across 0.2–0.7. Report **per-run rows and no aggregate** if any run fails to complete —
      survivors of a partial failure are not a random subsample (`EXP-2026-08-001` is the
      worked example of getting that wrong). The asymmetry matters and should be stated in the
      analysis: a false negative costs one retried beat, while a false positive silently drops
      what the player asked for, so the operating point should sit well below the
      precision-recall crossover.
- [ ] **Check whether the retry actually helps.** `DIRECTION_MAX_ATTEMPTS` is 2 on the
      assumption that a second beat aimed at the same requirement often lands it. Nothing has
      measured the second attempt's success rate; if it is near zero the cap should be 1 and
      the budget spent elsewhere.
