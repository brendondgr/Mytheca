// Shared "filter" for full-bleed Library card art (ScenarioCard / SettingCard /
// the carousel hero / SceneLoader).
//
// Three stacked layers, listed top-first:
//
//  1. A horizontal gradient that is dark on the left — under the text — and
//     falls away to the right so the scene/establishing art reads through.
//  2. A bottom reinforcement, for text that sits low in the frame.
//  3. A flat wash across the whole card.
//
// Layer 3 is the important one. The directional gradient alone protected text
// well at the left edge and progressively less across the text band, so over
// *bright* artwork the far end of a title or goal line washed out — the exact
// "near-white art directly behind the text band" edge case this file's own
// notes used to accept. A gradient cannot fix that on its own without dragging
// its dark end so far right that the artwork stops reading at all. A low flat
// wash sets a floor everywhere instead, and costs the art much less: it takes
// the far-right corner from ~14% darkened to ~28%, which reads as a gentle
// unifying tint rather than a scrim.
//
// The guarantee is enforced by `cardArt.test.ts`, which composites these
// against pure white — the worst case any artwork can present — and checks the
// result against `OVER_ART`. Change a stop and the test tells you what it cost.
//
// Fixed dark values (theme-independent) since the artwork is the same in every
// theme.
export const CARD_SCRIM =
  "linear-gradient(95deg, rgba(16,11,4,0.95) 0%, rgba(16,11,4,0.90) 34%, rgba(16,11,4,0.80) 58%, rgba(16,11,4,0.50) 78%, rgba(16,11,4,0.06) 100%), " +
  "linear-gradient(0deg, rgba(12,8,3,0.5) 0%, rgba(12,8,3,0) 42%), " +
  "linear-gradient(0deg, rgba(10,7,3,0.10) 0%, rgba(10,7,3,0.10) 100%)";

// Vertical variant for full-bleed PORTRAIT art (CharacterCard, and the hero's
// cast tiles): dark at the bottom — under the name/role footer — fading to
// clear by ~58% so the upper two-thirds of the portrait reads cleanly.
//
// Deliberately gets NO flat wash. Its text occupies a narrow band at the very
// bottom where the gradient is already at 0.72–0.92, which clears AA over white
// on its own (also covered by the test), and a wash over a portrait would dim
// the face for no benefit.
export const PORTRAIT_SCRIM =
  "linear-gradient(0deg, rgba(12,8,3,0.92) 0%, rgba(12,8,3,0.72) 22%, rgba(12,8,3,0.28) 42%, rgba(12,8,3,0) 58%)";

/**
 * How far across the card the text band is allowed to run, as a fraction.
 *
 * The card components cap their text at ~60% (`max-w-[60%]`) so it stays over
 * the dark side of the gradient; the title's line box runs further, to roughly
 * 78%, because it only reserves room for the top-right control cluster. Both
 * numbers are the positions the contrast test evaluates, so they live here
 * rather than being re-derived from the Tailwind classes.
 */
export const TEXT_BAND = {
  /** Body, eyebrow, and meta text — capped, and held to the AA 4.5:1 bar. */
  bodyEnd: 0.6,
  /** The title's full line-box extent. Large text, so the 3:1 bar applies. */
  titleEnd: 0.78,
} as const;

// Light text constants for content laid over the dark side of the scrim.
export const OVER_ART = {
  title: "#F6ECDA",
  eyebrow: "#E8B24A", // brightened gold — legible over the dark scrim
  // Opaque on purpose. This was `rgba(246,236,218,0.86)`, which composites with
  // whatever is behind it — so over bright art the body text lost contrast from
  // BOTH sides at once, the background lightening and the ink lightening with
  // it. A flat colour one step down from the title reads the same and cannot
  // drift.
  body: "#EFE3CC",
  meta: "#E8D8B8",
  accent: "#F0A088", // light ember for the "in this scene" state over art
  hair: "rgba(246,236,218,0.18)",
} as const;
