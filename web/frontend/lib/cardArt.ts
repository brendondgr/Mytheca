// Shared "filter" for full-bleed Library card art (ScenarioCard / SettingCard).
// A horizontal gradient that is dark on the left — under the text — and brightens
// to near-clear on the right so the scene/establishing art reads through, plus a
// light bottom reinforcement. Mirrors the carousel hero's scene-art scrim. Fixed
// dark values (theme-independent) since the artwork is the same in every theme.
export const CARD_SCRIM =
  "linear-gradient(95deg, rgba(16,11,4,0.94) 0%, rgba(16,11,4,0.82) 36%, rgba(16,11,4,0.46) 66%, rgba(16,11,4,0.14) 100%), linear-gradient(0deg, rgba(12,8,3,0.5) 0%, rgba(12,8,3,0) 42%)";

// Vertical variant for full-bleed PORTRAIT art (CharacterCard): dark at the
// bottom — under the name/role footer — fading to clear by ~58% so the upper
// two-thirds of the portrait reads cleanly. Same theme-independent dark values.
export const PORTRAIT_SCRIM =
  "linear-gradient(0deg, rgba(12,8,3,0.92) 0%, rgba(12,8,3,0.72) 22%, rgba(12,8,3,0.28) 42%, rgba(12,8,3,0) 58%)";

// Light text constants for content laid over the dark side of the scrim.
export const OVER_ART = {
  title: "#F6ECDA",
  eyebrow: "#E8B24A", // brightened gold — legible over the dark scrim
  body: "rgba(246,236,218,0.86)",
  meta: "#E8D8B8",
  accent: "#F0A088", // light ember for the "in this scene" state over art
  hair: "rgba(246,236,218,0.18)",
} as const;
