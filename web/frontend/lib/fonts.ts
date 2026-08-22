import localFont from "next/font/local";

// Mytheca's three type families (see docs/design-system.md):
// Cinzel = display/headings, EB Garamond = body/reading, IBM Plex Mono = labels/metadata.
// Each is exposed as a CSS variable so Tailwind utilities + raw CSS can reference it,
// and the variable class is applied once on <html> in app/layout.tsx.
//
// SELF-HOSTED, not `next/font/google`. That is not a preference: `next/font/google` fetches
// at BUILD time, so `next build` hard-fails with no network — which is why this repository
// had never once produced a production bundle in its own development environment, and why
// every "deferred verification" in docs/checklist.md traced back to the same root cause.
// Self-hosting also removes a third-party connection from the critical path.
//
// The woff2 files in `app/fonts/` are the **latin** subsets Google serves, which is exactly
// what `subsets: ["latin"]` requested before. Cinzel and EB Garamond ship as VARIABLE fonts —
// Google returns one identical file for every weight of each — so they are stored once and
// declared with a weight range rather than duplicated three times. IBM Plex Mono is static,
// so its two weights are two files. All three are OFL-licensed; the licences sit beside them.

/** Display / headings. Variable `wght`; the app uses 500–700. */
export const cinzel = localFont({
  src: [{ path: "../app/fonts/Cinzel-Variable.woff2", weight: "400 900", style: "normal" }],
  display: "swap",
  variable: "--font-cinzel",
  // Metric-compatible fallback, matching what `next/font/google` generated. Without it,
  // removing the Google loader would *introduce* the layout shift the next phase measures.
  adjustFontFallback: "Times New Roman",
  fallback: ["Georgia", "Times New Roman", "serif"],
});

/** Body / reading prose. Variable `wght`, with a true italic file. */
export const ebGaramond = localFont({
  src: [
    { path: "../app/fonts/EBGaramond-Variable.woff2", weight: "400 800", style: "normal" },
    { path: "../app/fonts/EBGaramond-Variable-Italic.woff2", weight: "400 800", style: "italic" },
  ],
  display: "swap",
  variable: "--font-eb-garamond",
  adjustFontFallback: "Times New Roman",
  fallback: ["Georgia", "Times New Roman", "serif"],
});

/** Labels / metadata. Static weights. */
export const ibmPlexMono = localFont({
  src: [
    { path: "../app/fonts/IBMPlexMono-400.woff2", weight: "400", style: "normal" },
    { path: "../app/fonts/IBMPlexMono-500.woff2", weight: "500", style: "normal" },
  ],
  display: "swap",
  variable: "--font-ibm-plex-mono",
  adjustFontFallback: "Arial",
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
});
