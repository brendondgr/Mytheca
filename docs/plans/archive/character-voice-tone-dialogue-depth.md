# Character Voice & Tone — Dialogue-Depth Rewrite

## 1. Introduction

The existing **Voice & Tone** feature (`docs/plans/archive/character-voice-tone-consistency.md`, already built and merged) generates a small list of `{situation, sample}` pairs per character and injects them into the turn loop so dialogue stays in-voice. The user reports the generated samples feel stilted and "textbook" — the current `_VOICE_SYSTEM` prompt (`web/backend/app/agents/character_agent.py`) asks for a *short situation label* (e.g. `"offered a bribe"`) paired with *one or two sentences* of reply, which produces flat, summary-style output rather than something that demonstrates how the character actually talks.

This plan **rewrites the generation prompt only** — no new schema, storage, endpoint, or UI plumbing (all of that already exists and stays as-is: the `{situation, sample}` shape, the `POST /characters/voice-samples` endpoint, the Propose/Redo button, the turn-loop injection). The rewrite changes the *content contract*: the model must first reason through the character's distinctive voice (diction, rhythm, tics, formality — grounded in their background/personality/speech), then produce 2–3 pairs where `situation` is what's said or happens *to* the character (often another character's line of dialogue) and `sample` is a **full back-and-forth dialogue exchange** in the character's own voice (several alternating lines), not a single flat sentence. The two places that render `voice_samples` into prompt/RAG text (`assembler._format_voice_samples`, `rag/entries._voice_samples_text`) are reformatted to read naturally with this longer, dialogue-shaped content, and the editor UI copy (`VoiceSamplesEditor.tsx`, `CharacterModal.tsx`) is updated to match so authors get the same expectation when hand-writing samples.

## 2. Gaps & Unanswered Questions

- **Keep the `{situation, sample}` field names?** (resolved, assumption): yes — only the *semantics and length* of each field change (situation becomes a dialogue prompt/beat, sample becomes a multi-line exchange). Renaming the JSON keys would force schema/frontend-type/test churn across 6+ files for no functional benefit; the field names are generic enough to carry the new meaning.
- **Sample count** (resolved, assumption): drop the target from 3 (2–4) to **2–3** pairs, cap stays at `_VOICE_SAMPLES_CAP = 4`. Fewer, richer, longer exchanges beat more, thinner ones — keeps the turn-prompt HEAD block from growing unbounded now that each sample is several lines instead of one.
- **Does the turn-loop injection preamble in `character_turn_agent.py` need to change?** (resolved, assumption): no — "Voice samples — how you sound (match this cadence, diction, and attitude in both speech and thought)" already reads correctly whether the content beneath it is one line or a multi-line exchange. Leaving it untouched avoids churning `test_character_turn_agent.py`, which asserts that exact string.
- **No complex gaps requiring human intervention.**

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend: rewrite the generation prompt + rendering format

- **Locations:**
  - `web/backend/app/agents/character_agent.py` — rewrite `_VOICE_SYSTEM` (~lines 113–126): instruct the model to first reason through the character's distinctive voice (diction, sentence rhythm, verbal tics, formality/dialect, what they avoid saying) grounded in the supplied background/personality/traits/speech, then produce **2–3** `{situation, sample}` pairs where `situation` is another party's line of dialogue or a vivid narrative beat aimed at the character, and `sample` is a **full back-and-forth exchange** (the character's reply, a short beat from the other party, the character's counter — several alternating lines) rather than one sentence, varied in register across pairs (calm, pressured, challenged, warm). Keep the JSON contract (`{"samples": [{"situation": ..., "sample": ...}]}`, no other keys) and `_VOICE_SAMPLES_CAP` unchanged. Update the module docstring line (~line 11–13) and the `propose_voice_samples` docstring (~line 360) to describe the new depth.
  - `web/backend/app/services/assembler.py` — reformat `_format_voice_samples` (~lines 172–187): replace the `"- When {situation}: \"{sample}\""` bullet with a two-line block (e.g. `- Prompt: "{situation}"\n  You: {sample}`, falling back to `- You: {sample}` when situation is blank) so a multi-sentence exchange reads cleanly instead of running on after a colon.
  - `web/backend/app/rag/entries.py` — mirror the same reformat in `_voice_samples_text` (~lines 50–61) for consistency between the turn-prompt and RAG-retrieval renderings.
  - `web/backend/app/schemas/character.py` — update the `VoiceSample` docstring (~lines 10–18) to describe `situation` as the prompting line/beat and `sample` as the full in-voice exchange (schema fields/types unchanged).
- **Rationale:** This is the actual fix the user asked for — everything downstream (turn-loop injection, RAG retrieval, editor) just renders/stores whatever this prompt produces, so the content-quality problem is solved entirely at the generation source plus the two render sites that assume the old short-phrase shape.
- **Tests:** `utils/tests/backend/services/test_assembler.py::test_voice_samples_rendered_into_cast` (~lines 96–115) asserts the old `"When haggling:"` / `"When threatened:"` bullet text — update the assertions to match the new rendered format (the fixture's short situation strings can stay; only the wrapping format changes). Confirm `utils/tests/backend/rag/test_entries.py::test_character_entry_maps_traits_and_prose` and `utils/tests/backend/agents/test_character_turn_agent.py::test_voice_samples_injected_into_head` still pass unchanged (they assert on substrings/pass-through, not the old bullet format). Re-run `utils/tests/backend/agents/test_character_agent.py::test_voice_samples_parses_and_caps` and the two adjacent voice-sample tests (~lines 215–256) to confirm parsing/capping/best-effort behavior is untouched by the prompt-text rewrite.
- **Action:** Run `.venv/bin/python -m pytest utils/tests/backend/services/test_assembler.py utils/tests/backend/rag/test_entries.py utils/tests/backend/agents/test_character_agent.py utils/tests/backend/agents/test_character_turn_agent.py` + `ruff check` + `mypy` on touched files. Once green, commit: `[Voice Tone Dialogue Depth] (1/3) Complete: rewrite voice-sample generation prompt for in-depth dialogue exchanges + reformat renderers.`

### Phase 2 — Frontend: editor copy to match the new format

- **Locations:**
  - `web/frontend/components/feature/VoiceSamplesEditor.tsx` — update the top doc comment (~lines 8–18) to describe the new situation→exchange shape; update the situation `<input>` placeholder (~line 56, currently `"Situation — e.g. offered a bribe"`) to something like `'What's said to them — e.g. "For the right price, I could forget I saw you here."'`; update the sample `<textarea>` placeholder (~line 73, currently `"What they'd say — in their own voice."`) to describe a full exchange; bump the textarea `rows` (~line 76, currently `2`) to `4` so the larger content is visible without scrolling; update the empty-state hint (~lines 39–41).
  - `web/frontend/components/feature/CharacterModal.tsx` — update the Voice & Tone section description paragraph (~lines 363–366, "Example lines showing how this character sounds — a situation and what they'd say…") to describe a back-and-forth exchange instead of a one-line description.
- **Rationale:** The editor is also used for **hand-authored** samples (not just Propose-generated ones); if the copy still promises "one line" the author will keep writing the old flat style even after the generation prompt improves. Purely UI copy — no state/logic/type changes, so no plumbing touched.
- **Tests:** `web/frontend/components/feature/VoiceSamplesEditor.test.tsx` — confirm existing add/remove/patch-row tests still pass unaffected by placeholder/copy text (they query by `aria-label`, not placeholder). No new test needed for copy-only changes.
- **Action:** Run `npm test -- VoiceSamplesEditor CharacterModal` + `npm run typecheck` + `npm run lint`. Once green, commit: `[Voice Tone Dialogue Depth] (2/3) Complete: update Voice & Tone editor copy to match dialogue-exchange format.`

### Phase 3 — Docs + full validation + merge to main

- **Locations:** `docs/api-contract.md` (~line 28, the `voiceSamples` shape description; ~line 416–423, the endpoint description) — tweak the one-line description of the `{situation, sample}` pairs to note they're now in-depth dialogue exchanges. `docs/data-flow.md` (~lines 152–163) — same note in the authoring-flow description. `docs/checklist.md` — add a short "done" entry under Follow-up Work summarizing this rewrite (prompt-only change, no schema/UI-plumbing change), referencing this plan.
- **Rationale:** Global project rules require docs to move with behavior in the same change; this is a content/behavior change to a documented field, not just an internal refactor.
- **Action:** Run the full validation gate — backend `.venv/bin/python -m pytest` (full suite) and frontend `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`. Once green, commit: `[Voice Tone Dialogue Depth] (3/3) Complete: docs + full validation; merge dialogue-depth voice/tone rewrite to main.` Merge the worktree branch to `main` (do not push unless asked), resolving any conflicts.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Rewritten generation prompt | `_VOICE_SYSTEM` — plan-the-voice-first, situation-as-dialogue-prompt, sample-as-full-exchange | `web/backend/app/agents/character_agent.py` |
| Reformatted turn-prompt renderer | `_format_voice_samples` block format for multi-line exchanges | `web/backend/app/services/assembler.py` |
| Reformatted RAG renderer | `_voice_samples_text` block format for multi-line exchanges | `web/backend/app/rag/entries.py` |
| Updated schema docstring | `VoiceSample` field semantics documented | `web/backend/app/schemas/character.py` |
| Updated editor copy | Placeholders/description/empty-state matching the exchange format | `web/frontend/components/feature/VoiceSamplesEditor.tsx`, `web/frontend/components/feature/CharacterModal.tsx` |
| Backend tests | Updated render-format assertions; parsing/injection tests re-verified unchanged | `utils/tests/backend/services/test_assembler.py` |
| Docs | Contract, data-flow, checklist entry | `docs/api-contract.md`, `docs/data-flow.md`, `docs/checklist.md` |
