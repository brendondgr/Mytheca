# Briefing: Multi-Character Roleplay Chat Engine

**Prepared from:** design conversation, 6/20/2026 (revised 6/21/2026)
**Subject:** Architecture and data-structure decisions for a multi-character roleplay chat app with a narrator and an agentic backend. Built around storylines, characters, settings, and scenarios — with a near-term **character stat system** (bounded, guided numeric values that shape story outcomes), and full dice-based resolution treated as an optional later layer.

---

## 1. Product concept

An app for creating characters that converse with one another while roleplaying inside a living world. The user directs how the conversation flows and can also play as a character. A persistent **narrator** describes the situation and environment alongside character dialogue, so the central chat reads like a scene rather than a flat message thread.

The UI is a 16:9 layout with a central narration/dialogue feed and supporting side panels (characters, storyline, settings, stats, branch choices, turn order, goals, emotional tone, relationships).

---

## 2. Core concepts and vocabulary

Four objects define the world. Everything else hangs off these.

- **Storyline** — the overarching story and world setting. This is the big container: the genre, the atmosphere, the history, the ongoing situations, and the persistent truth about the world. A storyline holds all of the characters, settings, and scenarios that belong to it, and it defines the baseline **stat schema** for the world. When you ask "what is this world and what is going on in it," the answer lives here.
- **Character** — a person involved in the storyline. Descriptive (who they are, how they speak and behave, what they want, what they're hiding, how they relate to others) and now also **numeric**: each character carries values for the world's stats (health, strength, and so on).
- **Setting** — a place within the storyline where situations and events happen. Settings are tracked over time so the world stays consistent (who's there, what state the place is in, time and weather, notable features).
- **Scenario** — a specific situation currently playing out within the storyline, acted out by the characters. Scenarios are dynamic and constantly changing; many of them happen over the life of a storyline. A scenario is the live "truth object" for the present moment — it's what the model generates *from* and what events *update*. A scenario can also add or tighten stats for its particular situation.

The relationship, in one line:

```
Storyline (the world, owns the baseline stat schema)
 ├── Characters (the people, each holding stat values)
 ├── Settings (the places)
 └── Scenarios (the situations being acted out — many, ever-changing,
                may add their own stats)
```

> **Note on the vocabulary change.** An earlier draft used "scenario" for the static world setup and "scene state" for the live moment. Those roles have been renamed and split: the static world is now the **Storyline**, places are pulled out into their own **Setting** concept, and **Scenario** now means the active, changing situation.

---

## 3. Core architectural principle

**The AI generates validated story events; the UI renders them. The AI never decides UI layout.**

The model emits small, typed events (one unit of story progress each), the backend validates them, and the frontend maps each event type to a visual component. This keeps the frontend "dumb" and the agent framework "smart," and avoids the model returning one large blob of prose.

```
User Input → Orchestrator → Scenario State → Character/Narrator Agents
→ Structured Event Output → Validator → Event Stream → Frontend Renderer
```

---

## 4. Format decisions

| Concern | Recommendation | Reason |
|---|---|---|
| Static config (storyline, characters, settings, stat definitions) | **YAML** | Readable for hand-authored config |
| Stat guidance | **Markdown** | One human-readable file per stat, injected into agent context |
| Live story streaming | **JSON / NDJSON** | YAML is fragile under partial streaming and multiline content; NDJSON gives one valid object per line |
| Validation | **JSON Schema or Zod** | Enables a parse → validate → repair/retry loop, and enforces stat ranges, before anything reaches the UI |

Pipeline: `AI output → parse → validate (incl. stat clamping) → repair/retry if invalid → stream to UI`

---

## 5. Key data structures

The system revolves around the four canonical objects plus the event abstraction:

- **Storyline** — title, genre, world setting, atmosphere/tone, history, ongoing world situations, persistent world flags, and the **baseline stat definitions** (see Section 9). The container that owns its characters, settings, and scenarios.
- **Character** — id, display name, role, avatar, accent color, personality (traits, speech style, tone), goals, secrets, relationship values, and a **stat block** (current values for each applicable stat, always within range). Belongs to a storyline.
- **Setting** — id, name, description, atmosphere, time/weather, who or what is present, notable features, current state. Belongs to a storyline; a scenario points at the setting it takes place in.
- **Scenario** — the live truth object for the current situation: which storyline it belongs to, which setting it's in, active characters, turn order, current turn index, goals with status, tone (primary + intensity), the world flags in play right now, and any **scenario-specific stat additions or range overrides**. The model generates *from* this state and emits events that *update* it.
- **Story Event** — the central abstraction. Every visible thing in the chat is an event with a base shape (`event_id`, `scenario_id`, `type`, `sequence`, `visibility`) plus type-specific fields.

---

## 6. Event types (minimal set to start)

Start with **five** event types, not thirty:

| Event type | UI rendering |
|---|---|
| `narration` | Teal narrator card |
| `character_dialogue` | Character chat bubble (uses speaker's avatar/color) |
| `character_action` | Action/emote card |
| `state_update` | Updates side panels (does not render as a chat message) |
| `branch_choices` | Updates branch-choices panel |

**Stat changes** ride on `state_update` to begin with: the payload names the character, the stat key, the new value (or delta), and a short reason, and the Stats panel re-renders. When you want bespoke rendering — an animating bar, a floating "+5 / −10" — promote it to a dedicated `stat_update` event later. Either way the data shape is the same.

Additional types to layer in later: `internal_thought` (with visibility controls), `relationship_update`, `goal_update`, `turn_update`.

**Visibility flags** matter: `public`, `private_to_user`, `private_to_character`, `hidden` — some content is shown to the player, some only affects agent reasoning. Stats can use these too (a hidden "suspicion" value the player can't see).

---

## 7. Streaming approach

Use **NDJSON** (one JSON object per line). Two streaming modes:

- **Option A — full events:** send only complete events. Easy to validate and render; less "live typing" feel. **Use for state and stat updates.**
- **Option B — delta streaming:** `message_start` → repeated `message_delta` → `message_end`. Feels like live AI typing but needs buffering and is harder to validate mid-stream. **Use for visible messages.**

The frontend renders a message as deltas arrive, then finalizes it on `message_end`.

---

## 8. Suggested agent roles

A multi-agent split rather than one monolithic model:

1. **Orchestrator / Director agent** — decides what happens next, who speaks next, whether narration is needed, pacing, transitions between scenarios, and **what stat changes a turn's events imply** (reading each stat's guidance).
2. **Narrator agent** — turns resolved events into descriptive prose, and reflects stat states in the world (a wounded character moves stiffly).
3. **Character agents** — each carries personality, goals, memory, relationships, secrets, emotional state, and **its own stat values, which color behavior**.
4. **State manager** — canonical source of truth for the storyline, characters, settings, the active scenario, and all stat values.
5. **Validator** — rejects invalid event types, unknown character IDs, malformed JSON, impossible state changes, unauthorized knowledge leaks, and **stat changes that reference undefined stats or fall outside the defined range** (it clamps rather than crashes).

An explicit **agent output contract** instructs the model to emit only valid structured events — every spoken line as `character_dialogue`, every description as `narration`, every movement as `character_action`, every world or stat change as `state_update`, and to never invent character/setting IDs or stat keys.

---

## 9. Character stats and tracked values

This is the new near-term feature. A **stat** is a bounded numeric value attached to a character that the AI reads and updates as the story unfolds. Stats give the world continuity and consequence: they shape what outcomes are plausible and how the agents respond going forward. Health, strength, and the like are stats — and so are softer tracked values like trust or morale. They are all the same kind of object, so you build the system once.

### 9.1 What a stat definition contains

```yaml
stat:
  key: health                    # stable id used in events
  display_name: Health
  description: Physical condition and vitality.
  min: 0                         # locked at creation
  max: 100                       # locked at creation
  default: 100                   # starting value for a new character
  guidance: ./stats/health.md    # the markdown instruction file (Section 9.4)
  visibility: public             # public | private_to_user | hidden
  applies_to: [character]        # extensible to relationships/settings later
```

A character then just holds values:

```yaml
character:
  id: kira
  display_name: Kira
  stats:
    health: 80
    strength: 14
```

### 9.2 Where stats are defined

- **Storyline** defines the **baseline stat schema** — the canonical set of stats for the whole world, with their ranges. This is where most stats live.
- **Scenarios** may **add scenario-specific stats** (a survival scene introduces `hunger`) or **tighten/override a range** for the situation (a duel caps `stamina` lower). Scenario definitions take precedence over the storyline baseline while that scenario is active.
- **Characters** hold a value for each applicable stat, always clamped to the active range.

### 9.3 The range (min / max)

The range and starting value are **set when the storyline or scenario is created**, exactly as you described. They are not suggestions to the model — the **validator enforces them**: every incoming stat change is clamped to `[min, max]`, so the AI can never push a value out of bounds, no matter what it emits. This is what makes the numbers trustworthy.

### 9.4 Guidance files (the AI's instructions per stat)

Each stat has a **markdown guidance file** that tells the agents how to interpret and adjust it. The relevant guidance files are injected into the Director/character/narrator context for the turn, so the model knows *when* a stat should move, *by how much*, and *what it means* at different levels. A suggested template:

```markdown
# Health

## What it represents
A character's physical condition and vitality. 0 = incapacitated, 100 = peak.

## What lowers it
Physical harm, exhaustion, illness, environmental damage.
Typical magnitudes:
- Minor injury (a graze, a hard fall): 5–15
- Serious injury (a deep wound, a bad fall): 20–40
- Grievous / life-threatening: 40+

## What raises it
Rest, medical care, healing items, the passage of safe time.
- Short rest / first aid: 5–15
- Full recovery / strong remedy: 30+

## Bands and their meaning
- 75–100  Healthy. No narrative penalty.
- 40–74   Hurt. Visible discomfort; the narrator should show it.
- 15–39   Critical. Actions are impaired; risky choices are dangerous.
- 1–14    Near death. Barely functional; should dominate the character's behavior.
- 0       Incapacitated. Cannot act until healed above 0.

## Behavioral guidance
Character agents at low health act cautiously, may panic, may seek help.
The narrator should reflect current health in description every few turns.
```

The structure that matters across every stat: **what raises it, what lowers it, magnitude guidance, the meaningful thresholds, and how each band should affect behavior and narration.** That is what turns a raw number into something the AI can steer by.

### 9.5 How a stat change flows through the system

```
Director/character agent proposes a change (stat key, delta or value, reason)
  → emitted as a state_update event
  → Validator confirms the stat exists and clamps the result to [min, max]
  → event streamed to the UI
  → Stats panel updates; narrator may reference the new state next turn
```

Because the change carries a **reason**, you get a free audit trail ("Health −25: struck by the falling beam") that's useful for debugging the model and for showing the player *why* a number moved.

### 9.6 How stats feed back into the story

Current stat values plus their guidance files go into the agents' context each turn. The Director uses them to judge what outcomes are plausible; character agents let their own stats color how they speak and act; the narrator reflects them in description. This is the loop that makes stats *matter* rather than just decorate — a near-dead character fights weakly and looks for an exit, a high-strength character can plausibly force a door, and so on.

### 9.7 Relationship and mood values are just stats

The persistent values worth tracking for social play — trust, suspicion, patience, fear, affection, influence, morale — are the same object with a relational target (character-to-character or character-to-player). Building the stat system gives you these for free; they just carry their own guidance files describing what shifts them.

---

## 10. Layered design summary

```
Narrative layer  → dialogue, narration, actions, tone, character behavior
Stat layer       → bounded character/relationship values, ranges, guidance,
                   stat updates with reasons
State layer      → storyline, characters, settings, active scenario,
                   known/hidden facts, world flags
Rendering layer  → chat bubbles, narrator cards, stats panel, turn order,
                   branch choices, panels
(optional) Rules → dice-based resolution of how much a stat changes
```

---

## 11. Optional later layer: dice-based resolution

With stats now part of the core, the thing that remains genuinely optional is **how uncertain outcomes get resolved.** Two approaches, and you can ship the first and add the second only if you want it:

- **Narrative resolution (default, in scope now):** the Director decides the outcome and the resulting stat change directly, guided by the stat files. Simple, flexible, no dice.
- **Dice-based resolution (optional, later):** uncertain actions resolve with a roll-and-threshold pattern (`check_request` → `roll_result` → `consequence` → `state_update`) against a few difficulty tiers, and the roll determines how much a stat moves. This layers cleanly on top of the stat system — the stats and ranges are already there; dice just become the function that decides the delta.

**Recommendation:** start with narrative resolution. The stat system delivers persistent consequences on its own; add dice only if you want the outcomes to feel chancier and more game-like.

---

## 12. Recommended build order

1. Lock the **four core objects** (Storyline, Character, Setting, Scenario) and the **five-event** schema.
2. Stand up the **NDJSON stream** with full-event mode, plus a validator.
3. Add **delta streaming** for visible messages once full-event flow works.
4. Introduce the **orchestrator + narrator + character** agents against the canonical state.
5. Build the **stat system**: stat definitions with ranges on the storyline, per-character values, validator clamping, the Stats panel, and `state_update`-carried stat changes.
6. Author **guidance files** for the first handful of stats and wire them into agent context, so the AI adjusts stats sensibly.
7. Extend stats to **relationship/mood values** (same machinery, relational target).
8. Only if desired, add **dice-based resolution** (Section 11) — last, and incrementally.
9. Expand event types and rules over time — avoid front-loading complexity.

---

## Open questions / decisions to confirm

- Persistence backend for the canonical state (fits an existing Django/Postgres + Redis stack well — structured storyline/character/setting/stat data in Postgres, live scenario checkpointing in Redis).
- Transport: NDJSON over fetch streaming vs. Server-Sent Events.
- How much character and setting "memory" persists across scenarios, and where it lives.
- Whether the user-as-character path reuses the character-agent contract or bypasses it.
- How a scenario transitions to the next one within a storyline, and what carries over when it does.
- **Stat lifecycle:** do stat values reset, persist, or partially carry over between scenarios in the same storyline?
- **Hidden stats:** which stats (e.g., suspicion) are hidden from the player, and how the UI handles a stat the player isn't allowed to see.
- **Drift over time:** should some values decay or regenerate on their own (health recovering, patience cooling) versus only changing in response to events?
