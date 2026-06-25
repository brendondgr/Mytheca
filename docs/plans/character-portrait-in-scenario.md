# Character Portrait in Scenario Areas

## 1. Introduction

When a character has a generated portrait WebP, their avatar in the Library's
Scenario column (ScenarioCard) and the hero Scenario Carousel (ScenarioCarousel)
currently shows only an initials-monogram ring. This plan wires the portrait
into those two locations so the cast strip reflects the same portrait already
shown on CharacterCard and the character profile modal.

The data is fully available: `ResolvedScenario.cast` is an array of full
`Character` objects, each carrying the optional `portrait` field
(`"/media/<uuid>.webp"`). The `mediaUrl()` helper in `lib/api.ts` converts that
relative path to an absolute URL. The `Monogram` component already accepts an
optional `src` prop and falls back to the initials-ring when `src` is absent.
No backend changes are needed — this is a pure frontend wiring task.

---

## 2. Gaps & Unanswered Questions

- **Portrait `alt` text:** `Monogram` renders an `<img>` when `src` is provided;
  the component uses the `mono` initials as the alt label. This is consistent
  with existing usage in `CharacterCard` — no change needed.
- **Size:** ScenarioCard uses 27 px; ScenarioCarousel uses 34 px. Both are
  fine — `Monogram` is square/circular at any size.

No complex gaps — all assumptions are straightforward.

---

## 3. Phases

### Phase 1 — ScenarioCard: add portrait to cast Monograms

**Location:** `web/frontend/components/feature/ScenarioCard.tsx`

1. Import `mediaUrl` from `@/lib/api` (already imported in `CharacterCard`;
   pattern is established).
2. In the `s.cast.map(...)` block (lines 70–85), add
   `src={c.portrait ? mediaUrl(c.portrait) : undefined}` to both `<Monogram>`
   instances (the `<button>`-wrapped one and the bare fallback).

No other files touch this change.

**Validation & Commit:**
> Run `npm test` (typecheck + lint + vitest) from `web/frontend/`. Once green,
> commit:
> `[Character Portrait in Scenario] (1/2) Complete: ScenarioCard cast Monograms now show portrait when available.`

---

### Phase 2 — ScenarioCarousel: add portrait to cast Monograms

**Location:** `web/frontend/components/feature/ScenarioCarousel.tsx`

1. Import `mediaUrl` from `@/lib/api`.
2. In the `s.cast.map(...)` block (lines 113–128), add
   `src={c.portrait ? mediaUrl(c.portrait) : undefined}` to both `<Monogram>`
   instances (button-wrapped and bare fallback).

No other files touch this change.

**Validation & Commit:**
> Run `npm test` (typecheck + lint + vitest) from `web/frontend/`. Once green,
> commit:
> `[Character Portrait in Scenario] (2/2) Complete: ScenarioCarousel cast Monograms now show portrait when available.`

---

## 4. Deliverables

| Deliverable | Description | Location |
|---|---|---|
| ScenarioCard portrait wiring | `src` prop on cast Monograms | `web/frontend/components/feature/ScenarioCard.tsx` |
| ScenarioCarousel portrait wiring | `src` prop on cast Monograms | `web/frontend/components/feature/ScenarioCarousel.tsx` |
| Tests (existing suite) | typecheck + vitest confirm no regressions | `web/frontend/**/*.test.tsx` |
