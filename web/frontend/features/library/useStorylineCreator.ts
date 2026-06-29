"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  type CommitEntityPatch,
  type CreatorDoc,
  type CreatorFields,
  draftDocTexts,
  fieldsFromStoryline,
  fromContextDocument,
  isCreatorValid,
  type PlanConcepts,
  renderProposalImages,
  toCreatorDoc,
  type TriageActive,
  type UploadDefaults,
  upsertAt,
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

  const [imagesAvailable, setImagesAvailable] = useState(false);
  const [generateImages, setGenerateImages] = useState(false);

  const [loading, setLoading] = useState(Boolean(editId));
  const [drafting, setDrafting] = useState(false);
  const [generatingPrimer, setGeneratingPrimer] = useState(false);
  const [triaging, setTriaging] = useState(false);
  const [triageActive, setTriageActive] = useState<TriageActive | null>(null);
  const [building, setBuilding] = useState(false);
  const [buildingImages, setBuildingImages] = useState(false);
  const [buildStage, setBuildStage] = useState<string | null>(null);
  const [planConcepts, setPlanConcepts] = useState<PlanConcepts | null>(null);
  const [committing, setCommitting] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // RAG corpus (vector store) status + the live re-embed action (edit mode).
  const [ragStatus, setRagStatus] = useState<{ available: boolean; indexed: number } | null>(null);
  const [reembedding, setReembedding] = useState(false);
  const [reembedProgress, setReembedProgress] = useState<string | null>(null);

  // Abort in-flight streams when the component unmounts (or a new run starts).
  const buildAbort = useRef<AbortController | null>(null);
  const triageAbort = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      buildAbort.current?.abort();
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

  // Detect whether ComfyUI is configured so image generation can be offered.
  useEffect(() => {
    let cancelled = false;
    void api
      .getSettings()
      .then((s) => {
        if (cancelled) return;
        const ok = Boolean(s.comfy?.baseUrl?.trim());
        setImagesAvailable(ok);
        setGenerateImages(ok); // default on when available
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

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

  // Patch the displayed cast/settings in place (used by both the live image render
  // during build and the commit) — e.g. once a portrait / scene-art URL lands.
  const applyEntityPatch = useCallback(
    (e: CommitEntityPatch) =>
      setProposed((p) => {
        if (!p) return p;
        if (e.type === "character") {
          return {
            ...p,
            characters: p.characters.map((c, i) => (i === e.index ? { ...c, ...e.patch } : c)),
          };
        }
        return { ...p, settings: p.settings.map((s, i) => (i === e.index ? { ...s, ...e.patch } : s)) };
      }),
    [],
  );

  // The world build streams: metadata fills the left fields, the blueprint seeds
  // skeleton cards (planConcepts), and each character/setting event appends to the
  // proposal so the right column fills in live. `done` swaps in the canonical world.
  // Then, when ComfyUI is available, portraits + scene art render live into the cards.
  const build = useCallback(async () => {
    const s = seed.trim();
    const docsOverview = draftGrounding(docs);
    // The cast/settings are built ONLY from the docs categorized as such — one
    // entity per doc, nothing invented.
    const characterDocs = docs
      .filter((d) => d.category === "character" && d.text)
      .map((d) => ({ name: d.name, text: d.text }));
    const settingDocs = docs
      .filter((d) => d.category === "setting" && d.text)
      .map((d) => ({ name: d.name, text: d.text }));
    if (!s && !docsOverview && characterDocs.length === 0 && settingDocs.length === 0) {
      setError(
        "Add a one-sentence seed, drop context files, or attach characters/settings to build from.",
      );
      return;
    }
    buildAbort.current?.abort();
    const ac = new AbortController();
    buildAbort.current = ac;
    setBuilding(true);
    setBuildingImages(false);
    setError(null);
    setBuildStage(null);
    setProposed(null);
    setPlanConcepts(null);
    // Accumulate the storyline core across events so `plan` can seed the proposal.
    const meta = { title: "", genre: "", tagline: "", premise: "", worldPrimer: "" };
    let finalWorld: ProposedWorld | null = null;
    try {
      for await (const ev of api.buildWorldStream(
        { seed: s || undefined, docsOverview, storylineId: editId, characterDocs, settingDocs },
        ac.signal,
      )) {
        switch (ev.type) {
          case "status":
            setBuildStage(ev.message);
            break;
          case "meta":
            meta.title = ev.title;
            meta.genre = ev.genre;
            meta.tagline = ev.tagline;
            meta.premise = ev.premise;
            setFields((prev) => ({
              ...prev,
              title: ev.title || prev.title,
              genre: ev.genre || prev.genre,
              tagline: ev.tagline || prev.tagline,
              premise: ev.premise || prev.premise,
            }));
            break;
          case "primer":
            meta.worldPrimer = ev.worldPrimer;
            setFields((prev) => ({ ...prev, worldPrimer: ev.worldPrimer || prev.worldPrimer }));
            break;
          case "plan":
            if (ev.stats.length) setStats(ev.stats);
            setPlanConcepts({ characters: ev.characters, settings: ev.settings });
            setProposed({ storyline: { ...meta }, stats: ev.stats, characters: [], settings: [] });
            break;
          case "character":
            setProposed((p) =>
              p ? { ...p, characters: upsertAt(p.characters, ev.index, ev.character) } : p,
            );
            break;
          case "setting":
            setProposed((p) =>
              p ? { ...p, settings: upsertAt(p.settings, ev.index, ev.setting) } : p,
            );
            break;
          case "done":
            finalWorld = ev.world;
            setProposed(ev.world);
            if (ev.world.stats.length) setStats(ev.world.stats);
            setFields((prev) => ({
              ...prev,
              title: ev.world.storyline.title || prev.title,
              genre: ev.world.storyline.genre || prev.genre,
              tagline: ev.world.storyline.tagline || prev.tagline,
              premise: ev.world.storyline.premise || prev.premise,
              worldPrimer: ev.world.storyline.worldPrimer || prev.worldPrimer,
            }));
            break;
          case "error":
            setError(ev.message);
            break;
        }
      }

      // Text build done → render portraits + scene art live whenever ComfyUI is
      // available (the build now produces images too, not just the commit). Verify
      // the server is actually *reachable* first — `imagesAvailable` only means a URL
      // is configured, so without this a stopped ComfyUI would 502 on every entity.
      const hasImageWork =
        Boolean(finalWorld) &&
        ((finalWorld?.characters.length ?? 0) > 0 || (finalWorld?.settings.length ?? 0) > 0);
      if (finalWorld && hasImageWork && imagesAvailable && generateImages && !ac.signal.aborted) {
        const reachable = await api
          .checkComfyStatus({})
          .then((st) => Boolean(st?.ok))
          .catch(() => false);
        if (reachable && !ac.signal.aborted) {
          setBuilding(false); // switch the panel to review mode while images render in
          setBuildingImages(true);
          await renderProposalImages(finalWorld, applyEntityPatch, setBuildStage, ac.signal);
        }
      }
    } catch (e) {
      if (!ac.signal.aborted) setError(messageOf(e));
    } finally {
      if (buildAbort.current === ac) buildAbort.current = null;
      setBuilding(false);
      setBuildingImages(false);
      setBuildStage(null);
    }
  }, [seed, docs, editId, imagesAvailable, generateImages, applyEntityPatch]);

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
  const discardProposal = useCallback(() => {
    setProposed(null);
    setPlanConcepts(null);
  }, []);

  // ---- commit ----
  const commit = useCallback(async (): Promise<string | null> => {
    if (!isCreatorValid(fields)) {
      setError("Give the world a title first.");
      return null;
    }
    // Stop any still-running build-time image render; commit persists what's there
    // and renders any that are still missing (no double-render, no race).
    buildAbort.current?.abort();
    setBuildingImages(false);
    setCommitting(true);
    setError(null);
    setProgress(null);
    try {
      const id = await commitWorld(
        {
          editId,
          fields,
          stats,
          statsOriginal,
          proposed,
          docs,
          existingDocs,
          generateImages: imagesAvailable && generateImages,
        },
        setProgress,
        // Patch the displayed cast/settings as each image renders, so previews
        // pop into the right column live during "Create World".
        applyEntityPatch,
      );
      return id;
    } catch (e) {
      setError(messageOf(e));
      return null;
    } finally {
      setCommitting(false);
      setProgress(null);
    }
  }, [
    editId,
    fields,
    stats,
    statsOriginal,
    proposed,
    docs,
    existingDocs,
    imagesAvailable,
    generateImages,
    applyEntityPatch,
  ]);

  const budget = useMemo(
    () => budgetFor({ worldPrimer: fields.worldPrimer, draftDocs: draftDocTexts(docs) }),
    [fields.worldPrimer, docs],
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
    setDocCategory,
    seed,
    setSeed,
    proposed,
    planConcepts,
    updateProposedCharacter,
    removeProposedCharacter,
    updateProposedSetting,
    removeProposedSetting,
    discardProposal,
    imagesAvailable,
    generateImages,
    setGenerateImages,
    budget,
    isValid: isCreatorValid(fields),
    loading,
    drafting,
    generatingPrimer,
    triaging,
    triageActive,
    building,
    buildingImages,
    buildStage,
    committing,
    progress,
    error,
    ragStatus,
    reembedding,
    reembedProgress,
    reembed,
    triage,
    draftMeta,
    generatePrimer,
    build,
    commit,
  };
}
