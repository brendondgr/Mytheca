# Venue Targets

Deadlines, page limits, anonymisation, and checklist requirements. Source:
`../mytheca-research-audit.md` §8, verified against pages retrieved **3 August 2026**.
Where a 2027 CFP does not exist, the most recent edition is the historical anchor and
is labelled as such. **Re-verify every date before acting on it.**

⚠️ **Standing constraint.** Nearly every archival venue has CFP language making a
zero-evaluation submission desk-rejectable:

- **AIIDE** — "results should be validated in a prototype or test-bed system."
- **EMNLP demo track** — submissions "that do not report any form of evaluation may
  be desk rejected," *and* a live demo link or downloadable package is required.
- **ICCC** — "some evaluation is expected," even for system-description papers.

---

## Tier 3 — Fast feedback (the recommended first move, not a consolation prize)

| Venue | Type | Deadline | Fit | Likelihood |
| --- | --- | --- | --- | --- |
| **ICIDS 2026 Late-Breaking Work** · icids2026.ardin.online | Archival (Springer LNCS), demo/poster | **14 Sep 2026 — OPEN** | ⭐ **Best current fit.** LBW is explicitly for "works in progress, working, presentable systems… selected if the full or short paper formats are unsuitable… due to their unfinished nature." Area: Methods and Tools | **Good**, even without evaluation — precisely the state LBW exists for |
| **EXAG 2026** (@ AIIDE, Belo Horizonte) · exag.org/call_for_papers | Workshop, CEUR **optional** | ⚠️ **21 or 28 Aug 2026 — two official pages disagree; assume 21 Aug and email the committee** | ⭐ Scope reads as if written for this project, and explicitly invites **"reports on failed experiments… with insight into what went wrong"** | **Good** — but tight, and papers must be 10–15 pp (full) / 5–9 pp (short) *including* references, with a **minimum** length enforced |
| **Evaluation of Interactive Agents @ NeurIPS 2026** · eval-interactive-agents-workshop.github.io | Workshop, **non-archival** | **29 Aug 2026 (AoE) — OPEN** | ⭐ Solicits "trajectory-level evaluation, including transcripts, tool calls, intermediate states" and "grader design, including deterministic checks." Mytheca's validator/presence/consistency triad **is** deterministic checks over agent trajectories. "Early-stage work is welcome" | **Moderate** — needs a claim and a preliminary measurement. Non-archival, so zero cost to later ARR/AIIDE options |
| **AIIDE Case Studies** · sites.google.com/view/aiide2026/calls/call-for-case-studies | Extended abstract (1–4 pp) + optional 2-hr demo | 2026 closed (9 Jul); **watch AIIDE 2027** | Requires only a **500-word outline** at submission. Co-chaired by Max Kreminski, whose Dramamancer work is directly adjacent | **Good** — lowest bar of any AAAI-affiliated venue, and the right home for the artifact *as an artifact* |
| **EMNLP/ACL/NAACL Demos** · 2026.emnlp.org/calls/demos | Archival demo | NAACL ~Feb–Mar 2027, ACL ~Apr–May 2027 (**extrapolated, not published**) | "Publicly available open-source systems are of special interest" | **Poor today** — needs an evaluation, a hosted demo, **and a license** |

⚠️ **Wordplay status is uncertain and it matters.** The single most on-topic workshop
in existence; 5th edition ran at EMNLP 2025. **No 2026 or 2027 edition confirmed**,
and it is absent from the EMNLP 2026 workshop list as far as could be determined.
Its 2025 accepted-paper list is the best available map of direct competition — see
the standing follow-up in `../OPEN_QUESTIONS.md`. Relatedly, the **ACL Joint Call for
Workshop Proposals 2027 closes 4 September 2026** and is a single shot for the whole
2027 cycle; proposing a successor workshop is unconventional but real, and best
pursued with the existing organisers (Ammanabrolu, Bosselut, Côté, Martin, Wakaki,
Yuan) rather than solo.

⚠️ **INT is effectively dormant.** Ran as "EXAG-INT 2025" (CEUR-WS Vol-4090) with
**3 submissions, 2 accepted**; absent from AIIDE 2026's workshops. Do not plan around it.

## Tier 2 — Target (after P1's evaluation exists)

| Venue | Deadline | Notes |
| --- | --- | --- |
| **AIIDE 2027** | **No 2027 CFP.** 2026 anchor: abstracts 26 Jun → papers 3 Jul 2026 | **Best topical fit of any archival venue** — Narrative Intelligence, Interactive Fiction, NLP in Games, Multi-Agent Systems in Games, NPC AI, Experience Management, Evaluation Methodologies. 9 pp, double-masked, **Limitations section required**, abstract precedes paper by a week, **optional artifact evaluation** after acceptance. ⚠️ AIIDE treats CEUR as archival — take the EXAG opt-out to preserve this option |
| **ICIDS 2027 full/short** | 2026 anchor: 5 Jul 2026 | Springer LNCS, strict double-blind ("non-anonymized papers will be desk-rejected"), ≥1 author must register and present (remote permitted). ⚠️ **Multiple fake conferences use the "ICIDS" acronym — only ARDIN's is legitimate** |
| **IEEE CoG 2027** | **No 2027 site.** 2026 anchor: papers 17 Mar, demos 30 Jun 2026 | 8 pp **including** references. Double-anonymous. "NONE OF THE SUBMISSION DEADLINES WILL BE EXTENDED." Tracks: AI for Game-playing (explicitly "believable agents"), PCG (explicitly "stories" and "characters"). Demo track needs no accepted paper |
| **FDG 2027** | **No 2027 CFP.** 2026 anchor: papers 15 Dec 2025; LBW/demos 30 Mar 2026 | 10 pp excl. references. Dedicated **Generative AI** track plus Game AI; a "Games and Demos" category. Double-anonymised with an author-response period |
| **ICCC 2027** | **Not announced.** ICCC'26 anchor: 8 Mar 2026 | Its **System or Resource description** type has the softest evaluation bar surveyed: "full evaluation… is not essential if the technical achievement is very high, some evaluation is expected." ⚠️ But generative-AI models "must be properly situated in the CC literature and evaluated according to acceptable practices in the field" |
| **IEEE Transactions on Games** | **Rolling — no deadline** | Requires "mature work." ⭐ New **Immersive papers** type: 6–14 pp **plus an interactive component submitted as a zip** — an unusually good structural fit. Open special issue on **LLMs and Games** (currency unverified). ⚠️ The site contradicts itself on blind review — confirm with the editors. Over-length charges $200/page |
| **ACM Creativity & Cognition 2027** | **Not announced** | Area: Creativity Support Tools. Verified 2026 rates: papers 20%, **posters 45%, demos 48%** — the poster/demo route is a plausible low-cost entry |

## Tier 1 — Reach (only under a reframing)

| Venue | Deadline | Verdict |
| --- | --- | --- |
| **ACL Rolling Review** → EACL/NAACL/COLING/ACL/EMNLP 2027 | **12 Oct 2026** → NAACL & COLING 2027; ACL 2027 cycle "January 2027" (exact date unpublished) | Long 8 pp / short 4 pp, anonymised, **Responsible NLP Checklist mandatory**, **Limitations section mandatory**, and **all authors must register as reviewers** or risk desk rejection. **Only viable under P1 or P4** — the system description is not a finding |
| **NeurIPS 2027 Evaluations & Datasets** | **2027 CFP not out.** 2026 anchor: 6 May 2026 | ⭐ The rename favours P2: "evaluation becomes an object of scientific study in its own right." ⚠️ Heavy: **double-blind now default**, data hosted at submission, **Croissant metadata with Responsible AI fields required**, **code release required at submission** — non-compliance justifies desk rejection |
| **CHI 2027** (Pittsburgh) | **10 Sep 2026** | Only viable under **P3**, and that is not enough time to run and write a user study properly. Word limits not page limits (>12,000 desk-rejected). All supplementary material and video figures **must also be anonymised**. ⚠️ **Four authors must be put forward as reviewers** — a real obstacle for a solo submission. ACM Open Access, so an APC may apply |

## Competitions and leaderboards

**There is no live 2026–2027 competition in interactive narrative, role-play, or LLM
game mastering.** AIIDE 2026's are StarCraft and quality-diversity level generation;
none of CoG 2026's ten are narrative; none of NeurIPS 2026's sixteen. CPDC has no
2026 edition but remains usable offline — its starter kit, leaderboard and ~12 public
system reports give ready-made baselines for persona + function-calling NPCs.

Benchmarks worth measuring against are ranked in `../RELATED_WORK.md`. The cheapest
credible leaderboard result available is **PersonaGym / PersonaScore** — six entries,
all frozen at 2024-07-10, fork-and-PR submission.

## Blockers that apply to every venue

- [ ] **No LICENSE file.** Blocks any artifact track, and blocks the EMNLP demo
      requirement outright. 0.1 weeks of work.
- [ ] **No evaluation.** Blocks every archival venue by explicit CFP language.
- [ ] **No hosted demo.** Blocks the ACL-family demo tracks.
- [ ] **Ethics-review route unconfirmed.** Blocks P3 and any human study; AIIDE, CHI
      and ICIDS all require a statement.
