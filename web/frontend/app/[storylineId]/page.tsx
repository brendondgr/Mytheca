import type { Metadata } from "next";
import { LibraryView } from "@/features/library/LibraryView";

export const metadata: Metadata = {
  title: "Library · Velora",
};

// `/{storylineId}` — the Library scoped to one storyline. The id selects the
// active world on load (see useLibraryState); unknown ids fall back to the first
// storyline. Seed slugs (e.g. `embergate`) and short 8-hex ids both resolve here.
export default async function StorylinePage({
  params,
}: {
  params: Promise<{ storylineId: string }>;
}) {
  const { storylineId } = await params;
  return <LibraryView initialStorylineId={storylineId} />;
}
