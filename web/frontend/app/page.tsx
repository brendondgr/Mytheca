import type { Metadata } from "next";
import { LibraryView } from "@/features/library/LibraryView";

export const metadata: Metadata = {
  title: "Library · Mytheca",
};

// The Library is Mytheca's front page for now (see docs/routes.md).
export default function Home() {
  return <LibraryView />;
}
