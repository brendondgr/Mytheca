import type { Metadata, Viewport } from "next";
import Script from "next/script";
import { cinzel, ebGaramond, ibmPlexMono } from "@/lib/fonts";
import { DEFAULT_THEME, THEME_PAGE_BG, themeClass, themeInitScript } from "@/lib/theme";
import { DEFAULT_FONT_SIZE, fontSizeClass, fontSizeInitScript } from "@/lib/font-size";
import { AppShell } from "@/components/layout/AppShell";
import "./globals.css";
import { VitalsProbe } from "@/components/layout/VitalsProbe";

export const metadata: Metadata = {
  // A template, so a route states only its own name. Every route previously
  // re-typed the " · Mytheca" suffix by hand, which meant a route that forgot
  // shipped a bare title and renaming the product meant touching every page.
  title: {
    default: "Mytheca",
    template: "%s · Mytheca",
  },
  description:
    "Mytheca — an AI-driven, multi-character roleplay chat engine, styled as a living manuscript.",
};

/**
 * The viewport declaration.
 *
 * There was none before this, which is a Tier 1 mobile failure: without
 * `width=device-width, initial-scale=1` a page can fall into the ~980px desktop
 * fallback viewport and reinstate the 300-350ms tap delay.
 *
 * `userScalable` and `maximumScale` are deliberately LEFT UNSET. Suppressing
 * zoom is a WCAG 1.4.4 failure, and it is the wrong fix for the auto-zoom
 * problem it is usually reached for — that one is solved by the >= 16px
 * `--fs-field` floor (styles/themes.css), not by taking zoom away.
 *
 * `themeColor` gives the mobile browser chrome a colour before any stylesheet
 * applies. The media-keyed pair below is the pre-JS default; the no-flash
 * script in `themeInitScript` immediately narrows it to the user's actual
 * saved theme, which is the only way to distinguish Ember from Slate — both
 * are dark, and `prefers-color-scheme` cannot tell them apart.
 */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // `viewportFit: "cover"` is deliberately ABSENT. It and `env(safe-area-inset-*)`
  // are all-or-nothing: opting in makes every fixed/sticky/full-screen element —
  // both header bars, the composer, every Drawer, the rail bar — responsible for
  // insetting itself by hand, and landscape moves the insets to left/right.
  // Adopting it here while the surfaces that must honour it are still being
  // rebuilt would put content under the notch. Without it the browser
  // letterboxes into the safe area automatically: safe, with visible bars.
  // Tracked in docs/checklist.md.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: THEME_PAGE_BG.light },
    { media: "(prefers-color-scheme: dark)", color: THEME_PAGE_BG[DEFAULT_THEME] },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      // Next warns when `scroll-behavior: smooth` is set on <html> without
      // this, because a route transition would then animate the scroll reset.
      // The attribute tells Next the smoothness is intentional and lets it
      // suppress the behaviour for its own navigations only.
      data-scroll-behavior="smooth"
      className={`${themeClass(DEFAULT_THEME)} ${fontSizeClass(DEFAULT_FONT_SIZE)} ${cinzel.variable} ${ebGaramond.variable} ${ibmPlexMono.variable} h-full antialiased`}
    >
      {/*
        Apply the persisted theme and font-size preset before paint, so there is
        no flash of the default theme.

        These are `next/script` rather than raw `<script dangerouslySetInnerHTML>`
        elements. React 19 warns whenever it *client-renders* a script element —
        "Scripts inside React components are never executed when rendering on the
        client" — and it is right to: if anything causes the root tree to be
        re-rendered on the client (a hydration mismatch anywhere in the app will
        do it), React recreates these nodes and the browser silently declines to
        run them. `beforeInteractive` hands them to Next instead, which injects
        them into the initial HTML outside the React element tree, so they run
        during document parse and are never re-created.
      */}
      {/* Browser extensions inject attrs/classes (e.g. `vc-init`) onto <body>
          before React hydrates; suppress the resulting mismatch warning. */}
      <body className="min-h-full" suppressHydrationWarning>
        <Script
          id="mytheca-theme-init"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: themeInitScript }}
        />
        <Script
          id="mytheca-font-size-init"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{ __html: fontSizeInitScript }}
        />
        <AppShell>{children}</AppShell>
        {/* Renders nothing and loads nothing unless NEXT_PUBLIC_VITALS=1 — see VitalsProbe. */}
        <VitalsProbe />
      </body>
    </html>
  );
}
