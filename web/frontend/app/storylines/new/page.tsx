import type { Metadata } from "next";
import { StorylineCreatorView } from "@/features/library/StorylineCreatorView";

export const metadata: Metadata = {
  title: "New Storyline",
};

// `/storylines/new` — the dedicated New Storyline page (also the empty-state default
// when no storylines exist; `/` redirects here). The literal `storylines/` segment
// resolves before the dynamic root `/[storylineId]`.
export default function NewStorylinePage() {
  return <StorylineCreatorView />;
}
