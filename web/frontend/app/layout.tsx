import type { Metadata } from "next";
import { cinzel, ebGaramond, ibmPlexMono } from "@/lib/fonts";
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
      className={`${cinzel.variable} ${ebGaramond.variable} ${ibmPlexMono.variable} h-full antialiased`}
    >
      <body className="min-h-full">{children}</body>
    </html>
  );
}
