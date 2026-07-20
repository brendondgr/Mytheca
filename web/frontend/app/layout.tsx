import type { Metadata } from "next";
import { cinzel, ebGaramond, ibmPlexMono } from "@/lib/fonts";
import { DEFAULT_THEME, themeClass, themeInitScript } from "@/lib/theme";
import { DEFAULT_FONT_SIZE, fontSizeClass, fontSizeInitScript } from "@/lib/font-size";
import { AppShell } from "@/components/layout/AppShell";
import "./globals.css";

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
      className={`${themeClass(DEFAULT_THEME)} ${fontSizeClass(DEFAULT_FONT_SIZE)} ${cinzel.variable} ${ebGaramond.variable} ${ibmPlexMono.variable} h-full antialiased`}
    >
      {/* Browser extensions inject attrs/classes (e.g. `vc-init`) onto <body>
          before React hydrates; suppress the resulting mismatch warning. */}
      <body className="min-h-full" suppressHydrationWarning>
        {/* Apply the persisted theme and font-size preset before paint to avoid a flash. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <script dangerouslySetInnerHTML={{ __html: fontSizeInitScript }} />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
