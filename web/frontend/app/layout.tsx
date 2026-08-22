import type { Metadata } from "next";
import Script from "next/script";
import { cinzel, ebGaramond, ibmPlexMono } from "@/lib/fonts";
import { DEFAULT_THEME, themeClass, themeInitScript } from "@/lib/theme";
import { DEFAULT_FONT_SIZE, fontSizeClass, fontSizeInitScript } from "@/lib/font-size";
import { AppShell } from "@/components/layout/AppShell";
import "./globals.css";
import { VitalsProbe } from "@/components/layout/VitalsProbe";

export const metadata: Metadata = {
  title: "Mytheca",
  description:
    "Mytheca — an AI-driven, multi-character roleplay chat engine, styled as a living manuscript.",
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
