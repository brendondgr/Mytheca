import { Cinzel, EB_Garamond, IBM_Plex_Mono } from "next/font/google";

// Velora's three type families (see docs/design-system.md):
// Cinzel = display/headings, EB Garamond = body/reading, IBM Plex Mono = labels/metadata.
// Each is exposed as a CSS variable so Tailwind utilities + raw CSS can reference it,
// and the variable class is applied once on <html> in app/layout.tsx.

export const cinzel = Cinzel({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
  variable: "--font-cinzel",
});

export const ebGaramond = EB_Garamond({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-eb-garamond",
});

export const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-ibm-plex-mono",
});
