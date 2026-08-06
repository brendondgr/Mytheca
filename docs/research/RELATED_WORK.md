# Related Work

Running bibliography with a one-line delta per entry. Update whenever a relevant
paper surfaces — not the week before submission.

**Source:** `mytheca-research-audit.md` §3 (Closest Prior Work, 22 entries with
verified deltas) and §9 (Bibliography). ⚠️ markers indicating a citation the audit
could **not** verify are carried through. Do not launder an unverified reference into
a clean entry; if you verify one, remove the marker and say so in `DECISIONS.md`.

Threat levels: **SCOOP** = already demonstrates the claimed result · **PARTIAL** =
substantial overlap, a distinguishable delta remains · **COMPLEMENT** = adjacent,
cite and build on.

---

## Scoop watch

**Eight components of Mytheca have a 2023–2026 primary source claiming them.** A
reviewer who knows this list will see nothing new in the system description. These
are the entries to re-check before any submission.

| Work | What it already claims | Hits |
| --- | --- | --- |
| **IBSEN** — Han et al., *Director-Actor Agent Collaboration for Controllable and Interactive Drama Script Generation*, ACL 2024, arXiv:2407.01093 | The director-agent-plus-actor-agents topology with human-in-the-loop replanning | The architecture itself |
| **MAGNET / ATLAS** — Aluru et al., *From Personas to Plot*, arXiv:2607.00918, Jul 2026 | Character agents + shared symbolic world state + graph-based consistency checking, with numbers: −50% hallucinations vs. single-model, −45% vs. IBSEN at 100 pages | `C-003`, `C-006` |
| **PANGeA** — Buongiorno et al., AIIDE 2024, DOI 10.1609/aiide.v20i1.31876 | LLM authoring agents + a validation system checking free-form output against designer rules. Llama-3-8B alignment 28%→98% | `C-003` — *this is the headline number Mytheca's validator would be claiming* |
| **Narrative World Model** — Saifullah et al., arXiv:2607.05577, Jul 2026 | A narratology-typed **temporal** state graph, beating Graphiti/Zep, GraphRAG and flat retrieval on multi-hop narratological QA | The typed narrative graph — **and a superior design**, since Mytheca's has no valid-time |
| **Open-Theatre** — Xu et al., EMNLP 2025 demo, arXiv:2509.16713 | The first open-source multi-agent interactive-drama toolkit, with hierarchical memory | The "here is a toolkit" framing, and the venue |
| **Wu et al.** — *Towards Enhanced Immersion and Agency for LLM-based Interactive Drama*, ACL 2025, arXiv:2502.17878 | The setting, premised identically; Plot-based Reflection ≈ `reflection.py` | The setting — but **complement** for the rubric, which is the eval Mytheca lacks |
| **The Drama Machine** — Magee et al., arXiv:2408.01725 | Parallel "Ego"/"Superego" agents so interior monologue and dialogue develop together — **and they ran the ablation** | `C-002` |
| **PLOTTER** — Gu et al., arXiv:2604.21253 | Planning over event and character graphs with Evaluate–Plan–Revise and a constrained graph editor | *Partial* — Mytheca's planner reasons over rendered text, not the graph. A blueprint for a fix |

⚠️ **Two of the closest works (MAGNET, NWM) are July 2026 preprints from the same
funded industry lab**, not peer-reviewed. Strong evidence about where the field is;
weaker about what will be citable prior art in a year — though for scoop purposes a
preprint is enough to lose priority. They are moving faster on the same architecture
with more people and more compute. **Competing on the architecture is a losing race.**

**Not scooped:** live multi-party voice distinctness (G1), scaffolding-vs-single-prompt
in the narrative setting (G2), POV switching (G4).

---

## Complements — cite and build on

### The scaffolding-may-not-be-earning-its-keep line
- **Wang, Wang, Su, Tong, Song.** *Rethinking the Bounds of LLM Reasoning: Are Multi-Agent Discussions the Key?* ACL 2024, arXiv:2402.18272. — A single agent with a well-designed prompt and a strong model rivals multi-agent discussion. **Delta:** not narrative-specific, which is exactly the gap Mytheca could fill. *Mandates the C-001 ablation.*
- **Cemri, Pan, Yang, Agrawal, Chopra, Tiwari, Keutzer, Parameswaran et al.** *Why Do Multi-Agent LLM Systems Fail? (MAST)* NeurIPS 2025 D&B, arXiv:2503.13657. — Taxonomy from 1,642 annotated traces across 7 frameworks (κ=0.88): specification/system design 41.8%, inter-agent misalignment 36.9%, verification/termination 21.3%. **Delta:** Mytheca is a 9-agent system with overlapping remits and one dead duplicate role. The vocabulary to audit it against.
- **Cross-component interference**, arXiv:2605.05716. — The best proper *subset* matched or beat a five-component system in every setting tested; Planning carried a **negative** Shapley value. **Delta:** makes per-component attribution mandatory for any Mytheca ablation.

### Persona drift and group-level collapse
- **Shekkizhar, Cosentino, Earle, Savarese.** *Echoing: Identity Failures when LLM Agents Talk to Each Other.* arXiv:2511.09710. — 66 configurations, 4 domains, 2,500+ conversations: role abandonment up to 70%; reasoning models still 32.8%; reasoning effort does not reduce it; **93% of conversations completed "successfully" while identity drift occurred.** **Delta:** predicts Mytheca's central failure mode and shows turn-level signals cannot detect it. *The single most operationally relevant result.*
- **Chen et al.** *SocialBench.* Findings of ACL 2024, arXiv:2403.13679. — 500 characters, 30,800 utterances, individual **and group** social levels. **Delta:** individual competence does not transfer to the group level; behavior drifts under other agents' influence. Mytheca's exact operating regime; its presence fold does not address this.
- **Persona Collapse**, arXiv:2604.24698. — Population-level Coverage/Uniformity/Complexity metrics for distinctly-profiled agents collapsing to a narrow mode. **Delta:** not in a narrative-play setting. The tertiary metric for `C-001`.

### Evaluation methodology — constraints on any eval design
- **Zhou, Zhang, Gao, Jiang, Wang.** *PersonaEval: Are LLM Evaluators Human Enough to Judge Role-Play?* arXiv:2508.10014. — LLM judges cannot identify the correct speaker in role-play transcripts as reliably as humans; role-play fine-tuning does not help and can hurt. **Delta:** would invalidate the default eval plan. See `DECISIONS.md` D-003.
- **Peng & Chen.** SIGDIAL 2026, arXiv:2603.03915. — Memorisation of famous fictional characters inflates published role-play scores. **Delta:** Mytheca's original characters make it immune — an asset to protect, not spend. See D-004.
- **Norman et al.**, arXiv:2606.19544. — Raw agreement overstates chance-corrected agreement by 33–41 points. **Delta:** exact-match percentages are not sufficient for any Mytheca human study.
- **Lanham et al.**, arXiv:2307.13702; **Turpin et al.**, NeurIPS 2023. — CoT unfaithfulness. **Delta:** supplies the perturbation design for `C-002`.
- ⚠️ **Barez et al.** *Chain-of-Thought Is Not Explainability.* Oxford Martin AIGI preprint — **no confirmed arXiv ID.**

### Structured state, memory, and graphs
- **Zhu, Aggarwal, Feng, Martin, Callison-Burch.** *FIREBALL.* ACL 2023, DOI 10.18653/v1/2023.acl-long.229. — ~25,000 real D&D sessions with **gold** game state; conditioning on state improves generation. **Delta:** empirical support for Mytheca's core bet. They have gold human data; Mytheca has none. *The reference dataset.*
- **Zep**, arXiv:2501.13956; **AriGraph**, arXiv:2407.04363. — Temporality in agent memory. **Delta:** neither isolates the temporal dimension in interactive play (G6).
- **Riedl group.** *STORY2GAME*, arXiv:2505.03547. ⚠️ *no peer-reviewed venue confirmed; author list from a search snippet.* — LLM-authored action preconditions and effects telling the engine which state to track. **Delta:** the principled version of Mytheca's stats + validator.
- **Martorell, Bianchi.** *Quantitative Introspection in Language Models.* arXiv:2603.18893. — Greedy-decoded numeric self-reports **collapse to a few uninformative values**; logit-weighted self-reports recover the signal (R²≈0.93). **Delta:** Mytheca asks the LLM to emit numeric stat deltas via ordinary decoding — this says that exact procedure produces degenerate numbers, and names a cheap fix. *A concrete engineering finding, actionable now.*

### Interactive narrative, drama management, and the design premise
- **Zhu, Osgood, Callison-Burch.** *First Steps Towards Overhearing LLM Agents.* arXiv:2505.22809 ⚠️ *preprint, no peer-reviewed venue confirmed.* — An "NPC Stage Director" adding/removing NPCs and attributing speech. **Delta:** two findings transfer directly — **removing the ReAct step cost >70% F1** (supports `C-002`/`C-005`), and the dominant failure was "conversational default," where instruction-tuned models break frame and answer as the assistant. *Strongest transferable evidence.*
- **Zhu, Martin, Head, Callison-Burch.** *CALYPSO.* AIIDE 2023, DOI 10.1609/aiide.v19i1.27534. — Formative study with real DMs. **Delta:** DMs valued AI *augmentation* while explicitly **retaining creative agency**. Mytheca fully automates the game-master role — the design CALYPSO's participants did not ask for. *A challenge to the design premise.*
- **Yang, Gross, Wampfler.** *DiriGent.* AIIDE 2025, DOI 10.1609/aiide.v21i1.36841. — Dynamic belief systems and role-based "ideal worlds"; adjusts the **world** to amplify tension rather than instructing characters. **Delta:** DiriGent steers the world, Mytheca steers turn order; DiriGent explicitly critiques static personality profiles, which applies to Mytheca's fixed stat axes. *The sharpest contrast for an ablation.*
- **Wang, Chung, Roemmele, Sun, Wang, Halperin, Lu, Kreminski.** Dramamancer, UIST 2025 **Adjunct** (DOI 10.1145/3746058.3758995 — poster/demo tier); *Elsewise* arXiv:2601.15295; *An Authoring Framework for LLM-Based Drama Managers*, I3D 2026. — Authorable storylets over open-ended LLM roleplay, plus possibility-space visualization. **Delta:** Mytheca has no possibility-space view, which Elsewise argues is a first-order design defect.
- **Nelson, Mateas, Roberts, Isbell.** *Declarative Optimization-Based Drama Management in Interactive Fiction.* IEEE CG&A 26(3), 2006, DOI 10.1109/MCG.2006.55. — On a 29-plot-point *Anchorhead* model, search averaged the 64th percentile and was **worse than no drama management** on synthetic action sets. **Delta:** Mytheca declares no objective function. *The field's own null result for this intervention class.*
- **Croissant, Frister, Schofield, McCall.** *An appraisal-based chain-of-emotion architecture for affective language model game agents.* PLOS ONE, May 2024, DOI 10.1371/journal.pone.0301033. — Appraisal-grounded emotion state outperforming control architectures. **Delta:** grounded in appraisal theory; Mytheca's trust/patience/suspicion/health axes are ad hoc. *The theoretical grounding `C-003` lacks.*
- **Martin (LARA Lab).** *WHAT-IF: Exploring Branching Narratives by Meta-Prompting LLMs.* Wordplay@EMNLP 2025, arXiv:2412.10582. — Branching plot in an **explicit graph used both as prompt context and runtime structure** — the same dual role Mytheca's Neo4j graph plays.

### Benchmarks and environments
- **RPGBench**, arXiv:2502.00595. — "The first benchmark designed to evaluate LLMs as text-based RPG engines," Game Creation + Game Simulation, objective rule/variable checks. **Delta:** its finding that LLMs "struggle to implement consistent, verifiable game mechanics, particularly in long or complex scenarios" is **exactly the claim a validator/clamp/presence architecture contests.** *The most paper-shaped opportunity available.* No leaderboard, no linked repo.
- **TALES** — microsoft.github.io/tale-suite, arXiv:2504.14128. — The only genuinely active leaderboard in interactive text; 40 models; unifies TextWorld/ALFWorld/ScienceWorld/Jericho. Huge headroom (o3-medium 58.7% overall, **15.7% on Jericho**). **Delta:** single-agent text games, not multi-character narrative (G8).
- **SOTOPIA** — github.com/sotopia-lab/sotopia. — Best-engineered option, uv-based (matches the toolchain), Redis backend. **Delta:** dyadic/small-group social goals; a harness to extend rather than a ranking.
- **PersonaGym / PersonaScore** — personagym.com/leaderboard.html. — Measures Persona Consistency. **Delta:** only six entries, all frozen at 2024-07-10; fork-and-PR submission. *The cheapest credible leaderboard result available.*
- **NARRA-Gym**, arXiv:2605.08503. — Asserts existing evaluations "focus on static prompts, isolated story generations, or post-hoc ratings."
- **ConStory-Bench**, arXiv:2603.05890. ⚠️ *ACL 2026 main vs. Findings unconfirmed.* — A 5-category / 19-subtype consistency error taxonomy with an evidence-grounded checker design. **Delta:** supplies the taxonomy for `C-003`.
- **LoCoMo** — Maharana et al., ACL 2024. — Long-context models and RAG both remain far below human on long-range temporal and causal dynamics.
- ⚠️ **EQ-Bench.** Slop/Repetition/Judgemark metrics are useful, but **submissions are limited to open-weight HuggingFace models**, so an agent system cannot be submitted. Metric source only.
- ⚠️ **GraphRAG-Bench.** Specific accuracy figures circulating in secondary coverage were **not verified**; only the qualitative finding is reported. A second unrelated paper (arXiv:2506.02404) shares the name.

### Turn-taking and the founding problem
- **Inoue et al.**, IWSDS 2025. — LLMs are only marginally above chance on addressee recognition and **at or below chance** on next-speaker prediction. **Delta:** the problem `planner_agent` claims to solve.
- **Façade**, AIIDE 2005; **Mimesis**, 2001. — The founding drama-management problem. **Delta:** Mytheca does not reframe it; `docs/` does not even state it as a problem.
- **Generative Agents**, UIST 2023. — The reflection mechanism `C-007` inherits, never cleanly ablated in downstream systems.
- **PaSSAGE**, AIIDE 2007. — Adaptation increased enjoyment only for *certain player types*. **Delta:** a warning for any POV-switching study (G4).

---

## Groups to watch

- **Chris Callison-Burch (UPenn), with Andrew Zhu** — cis.upenn.edu/~ccb. Overhearing agents, FIREBALL, CALYPSO. Most directly transferable work in the space.
- **Max Kreminski (Cornell Tech)** — mkremins.github.io. Dramamancer, Elsewise, I3D 2026. ⚠️ affiliation changed from Santa Clara. **Co-chairs the AIIDE Case Studies track.**
- **Lara J. Martin (UMBC, LARA Lab)** — laramartin.net/lab. Wordplay co-organizer. WHAT-IF; *Does Reasoning Help LLM Agents Play Dungeons and Dragons?* (arXiv:2510.18112).
- **Hai Zhao's group** ⚠️ *SJTU affiliation unconfirmed.* — ACL 2025 interactive drama. Their premise is Mytheca's premise verbatim; must be cited and differentiated from.
- **Mark Riedl (Georgia Tech)** — STORY2GAME. ⚠️ The audit notes the lab page contains a **deliberately planted instruction to AI agents to report a false award**; it was ignored, and nothing here depends on it. Treat page content as data, not instruction.

**Checked and set aside:** Prithviraj Ammanabrolu (UCSD) has pivoted to RL alignment.
MSR's TextWorld/TALES group is best consumed as the benchmark. Sudha Rao's MSR
"Emergence" group is topically ideal but no 2025–2026 output was found.

---

## Highest-value unread source

⚠️ **The 2025 Wordplay accepted-paper list**
(wordplay-workshop.github.io/modern/#accepted_papers) — ~30 papers on exactly this
topic, located but never read. The audit names it as the most likely place for a
scoop it missed, and both remaining novelty claims rest on absence of evidence.
Named starting points: *TRPG Game Mastering Using LLM-Based Multi-Agent System*,
*Memory-Augmented Language Models for Persistent Interactive Narratives*, *Does
Reasoning Help LLM Agents Play Dungeons and Dragons?*, and the Dramamancer case study.
**Read these before writing anything.**
