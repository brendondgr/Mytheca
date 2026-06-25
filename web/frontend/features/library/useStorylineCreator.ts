"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import * as api from "@/lib/api";
import { budgetFor } from "@/lib/contextBudget";
import { concatDocs, readDocFiles } from "@/lib/readDocs";
import type {
  ContextDocument,
  DocCategory,
  ProposedCharacter,
  ProposedSetting,
  ProposedWorld,
  StatDefinition,
} from "@/lib/types";
import {
  applyTriage,
  BLANK_FIELDS,
  commitWorld,
  type CreatorDoc,
  type CreatorFields,
  draftDocTexts,
  fieldsFromStoryline,
  isCreatorValid,
  toCreatorDoc,
} from "@/features/library/storylineCreator";

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong.";
}

/** Draft-included docs as one bounded grounding string (or undefined). */
function draftGrounding(docs: CreatorDoc[]): string | undefined {
  return concatDocs(docs.filter((d) => d.useDraft));
}

/**
 * State for the New Storyline page (`StorylineCreatorView`). Holds the by-hand
 * fields, the universal stats, the dropped + triaged context docs, and the agentic
 * build proposal; exposes the triage / build / draft / generate-primer / commit
 * actions. In edit mode it loads the storyline, its stats, and its corpus.
 */
export function useStorylineCreator(editId?: string) {
  const [fields, setFields] = useState<CreatorFields>(BLANK_FIELDS);
  const [stats, setStats] = useState<StatDefinition[]>([]);
  const [statsOriginal, setStatsOriginal] = useState<StatDefinition[]>([]);
  const [docs, setDocs] = useState<CreatorDoc[]>([]);
  const [existingDocs, setExistingDocs] = useState<ContextDocument[]>([]);
  const [seed, setSeed] = useState("");
  const [proposed, setProposed] = useState<ProposedWorld | null>(null);

  const [loading, setLoading] = useState(Boolean(editId));
  const [drafting, setDrafting] = useState(false);
  const [generatingPrimer, setGeneratingPrimer] = useState(false);
  const [triaging, setTriaging] = useState(false);
  const [building, setBuilding] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ---- edit-mode load ----
  useEffect(() => {
    if (!editId) return;
    let cancelled = false;
    void (async () => {
      try {
        const [sl, defs, ctx] = await Promise.all([
          api.getStoryline(editId),
          api.listStatDefinitions(editId),
          api.listContextDocuments(editId),
        ]);
        if (cancelled) return;
        setFields(fieldsFromStoryline(sl));
        setStats(defs);
        setStatsOriginal(defs);
        setExistingDocs(ctx);
      } catch (e) {
        if (!cancelled) setError(messageOf(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [editId]);

  const setField = useCallback(
    <K extends keyof CreatorFields>(key: K, value: CreatorFields[K]) =>
      setFields((prev) => ({ ...prev, [key]: value })),
    [],
  );

  // ---- context-file management ----
  const addFiles = useCallback(async (files: FileList | File[] | null) => {
    if (!files) return;
    const read = await readDocFiles(Array.from(files));
    if (read.length === 0) return;
    setDocs((prev) => {
      const byName = new Map(prev.map((d) => [d.name, d]));
      for (const doc of read) {
        const existing = byName.get(doc.name);
        // Re-dropping a name keeps its triage choices; a new file starts untriaged.
        byName.set(doc.name, existing ? { ...existing, text: doc.text } : toCreatorDoc(doc));
      }
      return Array.from(byName.values());
    });
  }, []);

  const removeDoc = useCallback(
    (name: string) => setDocs((prev) => prev.filter((d) => d.name !== name)),
    [],
  );
  const toggleDocUse = useCallback(
    (name: string, key: "useDraft" | "useRag") =>
      setDocs((prev) =>
        prev.map((d) => (d.name === name ? { ...d, [key]: !(d[key] ?? false) } : d)),
      ),
    [],
  );
  const setDocCategory = useCallback(
    (name: string, category: DocCategory) =>
      setDocs((prev) => prev.map((d) => (d.name === name ? { ...d, category } : d))),
    [],
  );

  // ---- agentic actions ----
  const triage = useCallback(async () => {
    const withText = docs.filter((d) => d.text);
    if (withText.length === 0) return;
    setTriaging(true);
    setError(null);
    try {
      const { items } = await api.triageDocuments(
        withText.map((d) => ({ name: d.name, text: d.text })),
        editId,
      );
      setDocs((prev) => applyTriage(prev, items));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setTriaging(false);
    }
  }, [docs, editId]);

  const draftMeta = useCallback(async () => {
    const s = seed.trim();
    if (!s) return;
    setDrafting(true);
    setError(null);
    try {
      const d = await api.draftStoryline(s, draftGrounding(docs));
      setFields((prev) => ({
        ...prev,
        title: d.title || prev.title,
        genre: d.genre || prev.genre,
        tagline: d.tagline || prev.tagline,
        premise: d.premise || prev.premise,
      }));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setDrafting(false);
    }
  }, [seed, docs]);

  const generatePrimer = useCallback(async () => {
    const premise = fields.premise.trim();
    const s = seed.trim();
    if (!premise && !s) return;
    setGeneratingPrimer(true);
    setError(null);
    try {
      const { worldPrimer } = await api.generateWorldPrimer({
        premise: premise || undefined,
        seed: s || undefined,
        docsOverview: draftGrounding(docs),
      });
      setFields((prev) => ({ ...prev, worldPrimer }));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setGeneratingPrimer(false);
    }
  }, [fields.premise, seed, docs]);

  const build = useCallback(async () => {
    const s = seed.trim();
    const docsOverview = draftGrounding(docs);
    if (!s && !docsOverview) {
      setError("Add a one-sentence seed or drop context files to build from.");
      return;
    }
    setBuilding(true);
    setError(null);
    try {
      const world = await api.buildWorld({
        seed: s || undefined,
        docsOverview,
        storylineId: editId,
      });
      setProposed(world);
      // Reflect the build into the editable left column; the proposal drives the cast.
      setFields((prev) => ({
        ...prev,
        title: world.storyline.title || prev.title,
        genre: world.storyline.genre || prev.genre,
        tagline: world.storyline.tagline || prev.tagline,
        premise: world.storyline.premise || prev.premise,
        worldPrimer: world.storyline.worldPrimer || prev.worldPrimer,
      }));
      if (world.stats.length) setStats(world.stats);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBuilding(false);
    }
  }, [seed, docs, editId]);

  // ---- proposed-world review edits ----
  const updateProposedCharacter = useCallback(
    (index: number, patch: Partial<ProposedCharacter>) =>
      setProposed((p) =>
        p ? { ...p, characters: p.characters.map((c, i) => (i === index ? { ...c, ...patch } : c)) } : p,
      ),
    [],
  );
  const removeProposedCharacter = useCallback(
    (index: number) =>
      setProposed((p) => (p ? { ...p, characters: p.characters.filter((_, i) => i !== index) } : p)),
    [],
  );
  const updateProposedSetting = useCallback(
    (index: number, patch: Partial<ProposedSetting>) =>
      setProposed((p) =>
        p ? { ...p, settings: p.settings.map((s, i) => (i === index ? { ...s, ...patch } : s)) } : p,
      ),
    [],
  );
  const removeProposedSetting = useCallback(
    (index: number) =>
      setProposed((p) => (p ? { ...p, settings: p.settings.filter((_, i) => i !== index) } : p)),
    [],
  );
  const discardProposal = useCallback(() => setProposed(null), []);

  // ---- commit ----
  const commit = useCallback(async (): Promise<string | null> => {
    if (!isCreatorValid(fields)) {
      setError("Give the world a title first.");
      return null;
    }
    setCommitting(true);
    setError(null);
    setProgress(null);
    try {
      const id = await commitWorld(
        { editId, fields, stats, statsOriginal, proposed, docs, existingDocs },
        setProgress,
      );
      return id;
    } catch (e) {
      setError(messageOf(e));
      return null;
    } finally {
      setCommitting(false);
      setProgress(null);
    }
  }, [editId, fields, stats, statsOriginal, proposed, docs, existingDocs]);

  const budget = useMemo(
    () => budgetFor({ worldPrimer: fields.worldPrimer, draftDocs: draftDocTexts(docs) }),
    [fields.worldPrimer, docs],
  );
  const statsOriginalKeys = useMemo(
    () => new Set(statsOriginal.map((s) => s.key)),
    [statsOriginal],
  );

  return {
    isEdit: Boolean(editId),
    editId,
    fields,
    setField,
    stats,
    setStats,
    statsOriginalKeys,
    docs,
    existingDocs,
    addFiles,
    removeDoc,
    toggleDocUse,
    setDocCategory,
    seed,
    setSeed,
    proposed,
    updateProposedCharacter,
    removeProposedCharacter,
    updateProposedSetting,
    removeProposedSetting,
    discardProposal,
    budget,
    isValid: isCreatorValid(fields),
    loading,
    drafting,
    generatingPrimer,
    triaging,
    building,
    committing,
    progress,
    error,
    triage,
    draftMeta,
    generatePrimer,
    build,
    commit,
  };
}
