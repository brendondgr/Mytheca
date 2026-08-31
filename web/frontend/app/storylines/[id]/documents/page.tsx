import type { Metadata } from "next";
import { DocumentsView } from "@/features/documents/DocumentsView";

export const metadata: Metadata = {
  title: "Documents",
};

// `/storylines/[id]/documents` — the world's context-document manager: see & adjust
// every uploaded reference document and how each is used.
export default async function StorylineDocumentsPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <DocumentsView storylineId={id} />;
}
