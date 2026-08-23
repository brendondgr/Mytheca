# Experiment Index

<!-- GENERATED FILE — do not hand-edit. Regenerate with `make research-index`. -->

Every experiment on record. `make validate-research` fails if this file is stale.

| ID | Started | Title | Status | Primary metric | Claims | Link |
|----|---------|-------|--------|----------------|--------|------|
| EXP-2026-08-001 | 2026-08-06 | ReAct per-beat planner vs. the one-shot speaker-set director | `failed` | — | C-005 | [EXP-2026-08-001-planner-vs-oneshot-director](experiments/EXP-2026-08-001-planner-vs-oneshot-director/) |
| EXP-2026-08-002 | 2026-08-11 | Do in-narrative moment prompts describe the cast by appearance rather than by name? | `complete` | name_leak = 0 ± 0 (n=3) | — | [EXP-2026-08-002-moment-prompt-style](experiments/EXP-2026-08-002-moment-prompt-style/) |
| EXP-2026-08-003 | 2026-08-19 | Where a turn's latency actually goes — capping reasoning vs. streaming the transport | `complete` | streaming-capped.ttft_s = 10.5904 ± 3.56282 (n=5) | C-008 | [EXP-2026-08-003-live-turn-visibility](experiments/EXP-2026-08-003-live-turn-visibility/) |
| EXP-2026-08-004 | 2026-08-19 | What the deployed model actually gives the player — the same code on skynet | `complete` | streaming-capped.ttft_s = 4.20733 ± 1.3376 (n=3) | C-008 | [EXP-2026-08-004-deployed-model-visibility](experiments/EXP-2026-08-004-deployed-model-visibility/) |
| EXP-2026-08-005 | 2026-08-20 | Where a conversation's latency goes, and why the prompt cache stops helping | `complete` | cached_tokens.every_turn = 800 ± 0 (n=9) | C-009 | [EXP-2026-08-005-conversation-scaling](experiments/EXP-2026-08-005-conversation-scaling/) |
| EXP-2026-08-006 | 2026-08-20 | Turn latency after the overhaul — the prompt cache is reclaimed; wall-clock is not measurable on this endpoint | `complete` | reusable_prefix_ratio = 0.7324 ± 0.2509 (n=10) | C-009 | [EXP-2026-08-006-turn-latency-overhaul](experiments/EXP-2026-08-006-turn-latency-overhaul/) |
| EXP-2026-08-007 | 2026-08-21 | In-voice frequency/presence penalties destroy sentence structure in character prose | `complete` | off.sentences_per_100_words = 11.4157 ± 3.95622 (n=10) | C-012 | [EXP-2026-08-007-prose-form](experiments/EXP-2026-08-007-prose-form/) |
| EXP-2026-08-008 | 2026-08-21 | The prose form end to end — does a live turn read like a scene, and at what cost in discarded beats? | `complete` | has_speech = 1 ± 0 (n=18) | — | [EXP-2026-08-008-prose-end-to-end](experiments/EXP-2026-08-008-prose-end-to-end/) |
| EXP-2026-08-009 | 2026-08-21 | Second person instead of a label — does relabelling the player's line stop characters calling them "the player"? | `complete` | names_the_player = 0 ± 0 (n=19) | — | [EXP-2026-08-009-prose-second-person](experiments/EXP-2026-08-009-prose-second-person/) |
| EXP-2026-08-010 | 2026-08-21 | Short/Medium/Long beat length — a paragraph count binds where a word count did not | `complete` | short.paragraph_breaks = 1.6 ± 1.74356 (n=20) | — | [EXP-2026-08-010-beat-length](experiments/EXP-2026-08-010-beat-length/) |
| EXP-2026-08-011 | 2026-08-22 | Does compacting dropped history preserve continuity, and what does it cost? | `complete` | B.continuity_hits = 0 (n=1) | — | [EXP-2026-08-011-context-compaction](experiments/EXP-2026-08-011-context-compaction/) |
| EXP-2026-08-012 | 2026-08-22 | Core Web Vitals on the first production bundle this repository has ever built | `complete` | story_player.INP = 440 ± 7.1554 (n=5) | — | [EXP-2026-08-012-core-web-vitals](experiments/EXP-2026-08-012-core-web-vitals/) |
| EXP-2026-08-013 | 2026-08-22 | Three art styles emit the LoRA state and tag set they intend, on every image surface | `complete` | no_foreign_tags = 6 ± 0 (n=6) | — | [EXP-2026-08-013-art-style-presets](experiments/EXP-2026-08-013-art-style-presets/) |
| EXP-2026-08-014 | 2026-08-22 | Record controls — what a rewind forgets, and what a re-roll sees | `complete` | rewind_interior_keys_after__baseline = 3 (n=1) | C-014 | [EXP-2026-08-014-record-controls](experiments/EXP-2026-08-014-record-controls/) |
