"use client";

import { useCallback, useEffect, useState } from "react";
import * as api from "@/lib/api";
import { readDocFiles, type ReadDoc } from "@/lib/readDocs";
import type { ContextDocument, DocCategory, EntityScope } from "@/lib/types";

/** A human label for an entity a doc is scoped or linked to (else its raw id). */
export type EntityLabeler = (entityType: EntityScope, entityId: string) => string;

/**
 * State + actions for the storyline document manager (`/storylines/[id]/documents`).
 *
 * Loads the storyline's FULL context corpus (every doc — storyline-level and
 * entity-owned) plus the cast/settings/scenarios so scope + provenance links can be
 * shown by name. All edits go straight through the existing context-doc endpoints and
 * update the in-memory list, so the manager stays live without a full refetch.
 */
export function useDocuments(storylineId: string) {
  const [docs, setDocs] = useState<ContextDocument[]>([]);
  const [title, setTitle] = useState("");
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [storyline, corpus, characters, settings, scenarios] = await Promise.all([
        api.getStoryline(storylineId),
        api.listContextDocuments(storylineId),
        api.listCharacters(storylineId).catch(() => []),
        api.listSettings(storylineId).catch(() => []),
        api.listScenarios(storylineId).catch(() => []),
      ]);
      setTitle(storyline.title);
      setDocs(corpus);
      const map: Record<string, string> = {};
      for (const c of characters) map[`character:${c.id}`] = c.name;
      for (const s of settings) map[`setting:${s.id}`] = s.name;
      for (const sc of scenarios) map[`scenario:${sc.id}`] = sc.title;
      setLabels(map);
    } catch {
      setError("Could not load documents.");
    } finally {
      setLoading(false);
    }
  }, [storylineId]);

  useEffect(() => {
    // Canonical mount data-fetch: load() sets state only after awaiting the API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  /**
   * Re-run the corpus load after a failure.
   *
   * `reload` alone is not enough for a retry: it leaves the previous error on
   * screen and never puts the view back into its loading state, so a
   * successful second attempt would arrive underneath a stale alert.
   */
  const retry = useCallback(() => {
    setError(null);
    setLoading(true);
    void load();
  }, [load]);

  const entityLabel = useCallback<EntityLabeler>(
    (entityType, entityId) => labels[`${entityType}:${entityId}`] ?? entityId,
    [labels],
  );

  /** Patch a doc's usage (flags / category) and reflect it locally. */
  const updateDoc = useCallback(
    async (docId: string, patch: Partial<ContextDocument>) => {
      // Optimistic: apply immediately, then persist (revert on failure).
      const prev = docs;
      setDocs((cur) => cur.map((d) => (d.id === docId ? { ...d, ...patch } : d)));
      try {
        const saved = await api.updateContextDocument(docId, patch);
        setDocs((cur) => cur.map((d) => (d.id === docId ? saved : d)));
      } catch {
        setDocs(prev);
        setError("Could not save the change.");
      }
    },
    [docs],
  );

  const removeDoc = useCallback(async (docId: string) => {
    const prev = docs;
    setDocs((cur) => cur.filter((d) => d.id !== docId));
    try {
      await api.deleteContextDocument(docId);
    } catch {
      setDocs(prev);
      setError("Could not delete the document.");
    }
  }, [docs]);

  /** Upload dropped `.txt`/`.md` files as storyline-level corpus docs. */
  const addFiles = useCallback(
    async (files: FileList | File[] | null, category: DocCategory = "other") => {
      if (!files) return;
      const read: ReadDoc[] = await readDocFiles(Array.from(files));
      if (read.length === 0) return;
      setBusy(true);
      try {
        const created = await api.bulkCreateContextDocuments(
          storylineId,
          read.map((f) => ({
            name: f.name,
            content: f.text,
            category: category === "select" ? "other" : category,
            includeRag: true,
            source: "upload",
          })),
        );
        setDocs((cur) => [...cur, ...created]);
      } catch {
        setError("Could not upload the files.");
      } finally {
        setBusy(false);
      }
    },
    [storylineId],
  );

  return {
    docs,
    title,
    loading,
    error,
    busy,
    entityLabel,
    updateDoc,
    removeDoc,
    addFiles,
    reload: load,
    retry,
  };
}

/** Docs grouped by triage bucket, for the manager's sectioned view. */
export function groupByCategory(docs: ContextDocument[]): [DocCategory, ContextDocument[]][] {
  const order: DocCategory[] = ["character", "setting", "other"];
  const groups: Record<string, ContextDocument[]> = {};
  for (const d of docs) {
    const key = d.category === "select" ? "other" : d.category;
    (groups[key] ??= []).push(d);
  }
  return order
    .filter((c) => (groups[c]?.length ?? 0) > 0)
    .map((c) => [c, groups[c]] as [DocCategory, ContextDocument[]]);
}
