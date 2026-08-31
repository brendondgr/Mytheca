# Mytheca — Website Audit (baseline)

**Audited:** 2026-08-31 · commit `96a09bf` (identical to `main`)
**Against:** `docs/audit/audit-profile.yaml`
**Method:** the `website-audit` protocol, stages 0–11. Evidence is the rendered page, not the source.
**Instruments:** `audit_a11y.py` (axe-core 4.x via Playwright, `--all --standard wcag22aa`), `audit_responsive.py`
(viewport matrix V1–V8, `isMobile+hasTouch`), `audit_motion.py` (4× CPU throttle, LoAF), `audit_seo.py`,
`check_headers.py`. Raw JSON retained alongside this report.

**Sample (7 routes, all templates):** `/` · `/embergate` · `/embergate/salt` (story player) ·
`/options` · `/storylines/new` · `/storylines/embergate/edit` · `/storylines/embergate/documents`.

## What this audit cannot tell you

Stated up front, per the protocol — an audit that overclaims is worse than one that is narrow and honest.

- Automated accessibility testing reaches **~30–40 %** of WCAG issues. axe's silence is not a pass.
  38 elements on `/` alone landed in axe's `incomplete` bucket — detected, undecidable without a human.
- There is **no field data** (`seo.data_access: []`). Every performance number here is **lab-only**.
- Motion was measured **headless**; headless under-reports jank. The long-frame counts are directional.
- Of the six criteria new in WCAG 2.2, only 2.5.8 Target Size is reliably automatable. One of six was machine-checked.
- Contrast was measured in the **rendered theme state**. Findings name their theme; the two dark themes
  and the light theme are three separate renderings and were not all swept exhaustively.

---

## 1. The headline

The site is **structurally sound and visually unstructured**. There is no horizontal overflow at any
viewport, no `100vh` misuse, no scroll-jacking, no dead `div onclick`, and the motion that exists is
cheap. What is missing is a **shared scale**. Measured over 136 component files:

| Measure | Count | What a system would have |
| --- | --- | --- |
| Arbitrary font sizes (`text-[Npx]`) | **625 uses, 30 distinct values** | one scale, 6–8 steps |
| Arbitrary spacing (`p-/m-/gap-[Npx]`) | **1,335 uses, 165 distinct values** | one scale, ~10 steps |
| Arbitrary border radii | 8 distinct values | 3–4 |
| Raw hex colours in components | 100+ uses (`#F6ECDA` ×31, `#8E2B1C` ×22, `#A8762A` ×19, …) | zero |
| Files using the existing type tokens | **29 of 136** | all of them |

This is the mechanism behind "everything is made to look good for what it is, but it still feels
unpolished." Each component was tuned to look right *in isolation*, so nothing aligns *across*
components. A 13px label beside a 12.5px label beside an 11px label reads as noise even when each was
a reasonable choice on its own. The token system in `styles/themes.css` is well built — a fluid
`--gutter`, a six-step `--fs-*` scale, four user-facing text-size presets — and the app **bypasses it**.

Two consequences fall straight out of that, and they are the two the owner named:

1. **Mobile fails on type size, not on layout.** 776 form-control auto-zoom failures and 184
   text-size findings, all traceable to the same arbitrary-pixel habit.
2. **There is no page frame.** `AppShell` contributes no max-width, no gutter, no vertical rhythm and
   no `<main>`; all 8 routes invent their own container independently.

---

## 2. Findings

Severity is consequence, not effort. `compliance.regime: none`, so WCAG failures are **not** escalated
to blocker on legal grounds — the blockers below are blockers on their own merits.

### BLOCKER

**B-1 · Content is lost at 320 CSS px on 4 of 7 routes** — WCAG 2.2 SC 1.4.10 (Reflow, AA)
Text visible at 1280px is *absent* at 320px. This is information loss, not reflow.
`/storylines/embergate/documents` loses `"Embergate · Documents"`; `/storylines/embergate/edit` and
`/storylines/new` lose `"Uncategorized"`; `/embergate/salt` loses `"Play-throughs"`.
*Evidence:* `audit_responsive.py`, 2026-08-31, V1 320×512 vs 1280×1024; `resp-{docs,edit,new,player}.json`.
*Fix:* a `max-width` breakpoint that hides a label must reposition it, not delete it.

**B-2 · No `viewport` declaration exists** — mobile.md Tier 1
`app/layout.tsx` has no `export const viewport`. Verified: `grep -rn "export const viewport" app/`
returns nothing. Without `width=device-width, initial-scale=1` a page can fall into the ~980px desktop
fallback viewport and reinstate the 300–350ms tap delay.
*Fix:* add `export const viewport: Viewport` with `width: "device-width"`, `initialScale: 1`,
`userScalable` unset, plus per-theme `themeColor`.

### MAJOR

**M-1 · 776 form controls render below 16 CSS px** — iOS Safari auto-zoom
Every `<input>`, `<select>` and `<textarea>` under 16px causes iOS Safari to zoom on focus and not
reliably zoom back out. Measured at 10.5px, 13px, 14px, 15px across all seven routes.
*Evidence:* `audit_responsive.py`, V1–V6 with `isMobile+hasTouch`; `resp-*.json`, rule `ios-input-autozoom`.
*Fix:* 16px floor on form controls. Disabling zoom is not a fix — it is a 1.4.4 failure.

**M-2 · 71 colour-contrast failures** — WCAG 1.4.3 (AA)
Three distinct root causes, all systemic:
- Per-entity accent colours used as *text* on card backgrounds, theme-independent so they fail in the
  dark themes: `#dc634a`/`#222b35` = **4.04** (×12), `#8e2b1c`/`#222b35` = **1.71**,
  `#3a5a78`/`#222b35` = **1.98**, `#6b4a8a`/`#222b35` = **2.02**, `#2f7d6b`/`#222b35` = **2.91**.
- The gold accent as small text: `#a8762a`/`#1a2129` = **4.08** (×20), `#a8762a`/`#222b35` = **3.61**,
  `#a8762a`/`#ede3cd` = **3.11**.
- Cream-on-accent buttons: `#f6ecda`/`#dc634a` = **3.02** (×6), `#f6ecda`/`#c8543e` = **3.74**.
Nearly all are at 7.5–10px, where the 4.5:1 threshold applies rather than the 3:1 large-text one.
*Why the existing gate missed them:* `utils/scripts/check_contrast.py` audits **declared theme tokens**.
These are raw hexes and decorative per-entity palettes, which live outside it.

**M-3 · 184 findings of body text below 14px; up to 58.2 % of a page's visible text at 10.5px**
`/storylines/embergate/documents` renders 58.2 % of its visible text at 10.5px at 320×512, and 54.7 %
at 768×1024. Audit thresholds: fail < 14px, warn 14–15px, pass ≥ 16px. A further 48 advisory findings
sit in the 14–15px warn band.

**M-4 · No skip link on any route, and no shared page frame**
*Corrected 2026-08-31 after checking the rendered DOM:* an earlier source-only reading of
`AppShell`/`layout.tsx` concluded there was no `<main>` landmark. That is wrong — every one of the
seven sampled routes renders **exactly one `<main>` and exactly one `<h1>`**. The landmark is fine.

What is actually missing is twofold. **No route has a skip link** (0 of 7 measured), so a keyboard user
tabs the full header on every navigation with no way past it. And each route hand-rolls its own `<main>`
with its own geometry — `px-[16px] py-[22px]` (documents), `px-[16px] py-[24px]` + `max-w-[1120px]`
(options), `px-[18px] py-[40px]` + `max-w-[1180px]` (creator), `mt-[16px]` and no max-width (library) —
because `AppShell` supplies no measure, gutter or rhythm for them to inherit.

**M-5 · 7 personal-data fields carry no `autocomplete` token** — WCAG 1.3.5 (AA), on `/…/edit`.

**M-6 · No route-level loading, error or not-found states**
No `loading.tsx`, `error.tsx` or `not-found.tsx` exists anywhere in `app/` (verified by `find`), so
every page renders its own loader and its own error state from scratch and a failure anywhere in a
route subtree escalates to the root. Focus movement on navigation is checked in Phase 7 rather than
asserted here — Next.js ships its own route announcer, so the claim needs measuring, not assuming.

### MINOR

**N-1 · `--header-h` is a phantom token.** `app/globals.css:198` sets
`scroll-margin-block-start: var(--header-h, 4.5rem)`. `--header-h` is declared nowhere, so the 72px
fallback always applies while the real headers are 52px (`AppHeader.tsx:39`) and 50px
(`SceneHeader.tsx:245`). Deep links land ~20px off.

**N-2 · The two dark themes never declare `color-scheme: dark`.** Native selects, date pickers, autofill
backgrounds and Firefox scrollbars render in light chrome on `.theme-dark` and `.theme-slate`. The
webkit-prefixed scrollbar block at `globals.css:226` covers one engine only.

**N-3 · Two header bars, no shared chassis.** 52px/`px-[16px] sm:px-[26px]`/with-shadow versus
50px/`px-[12px] sm:px-[24px]`/no-shadow, both repeating the same border and flex classes. The bar
height changes by 2px when you navigate from the library into a scene.

**N-4 · `<ul>` contains non-`<li>` children** on `/…/edit`; **`aria-allowed-attr`** violation on the
composer `<textarea>` on the player route.

**M-7 · Long frames during scroll, from forced synchronous layout**
*Corrected 2026-08-31: an earlier pass read only the tail of the run log and reported 2 minor frames.
The retained JSON carries more.* Under 4× CPU throttle:

| Route | Worst frame | Long frames | Dropped |
| --- | --- | --- | --- |
| `/` | **232ms** (180ms blocking) | 7 over 1.5× the 16.7ms median | — |
| `/embergate/salt` | **241ms** (188ms blocking) | 12 over the median | **8.82 %** |

Every one carries a non-zero `forcedStyleAndLayoutDuration` (30.5ms, 51.9ms measured), i.e. a DOM
read interleaved with writes forcing synchronous reflow. All occur at `scrollY 0`.

**Phase 3 attempted this and the attempt did not work.** Two genuine redundant forced layouts were
removed — `Composer.resize` and `BeatEditor` each read `scrollHeight` a second time *after* writing
`height`, forcing a whole extra synchronous layout for a number that cannot have changed. The fix is
correct and was kept. It moved nothing:

| | worst LoAF | long frames | dropped |
| --- | --- | --- | --- |
| before | 241ms | 12 | 8.82 % |
| after | 247ms | 11 | **11.76 %** |

n = 1 per arm, headless, so those deltas are noise in both directions — the honest reading is **no
measured change**, not a regression. The conclusion is that the fix targeted the wrong path: the
textarea autosize runs on keystrokes, and nothing is typing during a scroll pass. `scrollY 0` means
these frames are **mount and hydration work**, which is a different investigation and is not attempted
here. Recorded in `docs/checklist.md` rather than left looking solved.

**N-6 · Headers:** no `Permissions-Policy`; `X-Powered-By: Next.js` discloses the stack. Low
consequence for a local single-user app; recorded for whenever a deployment target is chosen.

### Recorded, but not a finding under this profile

**Mytheca is client-rendered for all domain data.** With JavaScript disabled, `/embergate` serves
35,376 bytes of HTML containing **none** of the storyline, cast or scenario content — verified
directly: zero elements in the markup carry `.reveal`, and zero carry an `opacity: 0` inline style.

`audit_motion.py` reports this as a **blocker** `fail-open-reveal` ("58 blocks of text are visible
only when JavaScript runs"), and its diagnosis is wrong for this case: it diffs visible text between
a JS and a no-JS render and attributes the difference to hiding. Nothing is hidden — the content is
never rendered, because it is fetched client-side. This was checked rather than accepted.

Severity comes from consequence, and every consequence the rule exists to prevent is nil here: the
profile sets `seo.priority: none`, there is no public origin, and no-JS is not a supported mode for a
local single-user AI chat application. It is recorded so a future reader does not rediscover the
blocker and act on it — and so that if Mytheca ever gains a public, indexable surface, this is the
first thing to revisit.

**The scroll-reveal system itself is correct.** `.reveal` in `styles/motion.css` carries no base
hidden state, is gated by both `@supports (animation-timeline: view())` and
`@media (prefers-reduced-motion: no-preference)`, declares `animation-timeline` after the shorthand,
and animates only `transform`/`opacity`. It is exactly the shape `dynamic-loading.md` prescribes.

### Not findings

Recorded so a later reader does not re-raise them:

- **No horizontal overflow** at any viewport, on any sampled route. The responsive skeleton is sound.
- **No `100vh`** anywhere in the codebase.
- **No scroll-event-driven reveals**, no abandoned reveal library, no `div onclick`.
- **Line length** is not reported at any severity — the 45–75 character figure is folklore
  (`site-categories.md` §1 evidence tiers).
- **SEO** is out of scope by owner decision (`seo.priority: none`).

---

## 3. Fit (stage 9)

Against the declared profile: `primary_job: demonstrate-craft`, `audience.intent: mixed`,
`motion.budget: expressive`, `content.volume: dense`.

| Declared | Built | Gap |
| --- | --- | --- |
| `motion.budget: expressive` | restrained: hover lifts, a fade, no entrance choreography | The site is quieter than its own brief. `motion.scroll_reveals: false` today. |
| `demonstrate-craft` | the craft is in the *prose engine*; the frame around it is generic | The reading surface does not carry the manuscript idea structurally — only decoratively. |
| `content.volume: dense` | dense, but with 30 type sizes and 165 spacing values | Density without a scale reads as clutter rather than richness. |

The mismatch is consistent and it is the same one in every row: **the design decisions are good and
they are not systematised.**

---

## 4. Sequencing

Remediation order, dependency-first — each stage makes the next cheaper:

1. **Tokens and scale** (fixes M-1, M-3, and the *cause* of M-2). A type scale with a 16px form floor,
   a spacing scale, and per-entity accent colours given AA-safe on-surface variants.
2. **Page frame** (fixes M-4, N-1, N-3, B-2). `<main>`, skip link, a shared header chassis, a real
   `--header-h`, the viewport export.
3. **Rebuild surfaces onto the frame** (fixes B-1, and removes the arbitrary values at their source).
4. **Motion layer** (closes the `expressive` gap; must satisfy the fail-open rule).
5. **Keyboard pass** (fixes M-6, and the seven-item minimum pass).

Re-audit as a **diff** against this report using the retained JSON.

---

# Re-audit — 2026-08-31, after the overhaul

Same instruments, same seven routes, same profile. Reported as a **diff** against the
baseline above, using the retained JSON. Nothing here is a fresh claim: every number has a
before and an after measured the same way.

## The numbers

| Measure | Baseline | After | |
| --- | ---: | ---: | --- |
| iOS form auto-zoom (`ios-input-autozoom`) | **776** | **0** | eliminated |
| Colour-contrast failures | **71** | **21** | −70 % |
| All **major** findings | **856** | **31** | −96 % |
| Blockers | 4 | 3 | the 3 are verified false positives, below |
| Smallest text rendered anywhere | **7.5px** | **11px** | the caption floor |
| Arbitrary font sizes in source | 625 over 30 values | **0** | on a 7-step scale |
| Arbitrary spacing values in source | 1,335 over 165 values | **0** | on a 9-step scale |
| Arbitrary border radii | 228 | **0** | on a 4-step scale |

Per route, majors: home 29→7 · storyline 29→7 · player 46→4 · options 230→5 · new 58→1 ·
edit 448→7 · documents 16→0.

**Text size is the one whose count barely moved and whose reality moved most.** The rule flags
anything under 14px, and Mytheca's caption tiers are 11–12px by design, so the count is
similar (184 → 185). The distribution is not:

| | baseline | after |
| --- | --- | --- |
| under 11px | **170 findings** (7.5px ×8, 8px ×25, 8.5px ×2, 9px ×24, 9.5px ×64, 10px ×8, 10.5px ×39) | **0** |
| 11–12px | 14 | 185 |

There is no longer any text below 11px anywhere in the app.

## What is left, and why

**3 blockers — all verified false positives.** Each was checked by hand rather than accepted:
- `TriagePanel`'s upload panel is a **disclosure**, collapsed below `lg` and openable. The
  script diffs visible text at 320px and 1280px and cannot see a toggle.
- `PlaythroughTray`'s label folds to a glyph below `sm`; the action stays reachable in the
  scene menu, and the button now carries an `sr-only` name (it previously had none — only a
  `title`, which is a last-resort naming source and is not surfaced on touch at all).
- The one **real** case — the storyline's name vanishing from the Documents header below
  768px — is fixed.

**21 contrast findings**, down from 71. Predominantly cream-on-accent at 12–13px, a trade-off
the locked design system already documents and `check_contrast.py` already encodes at 3:1
rather than 4.5:1. Not overridden silently.

**7 `form-missing-autocomplete`** on `/…/edit` — stat-name fields axe reads as personal-data
fields. **1 `aria-allowed-attr`** on the composer textarea. **1 `list`** on `/…/edit`. All
carried over from the baseline and unfixed; recorded rather than quietly dropped.

## One regression, found and fixed

The re-audit surfaced a finding the baseline did **not** have: `horizontal-overflow` on
`/options` at **V8** — 390px with a 32px root font size, the WCAG 1.4.4 "text at 200%"
viewport. The Options header cluster was a bare flex `div` rather than `HeaderLead`, so it
carried no `min-w-0`, could not shrink, and pushed the Library link 5px past the edge. Fixed
by using the primitive; re-measured at 0.

Worth stating plainly: **this was introduced by the overhaul and caught only because the
re-audit ran the full viewport matrix.** A spot-check at 390px would have missed it — the
overflow only exists once text doubles.

## What this re-audit still cannot tell you

Unchanged from the baseline, and still true: automated accessibility testing reaches ~30–40 %
of WCAG issues; there is no field data, so every performance number remains lab-only; motion
was measured headless, which under-reports jank; and one of the six WCAG 2.2 criteria is
machine-checkable. The keyboard and dialog behaviour reported in Phase 7 was verified by
driving a real browser, not by reading source — but a screen-reader pass has **not** been run.
