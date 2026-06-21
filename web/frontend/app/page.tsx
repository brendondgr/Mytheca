import type { Metadata } from "next";
import { LibraryView } from "@/features/library/LibraryView";

export const metadata: Metadata = {
  title: "Library · Velora",
};

// The Library is Velora's front page for now (see docs/routes.md).
export default function Home() {
  return <LibraryView />;
}
