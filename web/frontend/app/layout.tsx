import type { Metadata } from "next";
import { cinzel, ebGaramond, ibmPlexMono } from "@/lib/fonts";
import { DEFAULT_THEME, themeClass, themeInitScript } from "@/lib/theme";
import { AppShell } from "@/components/layout/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Velora",
  description:
    "Velora — an AI-driven, multi-character roleplay chat engine, styled as a living manuscript.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${themeClass(DEFAULT_THEME)} ${cinzel.variable} ${ebGaramond.variable} ${ibmPlexMono.variable} h-full antialiased`}
    >
      {/* Browser extensions inject attrs/classes (e.g. `vc-init`) onto <body>
          before React hydrates; suppress the resulting mismatch warning. */}
      <body className="min-h-full" suppressHydrationWarning>
        {/* Apply the persisted theme before paint to avoid a flash. */}
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
