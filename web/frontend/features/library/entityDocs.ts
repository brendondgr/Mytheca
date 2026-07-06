// Entity-scoped context documents for the Character / Setting / Scenario editors.
//
// Unlike the storyline page (Triage → bulk commit), these editors attach reference
// files to a *single* entity. The files persist (so they reappear on re-edit) and
// are embedded into the RAG corpus on save. `loadEntityDocs` re-hydrates a modal's
// `_docFiles` from the backend; `syncEntityDocs` reconciles the panel against the
// stored set (create new drops, delete removed ones — which also prunes embeddings).

import * as api from "@/lib/api";
import type { ReadDoc } from "@/lib/readDocs";
import type { DocCategory, EntityScope } from "@/lib/types";

/** The triage category implied by an entity scope (so the doc reads sensibly). */
const SCOPE_CATEGORY: Record<EntityScope, DocCategory> = {
  character: "character",
  setting: "setting",
  scenario: "other",
};

/** Load an entity's persisted context docs as `ReadDoc[]` (carrying their ids). */
export async function loadEntityDocs(
  storylineId: string,
  entityType: EntityScope,
  entityId: string,
): Promise<ReadDoc[]> {
  const docs = await api.listContextDocuments(storylineId, { entityType, entityId });
  return docs.map((d) => ({
    id: d.id,
    name: d.name,
    text: d.content,
    useDraft: d.includeDraft,
    useRag: d.includeRag,
    useExtract: d.includeExtract,
  }));
}

/**
 * Reconcile an entity's stored context docs against the editor's current files:
 * delete any the author removed (pruning their embeddings) and create any new
 * drops, scoped to the entity. Idempotent — re-running with the same files is a
 * no-op. Matches by file name.
 */
export async function syncEntityDocs(
  storylineId: string,
  entityType: EntityScope,
  entityId: string,
  docFiles: ReadDoc[] | undefined,
): Promise<void> {
  const files = docFiles ?? [];
  const existing = await api.listContextDocuments(storylineId, { entityType, entityId });
  const existingNames = new Set(existing.map((d) => d.name));
  const keepNames = new Set(files.map((f) => f.name));

  await Promise.all(
    existing.filter((d) => !keepNames.has(d.name)).map((d) => api.deleteContextDocument(d.id)),
  );

  const toCreate = files.filter((f) => !existingNames.has(f.name));
  if (toCreate.length) {
    await api.bulkCreateContextDocuments(
      storylineId,
      toCreate.map((f) => ({
        name: f.name,
        content: f.text,
        category: SCOPE_CATEGORY[entityType],
        includeDraft: f.useDraft ?? false,
        includeRag: f.useRag ?? true,
        // Extraction never applies to entity-scoped docs (already tied to one entity).
        includeExtract: f.useExtract ?? false,
        source: "upload",
        entityType,
        entityId,
      })),
    );
  }
}
