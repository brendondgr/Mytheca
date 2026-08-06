# Plan: Situational Voice Adaptation

## 1. Introduction

Characters currently voice their lines beautifully but **rigidly**: they replicate their authored
speech style, voice samples, and recent lines regardless of the emotional stakes of the moment. A
cocky quipster keeps quipping at a funeral; a character bleeding out from a stab wound answers "Is
that all you got?" instead of showing fear. The dialogue matches the *character*, but the *manner*
never adapts to the *situation*.

The root cause is that every layer of the per-character turn prompt is tuned for style **imitation**
and nothing grants permission — or instruction — to let manner bend with the moment. The situational
signals that should trigger adaptation (the character's own stats, the setting's mood, the emotional
weight of recent beats) are all present in context but framed as passive scenery. This plan reframes
the character-turn prompting from *"a voice to replicate"* to *"a constant personality whose
expression flexes with the stakes,"* and adds an explicit "read the moment" appraisal as the first
thing the hidden `<thinking>` step does. It is **prompt-first**: no new LLM call, zero added latency.
All changes live in the backend turn agents (`web/backend/app/agents/`) and the persisted prompt
registry.

## 2. Gaps & Unanswered Questions

- **Scope of the fix (assumption, proceeding):** Prompt-first only. A heavier alternative — a shared
  per-turn "scene appraisal" LLM call feeding a mood signal to every speaker — is **deferred** because
  it adds latency/cost (the local reasoning model needs large token budgets + long timeouts per call),
  and the prompt reframing should carry most of the win. Flagged as a follow-up in `docs/checklist.md`
  to revisit only if playtesting shows prompt-only is insufficient.
- **Stat semantics (assumption, proceeding):** Stat keys are storyline-configurable, so the prompt
  will **not** hardcode "health = danger." Instead the character's current stat values (already in the
  HEAD) plus the full stat-guidance bands (already in the cacheable system prefix) give the model what
  it needs; the fix is the *instruction to appraise its own condition*, not a brittle deterministic
  classifier.
- **Persisted prompt override contract:** `CHARACTER_OUTPUT_CONTRACT` is a stored key
  (`prompt_overrides`); editing its **default text** is safe (no key rename, no migration). Confirmed
  against `prompt_registry.py`.
- **Concurrent-session working tree:** `main` has unrelated uncommitted frontend changes from another
  session (`CharacterCard.tsx`, etc.). This work is backend-only; it will be done in a **git worktree**
  on a feature branch so those changes are never swept into these commits, then merged back to `main`.

## 3. Hierarchical Step-by-Step Instructions

### Phase 0: Isolate the work

- **Locations:** repo root; new worktree under a sibling path; branch `feat/situational-voice-adaptation`.
- **Rationale:** `main`'s working tree carries unrelated uncommitted frontend edits (memory:
  concurrent-sessions gotcha). A worktree gives a clean, isolated backend checkout using the repo-root
  `.venv` (memory: worktree-backend-venv — do not `uv sync` per worktree).
- **Action:** Create the worktree + branch. No commit (setup only).

### Phase 1: Character output contract — situational adaptation

- **Locations:** `web/backend/app/agents/prompt_registry.py` (`_CHARACTER_OUTPUT_CONTRACT`).
- **Changes:**
  - Add an **adaptation principle** rule: personality is constant, *manner adapts* — a quip-heavy
    character still quips when things are light, but when the moment turns grave (a death, real danger,
    someone breaking down, their own life on the line) the act drops and the real person shows (fear,
    grief, urgency, tenderness). Include the two concrete before/after examples (funeral → soften;
    being stabbed/dying → afraid, not "is that all you got?").
  - Make the `<thinking>` template **appraise the moment first**: the opening move of the thought is to
    read the emotional weight/stakes and decide whether the habitual manner fits *before* reasoning
    toward a response.
  - Reframe the existing "think in the SAME voice as your speech style" rule to "the same underlying
    voice, its **register and intensity bending with the stakes**" — so reasoning is no longer
    style-locked.
- **Rationale:** The output contract is the single, cacheable source of the format + behavioral rules
  shared by every speaker; it is where the "don't be on autopilot" instruction belongs.
- **Tests:** `utils/tests/backend/agents/test_character_turn_agent.py` — update
  `test_thinking_contract_anchors_to_voice` (assertion text changes) and add a new test asserting the
  contract carries the adaptation principle (e.g. asserts "manner" / adaptation language + that the
  thinking step appraises the moment). Keep `test_thinking_contract_asks_for_a_fuller_in_voice_paragraph`
  and `test_dialogue_is_optional_but_thinking_is_always_required` green.
- **Action:** Run `uv run pytest utils/tests/backend/agents/test_character_turn_agent.py`. Once green,
  commit: `Situational Voice Adaptation (1/4) Complete: output contract grants manner adaptation + moment-first thinking.`

### Phase 2: Per-character prompt HEAD/TAIL reframing

- **Locations:** `web/backend/app/agents/character_turn_agent.py` (`_build_user_prompt`).
- **Changes:**
  - **HEAD:** soften the imperative framing of voice anchors — voice samples become "your **baseline**
    voice (how you sound at rest) — keep the person, let the register flex with the moment," recent
    lines become "your recent voice — a reference, not a script," speech/traits framed as defaults
    rather than mandates. Preserve the anchors (voices must still stay distinct) but remove the
    "always match" pressure.
  - **TAIL (recency):** add a "read the moment first" cue that surfaces concrete adaptation triggers —
    the setting's mood/atmosphere (restated as a tonal constraint, not scenery) and a nudge to weigh
    the character's own condition — instructing them to let the moment shape how they come across and
    to drop the usual manner when it demands it. Keep the existing act-now / directive / correction
    tail lines intact and last.
- **Rationale:** Recency attention is strongest at the tail; the appraisal cue lands hardest there,
  while the HEAD reframing removes the replication pressure that fights adaptation.
- **Tests:** `test_character_turn_agent.py` — update `test_voice_samples_injected_into_head` and
  `test_prompt_is_bookended_and_grounded` for the new HEAD wording; add a test asserting the TAIL
  carries the "read the moment" adaptation cue and that setting mood is surfaced when a setting is
  present. Ensure the prompt still starts with `You are [1] <name>` and ends with the act-now line.
- **Action:** Run `uv run pytest utils/tests/backend/agents/test_character_turn_agent.py`. Once green,
  commit: `Situational Voice Adaptation (2/4) Complete: reframe HEAD voice anchors + add read-the-moment recency cue.`

### Phase 3: Reflection disposition carries emotional/situational state

- **Locations:** `web/backend/app/agents/reflection_agent.py` (`_SYSTEM`).
- **Changes:** broaden the `disposition` field guidance so the between-turn stance captures the
  character's **emotional/situational state** (shaken, grieving, afraid, relieved), not just
  intent/want. This state is injected into the next turn's HEAD ("Your current inner stance: …"), so
  adaptation persists across turns instead of resetting each beat.
- **Rationale:** A single-beat appraisal can be undone next beat; carrying the emotional shift forward
  makes the adapted manner stick until the situation changes.
- **Tests:** `utils/tests/backend/agents/test_reflection_agent.py` — update/extend the disposition
  assertions to reflect the broadened emotional-state guidance (keep the JSON-shape + best-effort
  None-on-failure tests green).
- **Action:** Run `uv run pytest utils/tests/backend/agents/test_reflection_agent.py`. Once green,
  commit: `Situational Voice Adaptation (3/4) Complete: disposition carries emotional/situational state across turns.`

### Phase 4: Docs, full validation, merge

- **Locations:** `docs/data-flow.md` (the character-turn prompt/behavior description, if present),
  `docs/checklist.md` (record the deferred scene-appraisal follow-up + this feature done),
  `docs/plans/archive/situational-voice-adaptation.md` (this file — mark complete).
- **Rationale:** Global rules require docs updated in the same change that alters behavior.
- **Validation:** Full backend suite `uv run pytest` (backend-only change; frontend untouched, but note
  `main` carries unrelated frontend edits — do not run/entangle them). No UI change, so no a11y pass.
- **Action:** Commit: `Situational Voice Adaptation (4/4) Complete: docs + full-suite validation.` Then
  merge `feat/situational-voice-adaptation` into `main`, resolving any conflicts, and remove the
  worktree. Do not push.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Output contract adaptation | Manner-adapts principle + moment-first thinking + non-style-locked reasoning | `web/backend/app/agents/prompt_registry.py` |
| Prompt HEAD/TAIL reframing | Baseline-voice framing + read-the-moment recency cue | `web/backend/app/agents/character_turn_agent.py` |
| Reflection emotional state | Disposition carries situational/emotional state across turns | `web/backend/app/agents/reflection_agent.py` |
| Turn-agent tests | Updated + new assertions for adaptation wording | `utils/tests/backend/agents/test_character_turn_agent.py` |
| Reflection tests | Updated disposition assertions | `utils/tests/backend/agents/test_reflection_agent.py` |
| Docs | Behavior note + deferred follow-up recorded | `docs/data-flow.md`, `docs/checklist.md` |
</content>
</invoke>
