import type { Metadata } from "next";
import { LibraryView } from "@/features/library/LibraryView";

export const metadata: Metadata = {
  // `absolute`, not a bare string: Next applies `title.template` to CHILD route
  // segments only, and this page IS the root segment the template is declared
  // on — so a bare "Library" here ships without the brand suffix while every
  // other route gets it. Every other page in the app can and does stay bare.
  title: { absolute: "Library · Mytheca" },
};

// The Library is Mytheca's front page for now (see docs/routes.md).
export default function Home() {
  return <LibraryView />;
}
