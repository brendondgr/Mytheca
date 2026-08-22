# Play-Experience Program — index for the five story-player plans

**Status:** index · **Created:** 2026-08-21 · **Owner:** brendondgr

Five plans were authored in parallel against the story player. They are implemented **one at a
time, in the order below**, each fully validated and committed before the next begins. This file
is navigational only — it is not a sixth plan and it contains no phases. The plans themselves are
the specification; where they disagreed, the reconciliation pass edited them and this index records
which one won.

---

## Recommended order

**Status: all five plans complete (58/58 phases), 2026-08-22.** Each plan carries its own
completion record; `docs/plans/reach-acceptance.md` is the composition audit across all of them.

| # | Plan | Phases | Status | Why here |
| --- | --- | --- | --- | --- |
| 1 | [`control-over-the-record.md`](control-over-the-record.md) | 11 | ✅ 11/11 | Owns the `turn_engine.py` split and the history-mutation primitives every later plan builds on |
| 2 | [`steering-the-scene.md`](steering-the-scene.md) | 11 | ✅ 11/11 | Consumes the split, the persisted `guidance` and the relaxed turn validation |
| 3 | [`making-it-legible.md`](making-it-legible.md) | 12 | ✅ 12/12 | Compaction must invalidate against a rewind seam that already exists |
| 4 | [`depth-for-players.md`](depth-for-players.md) | 12 | ✅ 12/12 | Builds presets and pins over a config menu whose contents are settled by #3 |
| 5 | [`reach.md`](reach.md) | 12 | ✅ 12/12 | Mobile/a11y parity for everything the first four added; written to land last |

---

## What each plan delivers

**1 · Control Over the Record.** Gives the player authority over the story record. A scenario stops
having exactly one silently-resumed play-through: a header tray lists, resumes, renames, deletes
and starts them, and lineage columns (`name` / `parentSessionId` / `forkSeq`) make a fork a real
thing. It splits the 1986-line `turn_engine.py` into `turn_emit` / `beat_runner` / `turn_setup`,
then builds `session_state` — truncate, Redis-buffer rebuild, stat replay, Neo4j `:Event` prune,
history copy, turn-boundary resolve, `expectedSeq` guard — and spends it on **branch**, **rewind**
(cutting at a turn boundary and handing the player's own line back to the composer), **edit in
place** (AI beats *and* the player's own), **re-roll** with alternate takes kept inside the event
row behind a pager, scene-image re-roll and delete, a text-less **Continue** turn, and a
**Ghostwriter** that drafts a line into the composer without persisting anything.

**2 · Steering the Scene.** Makes directing the scene first-class and, crucially, diagnoses *why*
targeted requirements get dropped — seven distinct causes, of which the largest is that a
requirement is marked satisfied for being carried into a prompt, before the beat is generated and
regardless of whether it emitted anything. The fix splits `satisfied` into **attempted** and
**delivered**, confirms delivery with a deterministic in-process lexical coverage check (no extra
LLM call), and gives the session a **standing direction** so an undelivered requirement outlives
its turn. Around that: the direction survives a reload, a turn can be pure direction, the direction
row exists from the first frame, `@Mei` keeps the name in the sent text and sets `directedAt`, a
requirement can be pinned to one character and is then never re-owned by the narrator, an absent
cast member can be brought in **only with the player's approval**, and the direction verbs become a
grouped, context-aware, keyboard-operable bar.

**3 · Making It Legible.** Retires "Number of beats" and replaces it with a transcript window that
fits itself to the model's real context budget, block-quantised so prompt-cache anchoring survives,
plus a rolling per-session **compaction** of the history that falls out of it. On top of that
engineering spine: every scene control relabelled by consequence and cost, a player-facing "what
the scene knows" panel and a visible line where verbatim memory ends, a status light driven by
actual model reachability instead of a hardcoded green dot, keyboard fluency with a shortcut sheet,
three anchored coach marks, transcript search, a recap that reuses the compaction agent, and an
editable scene-image prompt. It ends with a pre-registered interleaved two-arm experiment on
whether compaction hurts the writing.

**4 · Depth for Players.** Surfaces machinery that already exists but is unreachable, on the
guardrail that *more customisability is the goal and more sliders are not the way to get it*: a
per-turn override envelope on `TurnRequest` with visible **pins** (this turn vs. this scene), named
**scene presets** instead of loose numbers, a **planner off** switch backed by the deterministic
beat order the fallback already implements (the single largest latency lever in the app), a
player-pinned **register**, a per-character voice **looseness** bias on `top_p` only, the prompt
overrides brought into the scene with per-layer attribution, a three-stop **tie scope** that puts
the Neo4j relationship edges to work, and an honest answer to what stats do between scenes —
including a recoverable authored baseline that today's code destroys.

**5 · Reach.** Mobile, keyboard and assistive-technology parity. A real `Drawer` primitive and a
shared focus trap; each rail split into content + shell so the bottom sheet and the `lg` aside
render the *same* component (which is what makes the other four plans' additions reach mobile for
free); a scene-header overflow menu with an ordered item list sized to hold them; the storyline
switcher un-gated so phones can change worlds; the cramped context rail given room; the repo-wide
`sr-only` root-scroller defect fixed once at the utility and pinned by the offline CSS gate;
self-hosted fonts so `next build` works offline at all; a Core Web Vitals measurement; and a full
line-by-line acceptance pass recorded in `docs/plans/reach-acceptance.md`.

---

## Cross-plan dependency edges

| Depends | On | Why |
| --- | --- | --- |
| Steering P2 (`direction_runtime`) | **Control P3** | Lifts the direction helpers *out of* the module layout Control creates |
| Steering P1, P3 | **Control P1, P9** | Consumes `record_user_turn(guidance=…)` and the relaxed `validate_turn_inputs` |
| Steering P3 | **Control P9** | Extends Control's empty-text branch in `turn_setup`; does not add a second |
| Making It Legible P2–4, P6 | **Control P3** | All later references to the "opening" module mean `turn_setup.py` |
| Making It Legible P4 | **Control P4, P7, P8** | Wires `history_compaction.invalidate_after` into `session_state.truncate_session`, `edit_beat` and `beat_rerun` |
| Making It Legible P8 (ArrowUp) | **Control P7** | The keybinding fires Control's edit action; recall is only the fallback |
| Making It Legible P5 | **Steering P4** | The direction-box copy belongs on `DirectionRow`, not on `Composer` |
| Making It Legible P11 | **Control P8** | Control already closed the scene-image checklist entry; only the additive prompt edit is left |
| Depth P2 | **Control P3, Steering P2** | Verifies the agreed layout; `turn_beats`/`turn_effects` in its later phases mean `beat_runner.py` |
| Depth P4, P5 | **Making It Legible P3, P5** | Pins and presets sit on a config menu whose rows and consequence copy are already settled |
| Reach P3 | **Steering P9** | The rail split must move the cast rail's third section if it exists |
| Reach P4 | **Depth P9** | `SceneMenu.tsx` is *created* by Depth; Reach extends it and adds the narrow/wide split |
| Reach P4 | **Control P2, Making It Legible P7** | Must place the play-through tray and the real model-health indicator |
| Reach P11 | **all four** | The composition audit only means anything once every control exists |

---

## Shared files that need care

| File | Touched by | The care needed |
| --- | --- | --- |
| `web/backend/app/services/turn_engine.py` | all but Reach | **One split, owned by Control P3** → `turn_emit` / `beat_runner` / `turn_setup` (+ `turn_finalize`), then `direction_runtime` (Steering P2). Making It Legible and Depth verify rather than re-split. |
| `web/frontend/features/story-player/useScenePlay.ts` | all five | 604 lines today; every plan adds handlers. **Control P2 owns the split** into a sibling `useSessionRecord.ts` when it would pass 800, keeping the hook's public surface stable. `wc -l` it every phase. |
| `web/frontend/components/feature/SceneConfigMenu.tsx` | Legible P3/P5, Depth P4–P7/P10 | Contents after Legible: Max turns · Suggestions · Beat length · *What the scene remembers*. **No "Number of beats".** Depth adds rows + pins and keeps Legible's copy. 264 px popover inside a composer that must not overflow at 320. |
| `web/frontend/components/layout/SceneHeader.tsx` | Control P2, Legible P7, Depth P9, Reach P4 | Control deletes the fake dot; Legible puts a real four-state indicator in the slot; Depth folds Export + Inspector into `SceneMenu`; **Reach P4 owns the durable 320 px fix and the checklist bullet's removal.** No one else closes that bullet. |
| `web/frontend/components/feature/Composer.tsx` | all five | Steering P4 moves the direction field out to `DirectionRow`; Legible P3 removes the `contextBeats` prop chain; Control P10 adds Ghostwrite; Legible P8 adds `onRecallLast`; Depth P4 adds pin props. The mention menu keeps owning Arrow/Enter/Tab/Escape throughout. |
| `web/backend/app/services/events_store.py` | Control P1, Steering P1/P3, Depth P3 | `record_user_turn` grows keyword-only args (`guidance`, `tagged_doc_ids`, `overrides`) — additive JSON keys, no schema change. `user_turn_stats.preview` is changed twice; Control sets "first non-empty line", Steering adds the `guidance` fallback. |
| `web/backend/app/schemas/play.py` + `web/frontend/lib/events.ts` | all but Reach | `web/shared/contracts/` stays empty; the mirror is hand-maintained and **must change in the same phase** as the envelope. New fields: lineage + takes + `continuation` (Control), `directives` + `cast_request` (Steering), `contextPolicy`/`SceneKnowledge`/`LlmHealth` (Legible), `TurnOverrides` (Depth). |
| `web/backend/app/models/session.py` | Control P1, Steering P8, Legible P4 | Six new columns across three plans, **all additive-nullable** → no Alembic migration; the bootstrap reconciler self-heals. Do not batch them into one phase. |
| `web/backend/app/services/assembler.py` | Legible P3, Steering P9, Depth P3 | Legible removes the 5–100 `context_beats` clamp; Steering unions session-joined guests into `_build_cast`; Depth adds `beat_length_override`. The assembler stays **read-only**. |
| `web/backend/app/memory/buffer.py` | Control P4, Legible P3 | Any history mutation rebuilds the buffer through `session_state`, never patches it. Block anchoring must survive the window becoming dynamic. |
| `docs/checklist.md` | all five | Every plan reconciles it. Remove only what *your* plan closed; expect earlier plans to have taken bullets already; never re-add a bullet in order to narrow it. |
| `docs/research/experiments/` | Legible P12, Reach P10 | Ids are claimed in landing order: Legible takes **EXP-2026-08-011-context-compaction**, Reach takes the next free id (expected **012**). `ls` before scaffolding. |

Best-effort substrates — Redis, Neo4j, Qdrant — must keep degrading to a no-op in every plan. The
full suite runs with none of them and that must stay true.

---

## Decisions taken — 2026-08-21

Three of the questions below were put to the owner before implementation began and are **settled**.
They are recorded verbatim at the top of the Gaps section of every plan they touch.

| # | Question | Ruling |
| --- | --- | --- |
| 1 | Stat lifecycle / session scoping *(Depth §2.2 + Control H-1)* | **(C)** Per-stat `carry_over` flag with **session-scoped stat values**. New `session_character_stats` row set; resolution is session value → carried character value → authored baseline. Rewind replays surviving `state_update` events instead of relying on `StatPatch.fromValue`; branch copies the rows at the fork point. Gets its own phase in Control. |
| 8 | Compaction default *(Legible §G-A)* | **Ship OFF.** `TURN_CONTEXT_COMPACTION` defaults disabled until the interleaved two-arm experiment reports. The flip is one line and must not be made on a read-through. |
| 12 | `sr-only` fix *(Reach §9)* | **Redefine the utility once** — `@utility sr-only { position: fixed }`. No per-file sweep. Pinned by a regression test and the offline CSS gate. |

The remaining questions below stand, each with a default already implemented in its plan. They are
recorded so the choice is visible, not because they block work.

---

## Open questions — "Human intervention is needed to answer this question"

Consolidated across all five plans. Several are the same decision reached from different sides;
those are grouped.

### Stats — one decision, asked twice
1. **What should stats do between scenarios, and should stat values be session-scoped?**
   *(Depth §2.2 + Control H-1.)* `CharacterStat` is global to a character with no session or
   scenario scope, so a branch or a replay silently inherits the last play-through's values, and
   Control's rewind can only reconcile to whichever session is open. Options: **(A)** reset per
   play-through · **(B)** persist globally (today's accidental behaviour, made deliberate) ·
   **(C)** per-stat `carry_over` flag with session-scoped values — Depth's recommendation, and the
   one that also answers Control's H-1 · **(D)** storyline default with a per-scenario opt-out.
   (C) costs a new table and a change to every stat read and write. **Answer these together.**
2. **Should a `hidden`-visibility stat be invisible to the player, or shown as an unnamed
   movement?** *(Depth §2.3.)* (a) omit entirely from player surfaces (implemented) · (b) render
   "something shifted" · (c) delete the field as author-only metadata.

### The record
3. **Retention of rewind snapshots.** *(Control H-2.)* Every rewind forks a snapshot play-through.
   Keep all (implemented, badged and sorted last) · keep last N · hide behind a History disclosure ·
   make the snapshot opt-in per rewind.
4. **How many alternate takes to keep, and do they survive export?** *(Control H-3.)* Capped at 5
   with the oldest dropped; Markdown export shows only the active take, JSON shows all. Should a
   reader see the roads not taken, and should takes count toward the model's context?

### Direction
5. **Should the composer render a resolved mention as an inline chip inside the text?**
   *(Steering §2.1.)* Both routes are real work — an overlay mirror (~150 lines, drifts under zoom)
   or `contenteditable` (rewrites every key path and the whole co-located test suite). Neither is
   built; the below-the-box chip list ships instead.
6. **What happens to a carried-over requirement the player never dismisses?** *(Steering §2.2.)*
   Kept until dismissed and capped at `MAX_REQUIREMENTS` (implemented) · expire after N turns ·
   expire on a scene change. "Forever" is a product call.
7. **Should an unconfirmed delivery be a distinct third state in the UI?** *(Steering §2.3.)*
   Three states are honest but expose the heuristic's uncertainty, and a false negative reads as
   the app doubting prose the player just watched land.

### Context and compaction
8. **Does `TURN_CONTEXT_COMPACTION` ship on by default before the experiment reports?**
   *(Legible §G-A.)* Compaction changes what the model reads — a writing-quality change. The plan
   is written so either default is a one-line change; Phase 12 builds the interleaved two-arm study
   that would settle it.
9. **Is the scene's rolling summary the player's to edit?** *(Legible §G-B.)* Read-only is
   unambiguous; editable is the most powerful authoring control in the app and also a way to
   rewrite established history that no export or trace would explain.

### Scope and graph
10. **Should off-scene relationship ties be offered to the model, and ever be the default?**
    *(Depth §2.1.)* The *World* tie stop is real, populated graph data, but a character can then
    reference someone the scene never introduced, which reads as hallucination. (a) three stops,
    *Scene* default, *World* opt-in (the recommendation) · (b) ship only Addressed/Scene ·
    (c) *World* as the default.

### Mobile and accessibility
11. **How is the Core Web Vitals number actually captured?** *(Reach §8.)* (a) check in
    `puppeteer`/`playwright` + `lighthouse` as devDependencies — reproducible, ~300 MB of browser
    binaries in a repo with 5 runtime deps · (b) a flag-gated `web-vitals` probe plus a documented
    manual DevTools procedure — a real number, not reproducible by a command.
12. **Should the `sr-only` fix redefine the utility, or be a 17-file per-site sweep?**
    *(Reach §9.)* The plan proceeds with `@utility sr-only { position: fixed }` — one line, fixes
    23 call sites and every future one — with the sweep written in as the fallback. Confirm the
    preference before Phase 7, since it is a repo-wide change to a utility every screen-reader
    affordance depends on.
13. **The WCAG 2.5.8 24×24 floor is not met by `TriagePanel`'s `py-[2px]` `DocRow` chips.**
    *(Reach §10.)* Growing them changes the density `docs/design-system.md` explicitly specifies
    ("rails are small and quiet"). Grow · add spacing · claim the 2.5.8 spacing exception.

---

## Also unowned

No plan in this program owns **graph mode below `lg`** — making `GraphInspectorPanel` a drawer and
widening node-click coverage past Character. Depth's graph work is entirely backend-side. It stays
open in `docs/checklist.md`; Reach Phase 12 restates it rather than assigning it.
