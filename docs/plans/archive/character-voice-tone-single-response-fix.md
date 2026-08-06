# Character Voice & Tone — Single-Response, Situation-Authentic Fix

## 1. Introduction

The **Voice & Tone** feature (`character_agent.propose_voice_samples`) generates a small list of `{situation, sample}` pairs per character, persisted with the character and injected into the turn loop so dialogue stays in-voice. A prior change (`docs/plans/archive/character-voice-tone-dialogue-depth.md`, `[Voice Tone Dialogue Depth]`) rewrote `_VOICE_SYSTEM` to ask for a **full back-and-forth dialogue exchange** per pair ("this character's reply, a brief beat from the other party, and this character's follow-up — three to five lines total, alternating speakers"). The user now reports this is wrong: a voice sample should show *one* situation the character was confronted with and *a single response* demonstrating their voice — not a multi-turn conversation. The user also reports the responses don't feel authentic or situation-specific — they read as a generic voice reused across situations rather than a reaction tailored to what's actually happening in each prompt.

This plan **reverts the exchange-format instruction and replaces it with a single-response, situation-authenticity contract** — still a prompt-content-only change, no schema/storage/endpoint/UI-plumbing change (the `{situation, sample}` shape, `POST /characters/voice-samples`, and the turn-loop injection all stay as-is, matching the precedent set by the dialogue-depth plan it corrects). `_VOICE_SYSTEM` (`web/backend/app/agents/character_agent.py`) keeps the "reason through the character's distinctive voice first" instruction (that part was sound) but changes the output contract: `situation` is a previous situation/prompt the character was confronted with, `sample` is the character's **single** in-voice response to it — not a dialogue exchange — and each response must react to the *specifics* of its situation (not restate a generic personality blurb), with tone/register shifting across the 2-3 pairs to prove the character sounds different when calm vs. pressured vs. challenged. The two render sites (`assembler._format_voice_samples`, `rag/entries._voice_samples_text`) and the `VoiceSample` schema docstring are updated to describe a single response instead of an exchange. The editor UI copy (`VoiceSamplesEditor.tsx`, `CharacterModal.tsx`) is updated to match so hand-authored samples follow the same single-response shape.

## 2. Gaps & Unanswered Questions

- **Keep the `{situation, sample}` field names and `_VOICE_SAMPLES_CAP`/pair-count target?** (resolved, assumption): yes — this is a content-contract change, not a shape change. Target stays 2-3 pairs, cap stays `_VOICE_SAMPLES_CAP = 4`.
- **Does the turn-loop injection preamble in `character_turn_agent.py` need to change?** (resolved, assumption): no — "Voice samples — how you sound (match this cadence, diction, and attitude in both speech and thought)" reads correctly under either content shape; `test_character_turn_agent.py` asserts that exact string and stays untouched.
- **Render format (`"- Prompt: ... / You: ..."` two-line block)?** (resolved, assumption): keep the two-line block from the dialogue-depth change — it still reads cleanly for a single multi-sentence response, only the docstrings describing it need to drop "exchange" language.
- **No complex gaps requiring human intervention.**

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Backend: single-response prompt + renderers + schema docstring

- **Locations:**
  - `web/backend/app/agents/character_agent.py` — rewrite `_VOICE_SYSTEM` (~lines 114-138): keep the "think through this character's distinctive voice first" framing, but change the output instruction from "a full back-and-forth dialogue exchange... three to five lines total, alternating speakers" to a **single** in-voice response (roughly 1-4 sentences, whatever length that character would actually use) that reacts to the *specific content* of its `situation` — not a generic statement of temperament restated across pairs. Add an explicit instruction that each response must be recognizably about *that* situation (reference what just happened) and that the 2-3 pairs must vary in register/stakes (calm, pressured, challenged, warm) so the character's range shows. Keep the JSON contract (`{"samples": [{"situation": ..., "sample": ...}]}`) unchanged. Update the module docstring (~lines 11-13, "in-voice dialogue-exchange pairs" → "in-voice response pairs") and the `propose_voice_samples` docstring (~line 372, "dialogue-exchange pairs" → "response pairs"). Update the `_VOICE_SAMPLES_CAP` comment (~lines 110-112, drop "each pair is now a multi-line exchange").
  - `web/backend/app/services/assembler.py` — `_format_voice_samples` docstring (~lines 172-177): drop "dialogue-exchange pairs" / "full in-voice exchange" language, describe as the prompting situation + the character's single in-voice response. Block format unchanged.
  - `web/backend/app/rag/entries.py` — `_voice_samples_text` docstring (~line 50-51): same wording fix.
  - `web/backend/app/schemas/character.py` — `VoiceSample` docstring (~lines 10-17): change "in-voice back-and-forth exchange (several alternating lines, not one sentence)" to describe `sample` as the character's single in-voice response to the situation, specific to that moment rather than a generic voice description.
- **Rationale:** The generation prompt is the actual source of both reported defects (multi-turn dialogue instead of one response; generic voice instead of situation-specific reaction) — everything downstream just stores/renders whatever this prompt produces.
- **Tests:** `utils/tests/backend/services/test_assembler.py::test_voice_samples_rendered_into_cast` and `utils/tests/backend/rag/test_entries.py` already use single-line sample fixtures (`"Coin first, favor later."`) — confirm they still pass unchanged (docstring-only edits, no format change). `utils/tests/backend/agents/test_character_agent.py::test_voice_samples_parses_and_caps` / `test_voice_samples_empty_without_description` / `test_voice_samples_best_effort_on_malformed` — confirm parsing/capping/best-effort untouched by the prompt-text rewrite. `utils/tests/backend/agents/test_character_turn_agent.py` — confirm the HEAD-injection test is unaffected.
- **Action:** Run `.venv/bin/python -m pytest utils/tests/backend/services/test_assembler.py utils/tests/backend/rag/test_entries.py utils/tests/backend/agents/test_character_agent.py utils/tests/backend/agents/test_character_turn_agent.py` + `ruff check` + `mypy` on touched files. Once green, commit: `[Voice Tone Single Response Fix] (1/3) Complete: rewrite voice-sample prompt for single situation-authentic responses + fix renderer/schema docstrings.`

### Phase 2 — Frontend: editor copy back to single-response shape

- **Locations:**
  - `web/frontend/components/feature/VoiceSamplesEditor.tsx` — top doc comment (~lines 8-19): describe the row as situation → a single in-voice response, drop "full back-and-forth exchange" language. Empty-state hint (~lines 40-44, "add one (or Propose) to show a real exchange... how they answer back"): change to describe one response to a past situation. Sample `<textarea>` placeholder (~line 77, "The full back-and-forth — how they reply, and how the exchange continues..."): change to describe a single in-voice reply to the situation above. Textarea `rows` (~line 80, currently `4`): fine to leave at 4 (a single rich response can still run a few lines) — no change needed unless it reads oddly once the placeholder changes.
  - `web/frontend/components/feature/CharacterModal.tsx` — Voice & Tone section description paragraph (~lines 363-368, "Real back-and-forth exchanges showing how this character actually talks..."): change to describe situation → single-response pairs.
- **Rationale:** The editor is also used for hand-authored samples; copy promising "a real exchange" trains authors toward the wrong shape even after the generation prompt is fixed.
- **Tests:** `web/frontend/components/feature/VoiceSamplesEditor.test.tsx` and any `CharacterModal` voice-section tests — confirm they query by `aria-label`, not placeholder/copy text, and pass unaffected. No new test needed for copy-only changes.
- **Action:** Run `npm test -- VoiceSamplesEditor CharacterModal` + `npm run typecheck` + `npm run lint`. Once green, commit: `[Voice Tone Single Response Fix] (2/3) Complete: update Voice & Tone editor copy to single-response shape.`

### Phase 3 — Docs + full validation + merge to main

- **Locations:** `docs/api-contract.md` (the `voiceSamples` shape description + `/characters/voice-samples` endpoint description) — correct "dialogue exchange" wording to "single in-voice response". `docs/data-flow.md` (authoring-flow description) — same correction. `docs/checklist.md` — add a "done" entry under Follow-up Work summarizing this fix and noting it corrects the prior dialogue-depth change, referencing this plan.
- **Rationale:** Global project rules require docs to move with behavior in the same change.
- **Action:** Run the full validation gate — backend `.venv/bin/python -m pytest` (full suite) and frontend `npm test` + `npm run typecheck` + `npm run lint` + `npm run build`. Once green, commit: `[Voice Tone Single Response Fix] (3/3) Complete: docs + full validation; merge single-response voice/tone fix to main.` Merge the worktree branch to `main` (do not push unless asked), resolving any conflicts.

## 4. Deliverables Table

| Deliverable | Description | Location |
| --- | --- | --- |
| Rewritten generation prompt | `_VOICE_SYSTEM` — single situation-authentic response per pair, register varies across pairs | `web/backend/app/agents/character_agent.py` |
| Corrected renderer docstrings | `_format_voice_samples` describes a single response | `web/backend/app/services/assembler.py` |
| Corrected RAG renderer docstring | `_voice_samples_text` describes a single response | `web/backend/app/rag/entries.py` |
| Corrected schema docstring | `VoiceSample` field semantics documented as single response | `web/backend/app/schemas/character.py` |
| Corrected editor copy | Placeholders/description/empty-state matching single-response shape | `web/frontend/components/feature/VoiceSamplesEditor.tsx`, `web/frontend/components/feature/CharacterModal.tsx` |
| Docs | Contract, data-flow, checklist entry | `docs/api-contract.md`, `docs/data-flow.md`, `docs/checklist.md` |
