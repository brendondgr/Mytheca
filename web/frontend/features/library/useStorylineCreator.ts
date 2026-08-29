"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as api from "@/lib/api";
import { readDocFiles, type DocUse } from "@/lib/readDocs";
import { budgetFor } from "@/lib/contextBudget";
import type {
  ContextDocument,
  DocCategory,
  PopulateOptions,
  StatDefinition,
} from "@/lib/types";
import {
  applyTriage,
  BLANK_FIELDS,
  commitWorld,
  type CreatorDoc,
  type CreatorFields,
  draftDocTexts,
  draftGrounding,
  fieldsFromStoryline,
  runPopulate,
  fromContextDocument,
  isCreatorValid,
  toCreatorDoc,
  type TriageActive,
  type UploadDefaults,
} from "@/features/library/storylineCreator";
import {
  type BuildState,
  emptyBuild,
  willBuild,
} from "@/features/library/worldBuild";

function messageOf(e: unknown): string {
  return e instanceof Error ? e.message : "Something went wrong.";
}

/**
 * What the Build-world dialog offers by default: build the cast + settings, but no
 * artwork — every image is a ComfyUI render, so it stays an explicit opt-in.
 */
export const DEFAULT_POPULATE: PopulateOptions = {
  enabled: true,
  withArtwork: false,
  artStyle: null,
  // Resolved by the dialog from what the author actually uploaded: "auto" means the
  // server builds from their classified files when there are any.
  source: "auto",
};

/**
 * State for the New Storyline page (`StorylineCreatorView`). Holds the by-hand
 * fields, the universal stats, and the dropped + triaged context docs; exposes the
 * triage / generate-primer / commit actions. In edit mode it loads the storyline,
 * its stats, and its corpus.
 */
export function useStorylineCreator(editId?: string) {
  const [fields, setFields] = useState<CreatorFields>(BLANK_FIELDS);
  const [stats, setStats] = useState<StatDefinition[]>([]);
  const [statsOriginal, setStatsOriginal] = useState<StatDefinition[]>([]);
  const [docs, setDocs] = useState<CreatorDoc[]>([]);
  const [existingDocs, setExistingDocs] = useState<ContextDocument[]>([]);

  const [loading, setLoading] = useState(Boolean(editId));
  const [generatingPrimer, setGeneratingPrimer] = useState(false);
  const [generatingStyle, setGeneratingStyle] = useState(false);
  const [triaging, setTriaging] = useState(false);
  const [triageActive, setTriageActive] = useState<TriageActive | null>(null);
  const [committing, setCommitting] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // RAG corpus (vector store) status + the live re-embed action (edit mode).
  const [ragStatus, setRagStatus] = useState<{ available: boolean; indexed: number } | null>(null);
  const [reembedding, setReembedding] = useState(false);
  const [reembedProgress, setReembedProgress] = useState<string | null>(null);

  // Abort in-flight streams when the component unmounts (or a new run starts).
  const triageAbort = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      triageAbort.current?.abort();
    },
    [],
  );

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
        // Re-hydrate the panel with the world's saved corpus so previously-uploaded
        // context files stay visible on edit (the "lost track" fix). Only storyline-
        // level docs belong here; entity-scoped docs live in their own editors.
        setDocs(ctx.filter((d) => !d.entityType).map(fromContextDocument));
        // Best-effort: how many entries are embedded for this world.
        void api.getRagStatus(editId).then((s) => {
          if (!cancelled) setRagStatus(s);
        }).catch(() => {});
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
  // `opts` carries the author's chosen upload target (category + Draft/RAG), so a
  // whole batch can be dropped pre-categorized (e.g. "Characters") with no triage. When
  // omitted, files land Uncategorized with the default Draft/RAG.
  const addFiles = useCallback(
    async (files: FileList | File[] | null, opts: UploadDefaults = {}) => {
      if (!files) return;
      const read = await readDocFiles(Array.from(files));
      if (read.length === 0) return;
      setDocs((prev) => {
        const byName = new Map(prev.map((d) => [d.name, d]));
        for (const doc of read) {
          const existing = byName.get(doc.name);
          if (existing) {
            // Re-dropping a name refreshes its text; if the author picked a target for
            // this batch, apply it (they're explicitly re-bucketing) — else keep choices.
            const category = opts.category ?? existing.category;
            byName.set(doc.name, {
              ...existing,
              text: doc.text,
              category,
              triaged: category !== "select" ? true : existing.triaged,
              useDraft: opts.useDraft ?? existing.useDraft,
              useRag: opts.useRag ?? existing.useRag,
            });
          } else {
            byName.set(doc.name, toCreatorDoc(doc, opts));
          }
        }
        return Array.from(byName.values());
      });
    },
    [],
  );

  const removeDoc = useCallback(
    (name: string) => setDocs((prev) => prev.filter((d) => d.name !== name)),
    [],
  );
  const toggleDocUse = useCallback(
    (name: string, key: DocUse) =>
      setDocs((prev) =>
        prev.map((d) => (d.name === name ? { ...d, [key]: !(d[key] ?? false) } : d)),
      ),
    [],
  );
  // Bulk select/deselect one use across every doc — the only workable control once a
  // batch of dozens is in the panel.
  const setAllDocUse = useCallback(
    (key: DocUse, value: boolean) =>
      setDocs((prev) => prev.map((d) => ({ ...d, [key]: value }))),
    [],
  );
  const setDocCategory = useCallback(
    (name: string, category: DocCategory) =>
      setDocs((prev) => prev.map((d) => (d.name === name ? { ...d, category } : d))),
    [],
  );

  // ---- agentic actions ----
  // Triage streams per file: each `item` event fills one row as it's classified,
  // so the panel sorts documents in front of the author instead of all at once.
  const triage = useCallback(async () => {
    // Only sweep the Uncategorized leftovers — files the author (or a prior triage)
    // already bucketed keep their category.
    const withText = docs.filter((d) => d.text && d.category === "select");
    if (withText.length === 0) return;
    triageAbort.current?.abort();
    const ac = new AbortController();
    triageAbort.current = ac;
    setTriaging(true);
    setError(null);
    setTriageActive(null);
    try {
      for await (const ev of api.triageDocumentsStream(
        withText.map((d) => ({ name: d.name, text: d.text })),
        editId,
        ac.signal,
      )) {
        if (ev.type === "status") {
          setTriageActive({ name: ev.name, index: ev.index, total: ev.total });
        } else if (ev.type === "item") {
          setDocs((prev) => applyTriage(prev, [ev.item]));
        } else if (ev.type === "error") {
          setError(ev.message);
        }
      }
    } catch (e) {
      if (!ac.signal.aborted) setError(messageOf(e));
    } finally {
      if (triageAbort.current === ac) triageAbort.current = null;
      setTriaging(false);
      setTriageActive(null);
    }
  }, [docs, editId]);

  const generatePrimer = useCallback(async () => {
    const premise = fields.premise.trim();
    if (!premise) return;
    setGeneratingPrimer(true);
    setError(null);
    try {
      const { worldPrimer } = await api.generateWorldPrimer({
        premise,
        docsOverview: draftGrounding(docs),
      });
      setFields((prev) => ({ ...prev, worldPrimer }));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setGeneratingPrimer(false);
    }
  }, [fields.premise, docs]);

  /**
   * Draft the world's style guide from the premise — the sibling of `generatePrimer`.
   *
   * An empty answer is left alone rather than written in: the agent returns `{}` for an
   * unreachable model, an unusable reply, or a world it could not read, and overwriting the
   * author's existing blocks with nothing in any of those cases would be the one outcome
   * they cannot undo.
   */
  const generateStyle = useCallback(async () => {
    const premise = fields.premise.trim();
    if (!premise) return;
    setGeneratingStyle(true);
    setError(null);
    try {
      const { styleBlocks } = await api.generateStyleGuide({
        premise,
        docsOverview: draftGrounding(docs),
      });
      if (Object.keys(styleBlocks ?? {}).length) {
        setFields((prev) => ({ ...prev, styleBlocks }));
      }
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setGeneratingStyle(false);
    }
  }, [fields.premise, docs]);

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
      return await commitWorld(
        { editId, fields, stats, statsOriginal, docs, existingDocs },
        setProgress,
      );
    } catch (e) {
      setError(messageOf(e));
      return null;
    } finally {
      setCommitting(false);
      setProgress(null);
    }
  }, [editId, fields, stats, statsOriginal, docs, existingDocs]);

  // ---- create + build (the Build-world dialog drives this) ----
  // The world is persisted first, then populated with the stream folded into `build`
  // so the dialog can show it happening. The id is held here (not returned early) so
  // the author only leaves for the world once the run reports `done`.
  const [build, setBuild] = useState<BuildState>(emptyBuild);
  const [builtId, setBuiltId] = useState<string | null>(null);
  const buildAbort = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      buildAbort.current?.abort();
    },
    [],
  );

  const createAndBuild = useCallback(
    async (options: PopulateOptions): Promise<{ id: string | null; state: BuildState }> => {
      setBuild({ ...emptyBuild(), phase: "creating", step: "Creating the world…" });
      setBuiltId(null);
      const id = await commit();
      if (!id) {
        const failed: BuildState = {
          ...emptyBuild(),
          phase: "failed",
          error: "The world could not be created.",
        };
        setBuild(failed);
        return { id: null, state: failed };
      }
      setBuiltId(id);
      if (!willBuild(options)) {
        const skipped: BuildState = { ...emptyBuild(), phase: "done" };
        setBuild(skipped);
        return { id, state: skipped };
      }
      buildAbort.current?.abort();
      const ac = new AbortController();
      buildAbort.current = ac;
      const state = await runPopulate(id, options, draftGrounding(docs), setBuild, ac.signal);
      return { id, state };
    },
    [commit, docs],
  );

  /** Stop an in-flight build. What already landed stays — the world is not rolled back. */
  const stopBuild = useCallback(() => {
    buildAbort.current?.abort();
    buildAbort.current = null;
  }, []);

  const resetBuild = useCallback(() => {
    buildAbort.current?.abort();
    buildAbort.current = null;
    setBuild(emptyBuild());
    setBuiltId(null);
  }, []);

  const budget = useMemo(
    () => budgetFor({ worldPrimer: fields.worldPrimer, draftDocs: draftDocTexts(docs) }),
    [fields.worldPrimer, docs],
  );
  // What the author's context files are classified as — the dialog says which people
  // and places the build will make from them, so nothing is a surprise.
  const sourceFiles = useMemo(
    () => ({
      characters: docs.filter((d) => d.category === "character" && d.text).length,
      settings: docs.filter((d) => d.category === "setting" && d.text).length,
      lore: docs.filter((d) => !["character", "setting"].includes(d.category) && d.text).length,
    }),
    [docs],
  );
  const statsOriginalKeys = useMemo(
    () => new Set(statsOriginal.map((s) => s.key)),
    [statsOriginal],
  );

  // Re-embed the world's whole corpus, streaming "Embedding i / N" progress so the
  // author sees the conversion happen and the resulting indexed count.
  const reembed = useCallback(async () => {
    if (!editId) return;
    setReembedding(true);
    setReembedProgress("Starting…");
    let available = true;
    try {
      for await (const ev of api.reindexCorpusStream(editId)) {
        if (ev.stage === "embedding") {
          setReembedProgress(`Embedding ${ev.index} / ${ev.total}: ${ev.name}`);
        } else if (ev.stage === "done") {
          available = ev.available;
        }
      }
      const status = await api.getRagStatus(editId).catch(() => null);
      if (status) setRagStatus(status);
      setReembedProgress(
        available ? `Embedded ${status?.indexed ?? 0} entries` : "Vector store unavailable",
      );
    } catch {
      setReembedProgress("Re-embed failed");
    } finally {
      setReembedding(false);
    }
  }, [editId]);

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
    setAllDocUse,
    setDocCategory,
    /** The Draft-selected context files as one bounded grounding string (or undefined). */
    docsOverview: () => draftGrounding(docs),
    budget,
    sourceFiles,
    isValid: isCreatorValid(fields),
    loading,
    generatingPrimer,
    generateStyle,
    generatingStyle,
    triaging,
    triageActive,
    committing,
    progress,
    error,
    ragStatus,
    reembedding,
    reembedProgress,
    reembed,
    triage,
    generatePrimer,
    commit,
    /** Live state of the create-time world build (rendered by `BuildWorldModal`). */
    build,
    /** The id of the world created by `createAndBuild` (available before the build ends). */
    builtId,
    createAndBuild,
    stopBuild,
    resetBuild,
  };
}
