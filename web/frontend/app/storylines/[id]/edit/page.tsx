import type { Metadata } from "next";
import { StorylineCreatorView } from "@/features/library/StorylineCreatorView";

export const metadata: Metadata = {
  title: "Edit Storyline",
};

// `/storylines/[id]/edit` — the storyline editor (same page as create, prefilled).
export default async function EditStorylinePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <StorylineCreatorView editId={id} />;
}
