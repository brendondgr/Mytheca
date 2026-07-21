# Auto-Propose Starting Stats on Draft with Mytheca

## 1. Introduction

When a user clicks "❖ Draft with Mytheca" in the Character Creator, the backend `draft_character()` agent fills in the character's base-identity fields (name, role, traits, appearance, background, personality, speech, goal, secret, color). However, starting-stat proposals are a separate, explicit action — the user must click a second "❖ Propose" button in the Starting Stats section. This means every agentic character creation requires two separate LLM round-trips that the user must initiate manually, even though all the information needed for stat proposals (character fields + storyline stat schema) is already available after the first call.

The fix is entirely frontend-side: after `draftCharacter()` completes successfully in `useLibraryState.ts`, automatically chain a `proposeStartingStats()` call using the newly drafted fields. The backend is unchanged (both endpoints already exist and work independently). The auto-proposal is best-effort — if no stats are defined for the storyline, or if the proposal call fails, the draft still succeeds and the Starting Stats section remains empty. One phase covers the hook change, UI indicator, and test updates; it ends with a commit.

---

## 2. Gaps & Unanswered Questions

- **Should the user be able to tell stats were auto-proposed vs. manually proposed?** No distinction needed — the UI already shows the proposals the same way regardless of trigger. The "❖ Redo" button remains available for re-proposing. *(Assumption: treat it as identical to a manual propose.)*
- **If stat proposal fails mid-draft, should the error surface?** No — silent degradation. The draft succeeds; the Starting Stats section stays empty with the normal "No stats proposed yet" message. *(Assumption: errors in the chained propose call are swallowed, not re-thrown.)*
- **What if the user clicks "❖ Draft with Mytheca" a second time on a character that already has proposed stats?** The second draft will re-propose stats, overwriting the prior proposals — same behaviour as clicking "❖ Redo" manually. *(Assumption: acceptable; no special guard needed.)*

---

## 3. Hierarchical Step-by-Step Instructions

### Phase 1 — Chain stat proposal in `draftCharacter()` + update tests (Frontend only)

This is a **single-phase** plan. The backend is untouched. All work is in the frontend hook and its tests.

---

#### Step 1.1 — Read the current `draftCharacter()` implementation

- **Location:** `web/frontend/features/library/useLibraryState.ts` (~lines 247–279)
- **Rationale:** Confirm the exact shape of the drafted fields returned by `api.draftCharacter()` so the chained `proposeStartingStats()` call receives the correct arguments (name, role, traits, personality, background).
- **Also read:** `web/frontend/features/library/useLibraryState.ts` `proposeStartingStats()` (~lines 324–343) to see the exact call signature used when it runs manually, so the chained call matches exactly.

---

#### Step 1.2 — Modify `draftCharacter()` in `useLibraryState.ts`

- **Location:** `web/frontend/features/library/useLibraryState.ts`
- **Change:** After the existing draft merge block (where `setDraft(...)` is called with the response fields), add a chained `proposeStartingStats()` call using the **response fields** (not the pre-existing draft state, which may be stale):

  ```
  After setDraft(draft → { ...draftedFields, _ai: true }):
    try {
      await proposeStartingStats({
        using drafted name, role, traits, personality, background
        (pass these directly from the draft response, not from state)
      });
    } catch {
      // silent — draft already succeeded
    }
  ```

- **Important:** `generatingStats` is already the spinner flag for `proposeStartingStats()`. Since we're calling `proposeStartingStats()` (the existing hook method), the spinner state will be set/cleared automatically — the Starting Stats section in the modal will show a loading state while stats are being proposed.
- **Alternative approach (simpler and avoids duplication):** Instead of duplicating the API call, just call `this.proposeStartingStats()` (or the equivalent inner call) using the drafted fields directly. Check whether `proposeStartingStats()` reads fields from `draft` state or accepts parameters — if it reads from state, the `setDraft()` call must complete before invoking it. Since React state updates are batched, use the drafted fields directly from the response rather than relying on state.
- **Rationale:** A single click on "❖ Draft with Mytheca" now produces both a complete character identity and a ready-to-review stat proposal, fulfilling the user request.

---

#### Step 1.3 — Verify `CharacterModal.tsx` requires no changes

- **Location:** `web/frontend/components/feature/CharacterModal.tsx` (~lines 309–377)
- **Rationale:** The Starting Stats section already renders a loading spinner when `lib.generatingStats` is true, and already renders the proposals when `draft._startingStats` is populated. Since the auto-proposal flows through the same `proposeStartingStats()` method with the same state flags, no UI changes should be needed.
- **Confirm:** Read lines 309–377 of `CharacterModal.tsx` to verify the `generatingStats` spinner covers the auto-proposal window and the "❖ Propose" / "❖ Redo" button still renders correctly once proposals arrive.

---

#### Step 1.4 — Update `useLibraryState.character.test.ts`

- **Location:** `web/frontend/features/library/useLibraryState.character.test.ts`
- **Changes needed:**
  1. Find the existing test(s) for `draftCharacter()`. They will be mocking `api.draftCharacter` but likely NOT mocking `api.proposeStartingStats`. Add a mock for `api.proposeStartingStats` that returns a sample proposals array.
  2. Add a new assertion: after `draftCharacter()` resolves, `draft._startingStats` should be populated with the proposals returned by the mocked `proposeStartingStats`.
  3. Add a test for the **error case**: if `api.proposeStartingStats` rejects, `draftCharacter()` still succeeds and `draft._startingStats` remains undefined/empty (graceful degradation).
  4. Check whether there are tests that assert `draft._startingStats` is NOT set after `draftCharacter()` — update those to expect it IS set (or to be flexible about it).

---

#### Step 1.5 — Update `CharacterModal.test.tsx` if needed

- **Location:** `web/frontend/features/library/CharacterModal.test.tsx` (or co-located test file)
- **Changes needed:** If any test mocks the `useLibraryState` hook's `draftCharacter` to set up state and then asserts the Starting Stats section is empty immediately after a draft, those tests need updating. In practice, since `CharacterModal` tests likely mock the hook's state directly (not the internal flow), changes may be minimal. Read the test file to confirm.

---

#### Step 1.6 — Run validation and commit

- **Backend validation:** `uv run pytest` — backend is unchanged, but run to confirm nothing broke.
- **Frontend validation:**
  - `npm test` (from `web/frontend/`) — all tests must pass, including the updated/new `draftCharacter` tests.
  - `npm run typecheck` — no TypeScript errors.
  - `npm run lint` — no ESLint errors.
- **Accessibility/responsive:** No new interactive surfaces were added (the stats section and its loading spinner already existed); the auto-proposal flows through the existing UI. Deferred in-browser pass applies (same standing constraint: shared dev server on 3346).
- **Action:** Once all checks are green, commit locally:
  > `[Draft with Mytheca Auto-Stats] (1/1) Complete: draftCharacter() now auto-proposes starting stats after a successful character draft.`

---

## 4. Deliverables Table

| Deliverable | Description | Location |
|---|---|---|
| `useLibraryState.ts` change | `draftCharacter()` chains `proposeStartingStats()` after a successful draft | `web/frontend/features/library/useLibraryState.ts` |
| Updated hook tests | `draftCharacter` tests mock + assert auto-proposal; error-case graceful degradation test | `web/frontend/features/library/useLibraryState.character.test.ts` |
| Modal test review | Confirm/update `CharacterModal.test.tsx` if any assertion contradicts the new behavior | `web/frontend/features/library/CharacterModal.test.tsx` (or co-located) |

> **No backend changes.** `POST /characters/draft` and `POST /characters/starting-stats` are unchanged.
> **No new dependencies.**
> **No schema changes.**
