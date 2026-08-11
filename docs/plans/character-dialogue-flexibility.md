# Character Dialogue Flexibility

> **Shipped 2026-08-11**, all six phases. Two deviations from the plan as written:
> the voice-sample field is called **`moment`**, not `register` — a pydantic field named
> `register` shadows `ABCMeta.register` on the model base — and reflection effort stayed
> `LOW` (see §2). The live in-browser a11y pass for the new Moment select could not run:
> `next/font/google` cannot reach Google Fonts in this sandbox, so the page never renders.
> Recorded in `docs/checklist.md` under *Deferred verification*.

## 1. Introduction

Characters currently speak from a fixed script. Their prompt head carries `speech`,
`traits`, and a block of authored situation → response pairs — concrete text proving
exactly how the person sounds — while the only counterweight is abstract prose in the
output contract asking them to "let the register flex with the moment". Concrete
exemplars beat abstract instructions, so a cocky character stays cocky while bleeding
out. Worse, the one signal that claims to describe the present moment
(`ctx.setting.atmosphere`, injected as *"the scene right now: …"*) is authored at world
creation and **never written again during play** — it actively pins every beat to the
scene's opening tone.

This plan replaces prose exhortation with a computed, per-beat **register** and makes
every downstream voice signal condition on it. `planner_agent.next_beat` already runs
once per beat and returns structured JSON; it gains a `register` + `stakes` field at no
extra LLM call. That register then (a) is stated as fact in the character prompt's
recency tail, (b) selects which voice samples get injected, and (c) tunes the sampler.
Finally, the genuinely-adaptive signal that already exists — `disposition` from
`reflection_agent` — is expanded and moved from the prompt head to the tail where
recency attention is strongest. Five phases, backend-heavy, with one frontend authoring
change in Phase 3.

This also closes the **Scene-appraisal signal** entry in `docs/checklist.md` — but by
piggy-backing on the planner call rather than adding the "one cheap shared per-turn LLM
call" that entry contemplated, so the local-model latency concern it raised does not
apply.

---

## 2. Gaps & Unanswered Questions

**Resolved by assumption (proceeding):**

- **Register taxonomy.** Four values — `light` · `neutral` · `tense` · `grave` — plus
  absent (`None`). One axis, not a matrix: a second `intensity` dimension would make
  voice-sample tagging combinatorial for the author with no clear payoff. `stakes` is a
  short free-text phrase (what is actually at risk right now) carried alongside.
- **Degradation.** Register is always optional. A planner fallback (offline, malformed
  reply, `APIError`), a puppet beat, or a directly-constructed `TurnContext` in tests all
  yield `register=None`, and every consumer must reproduce today's exact behavior in that
  case. This keeps the 784-case suite meaningful and keeps the turn loop working with no
  LLM configured.
- **Untagged voice samples.** Existing authored characters have no `register` on their
  samples. Selection therefore prefers matching-or-untagged rows and **falls back to the
  full set** when nothing matches — an existing world never loses its voice profile.
- **No migration.** `Character.voice_samples` is already a JSON column of free-form
  dicts; adding a `register` key inside each dict is additive and needs no Alembic
  revision.
- **Reflection effort stays `LOW`** (deviation from the approved Idea 7 as discussed).
  `dispatch_reflection` runs **inline** by default (`TURN_ASYNC_FINALIZE` is off), and in
  a crowd the *whole* present cast reflects — raising a 5-character cast to `MEDIUM`
  reasoning on a local model puts that cost directly on the turn tail. The prompt
  expansion and the head → tail move are the parts that carry the behavioral weight; the
  effort knob is recorded as a follow-up in `docs/checklist.md` rather than taken here.

**Needs human input — none.** Nothing in this plan is blocked.

**Deliberately out of scope** (recorded in `docs/checklist.md`, not silently dropped):

- The **narrator** does not receive the register. `narrator_agent` still uses
  `setting.atmosphere` for scenery, which is legitimate (it describes a place, not a
  present mood) — but a register-aware narrator is the obvious next increment.
- **Idea 4 (composure as a real stat)** and **Idea 6 (tonal redo pass)** were not
  approved for this round.
- `setting.current_state` is still never written during play. Phase 1 stops *misusing*
  it; it does not build the rolling scene-state writer that would make it true.

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Stop asserting a stale mood as the present moment

- **Locations:** `web/backend/app/agents/character_turn_agent.py` (`_build_user_prompt`
  — the `moment` cue in the TAIL, and the `Setting:` line in the MIDDLE);
  `utils/tests/backend/agents/test_character_turn_agent.py`.
- **Rationale:** This must land first and alone. Every later phase feeds a *real*
  per-beat signal into the same tail slot; leaving the authored-at-creation atmosphere
  there as *"the scene right now"* would have the two fight each other. Removing an
  active anti-signal is also the one change here that can improve output on its own.
- **Work:** Drop the `(the scene right now: …)` parenthetical from the tail cue entirely.
  Keep the `Setting:` line in the MIDDLE but relabel it so it reads as the authored
  description of the place rather than a live report. Leave the generic "read the moment"
  sentence — Phase 2 replaces its guts.
- **Test:** a case asserting that a `Setting` whose `atmosphere` says one thing does not
  produce a present-tense mood claim in the tail, and that the setting still appears once
  as scenery.
- *Action: Run `uv run pytest utils/tests/backend/agents/test_character_turn_agent.py`
  plus the full backend suite. Once green, commit:
  `[Character Dialogue Flexibility] (1/6) Complete: Stopped injecting the authored setting atmosphere as the scene's present mood.`*

### Phase 2 — The planner emits the register

- **Locations:** `web/backend/app/agents/prompt_registry.py` (`_PLANNER_SYSTEM`);
  `web/backend/app/agents/planner_agent.py` (`BeatDecision`, `next_beat` parsing,
  `_fallback_beat`); `web/backend/app/agents/character_turn_agent.py`
  (`generate_line` / `generate_line_with_usage` / `_build_user_prompt` gain
  `register` + `stakes`); `web/backend/app/services/turn_engine.py` (`_generate_speaker`
  signature + both call sites, and the existing `plan` trace frame);
  `utils/tests/backend/agents/test_planner_agent.py`,
  `utils/tests/backend/agents/test_character_turn_agent.py`,
  `utils/tests/backend/services/` (turn-engine threading).
- **Rationale:** This is the keystone — Phases 3 and 5 both consume the register, and
  Phase 4 is meaningless without it. It costs no additional LLM call because the planner
  already runs per beat and already returns JSON.
- **Work:** Add `"register"` and `"stakes"` to the planner's JSON contract with a short
  rule explaining each value. Add `register: str | None` and `stakes: str` to
  `BeatDecision`, parsed with a strict whitelist (anything unrecognized → `None`);
  `_fallback_beat` returns `None`. Thread the pair through `turn_engine._generate_speaker`
  into the character call, **including the consistency-guard re-run**. In the character
  prompt tail, state the register as an established fact plus a per-value directive, and
  name the stakes — replacing the generic "read the moment" question with an answer.
  Surface `register`/`stakes` in the existing `plan` trace frame's `data` so the Turn
  Inspector shows the call.
- **Docs:** `docs/data-flow.md` (the turn path gains a per-beat register),
  `docs/api-contract.md` if the trace frame's `data` shape is documented there.
- *Action: Run `uv run pytest`. Once green, commit:
  `[Character Dialogue Flexibility] (2/6) Complete: The planner now reads each beat's register and stakes, and the character prompt states them as fact.`*

### Phase 3 — Register-tagged voice samples, selected rather than dumped

- **Locations:** `web/backend/app/schemas/character.py` (`VoiceSample.register`);
  `web/backend/app/services/assembler.py` (`CastMember` gains the raw sample rows;
  `_format_voice_samples` becomes register-aware);
  `web/backend/app/agents/character_turn_agent.py` (renders the selected subset per beat);
  `web/backend/app/agents/character_agent.py` (`_VOICE_SYSTEM` asks for tags and requires
  at least one off-baseline sample); `web/frontend/lib/types.ts` (`VoiceSample`);
  `web/frontend/components/feature/VoiceSamplesEditor.tsx` (a register control per row);
  `web/frontend/features/library/editor.ts` + `useLibraryState.ts` (draft round-trip);
  `utils/tests/backend/services/test_assembler.py`,
  `utils/tests/backend/agents/test_character_agent.py`,
  `web/frontend/components/feature/VoiceSamplesEditor.test.tsx`.
- **Rationale:** The heart of the fix. Injecting every at-rest sample on every beat is
  what makes the character sound scripted; the model needs a concrete exemplar of *this
  specific person, not at rest*. Selection has to happen in the agent, not the assembler,
  because the register is only known per beat while assembly is per turn — hence the raw
  rows move onto `CastMember` and rendering moves to the call site.
- **Work:** Add an optional `register` to `VoiceSample` (empty = applies to any). Keep the
  pre-rendered all-samples string on `CastMember` (`director_agent` reads it) and add the
  raw rows beside it. Selection: rows tagged with the current register, plus untagged
  rows; if that yields nothing (or the register is `None`), render all — today's exact
  behavior. Relabel the injected block so it reads as *how you sound in a moment like
  this* rather than a baseline. Update the authoring prompt to tag each pair and to
  demand range (at least one `grave` or `tense` pair), raising the cap accordingly. On the
  frontend, add a native `<select>` per row with a visible label.
- **Validation extras:** UI change → accessibility + responsive pass (keyboard reachable,
  visible focus, AA contrast, labelled control, 320/375/768/1024).
- *Action: Run `uv run pytest`, then `npm test` + `npm run typecheck` + `npm run lint` in
  `web/frontend`, plus the a11y/responsive pass. Once green, commit:
  `[Character Dialogue Flexibility] (3/6) Complete: Voice samples carry a register and only the matching ones reach the prompt.`*

### Phase 4 — Register-conditioned sampler parameters

- **Locations:** `web/backend/app/agents/character_turn_agent.py` (`_voice_params`, the
  `_VOICE_*` constants); `utils/tests/backend/agents/test_character_turn_agent.py`.
- **Rationale:** The sampler is currently fixed for every beat. Frequency and presence
  penalties push the model toward *unused* tokens — that is, toward flourish and novelty,
  exactly the quip-seeking behavior we want suppressed when the moment is grave. Lowering
  them (and `top_p`) in a grave register lets plain, direct, even repetitive language
  through; raising them in a light register keeps banter lively.
- **Work:** Replace the three module constants with a small register → parameter table.
  `register=None` must resolve to today's exact triple (`top_p 0.92`,
  `frequency_penalty 0.4`, `presence_penalty 0.3`) so the fallback path is bit-identical.
  Temperature and `max_tokens` stay under the operator's config as they are today.
- *Action: Run `uv run pytest`. Once green, commit:
  `[Character Dialogue Flexibility] (4/6) Complete: Sampler penalties and top_p now track the beat's register.`*

### Phase 5 — Promote disposition to the recency tail

- **Locations:** `web/backend/app/agents/reflection_agent.py` (`_SYSTEM`);
  `web/backend/app/agents/character_turn_agent.py` (`_build_user_prompt` — disposition
  moves out of the HEAD and the existing weak tail note is replaced);
  `utils/tests/backend/agents/test_reflection_agent.py`,
  `utils/tests/backend/agents/test_character_turn_agent.py`.
- **Rationale:** `disposition` is the only per-turn signal in the system that already
  tracks how a character has actually been changed by events — and it is buried in the
  head, one clipped line long, outweighed by the whole voice-sample block above it.
  Moving it to the tail puts it where recency attention is strongest, beside the register.
- **Work:** Let the reflection prompt return a fuller disposition (2–3 sentences) that
  names the emotional shift, not just the want. In the character prompt, drop the head
  line, and in the tail state the stance as the character's current condition with
  explicit license to break their usual manner because of it. Effort stays `LOW`
  (see §2).
- *Action: Run `uv run pytest`. Once green, commit:
  `[Character Dialogue Flexibility] (5/6) Complete: A character's carried-in stance is fuller and now leads the act-now tail.`*

### Phase 6 — Documentation reconciliation and the full gate

- **Locations:** `docs/data-flow.md`, `docs/architecture.md`, `docs/documentation.md`,
  `docs/checklist.md`, `docs/api-contract.md`, `CLAUDE.md` if any routing fact changed.
- **Rationale:** The repo rule is docs-in-the-same-change, and Phases 1–5 each touch
  their own docs — this phase is the reconciliation pass: close the **Scene-appraisal
  signal** checklist entry with what was actually built, and record the three deferrals
  from §2 (register-aware narrator, reflection effort, rolling scene state) as open work
  rather than leaving them implicit.
- **Work:** Sweep for prose that the register invalidates. Delete superseded sentences
  outright rather than leaving them beside their replacement.
- *Action: Run the full gate — `uv run pytest`, `npm test`, `npm run typecheck`,
  `npm run lint`. Once green, commit:
  `[Character Dialogue Flexibility] (6/6) Complete: Documented the per-beat register path and recorded the deferred follow-ups.`*

---

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Stale-mood removal | Authored atmosphere no longer claims to be the present moment | `web/backend/app/agents/character_turn_agent.py` |
| Register contract | `register` + `stakes` on the planner's JSON reply | `web/backend/app/agents/prompt_registry.py` |
| `BeatDecision` fields | Parsed, whitelisted, `None` on any fallback | `web/backend/app/agents/planner_agent.py` |
| Register threading | Planner → engine → character call (incl. guard re-run) | `web/backend/app/services/turn_engine.py` |
| Register in the prompt | Stated as fact in the recency tail | `web/backend/app/agents/character_turn_agent.py` |
| Tagged voice samples | Optional `register` per pair | `web/backend/app/schemas/character.py` |
| Raw sample rows | Per-beat selection needs the unrendered list | `web/backend/app/services/assembler.py` |
| Authoring prompt | Tags each pair, demands off-baseline range | `web/backend/app/agents/character_agent.py` |
| Register control | Per-row select in the voice editor | `web/frontend/components/feature/VoiceSamplesEditor.tsx` |
| TS mirror + draft | `VoiceSample.register` round-trip | `web/frontend/lib/types.ts`, `features/library/{editor,useLibraryState}.ts` |
| Sampler table | Register → `top_p` / penalties | `web/backend/app/agents/character_turn_agent.py` |
| Fuller disposition | Reflection returns an emotional shift, not a want | `web/backend/app/agents/reflection_agent.py` |
| Backend tests | Planner parsing, prompt shape, selection, sampler, reflection | `utils/tests/backend/{agents,services}/` |
| Frontend test | Register control, co-located | `web/frontend/components/feature/VoiceSamplesEditor.test.tsx` |
| Docs | Turn path, checklist reconciliation | `docs/{data-flow,architecture,documentation,checklist}.md` |
