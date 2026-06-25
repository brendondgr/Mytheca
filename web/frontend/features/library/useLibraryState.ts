"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  AI_BRANCHES,
  AI_CHARACTERS,
  AI_SCENARIOS,
  AI_SETTINGS,
  resolveScenario,
} from "@/lib/seed-data";
import * as api from "@/lib/api";
import { concatDocs, docsForDraft } from "@/lib/readDocs";
import { DEFAULT_SEAL_COLOR, DEFAULT_SEAL_SYMBOL } from "@/lib/seals";
import type { Character, Scenario, Setting, Storyline } from "@/lib/types";
import {
  DEFAULT_DRAFTS,
  STORYLINE_DRAFT,
  isDraftValid,
  isStorylineDraftValid,
  pickUnused,
  type Draft,
  type EditorMode,
  type EntityType,
  type ModalState,
} from "@/features/library/editor";

export type LibraryTabKey =
  | "scenarios"
  | "characters"
  | "settings"
  | "storylines";

function messageOf(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

/** Wrap a summary from the API into the nested Storyline shape the UI holds. */
function emptyStoryline(summary: api.StorylineSummary): Storyline {
  return { ...summary, characters: [], settings: [], scenarios: [] };
}

export function useLibraryState() {
  // State is storyline-scoped: we hold every storyline and an "active" id; the
  // cast/settings/scenarios shown are the active storyline's own. Data is loaded
  // from the backend on mount and each storyline's children are hydrated lazily.
  const [storylines, setStorylines] = useState<Storyline[]>([]);
  const [activeStorylineId, setActiveStorylineId] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  // Ids whose children have already been fetched (avoids refetching on switch).
  const hydrated = useRef<Set<string>>(new Set());

  const activeStoryline =
    storylines.find((s) => s.id === activeStorylineId) ?? storylines[0];
  const characters = useMemo(
    () => activeStoryline?.characters ?? [],
    [activeStoryline],
  );
  const settings = useMemo(
    () => activeStoryline?.settings ?? [],
    [activeStoryline],
  );
  const scenarios = useMemo(
    () => activeStoryline?.scenarios ?? [],
    [activeStoryline],
  );

  // Mutate the active storyline's collections. The thin setX wrappers below let
  // every existing `setCharacters((cs) => …)` call-site stay unchanged.
  function updateActive(updater: (sl: Storyline) => Storyline) {
    setStorylines((sls) =>
      sls.map((sl) => (sl.id === activeStorylineId ? updater(sl) : sl)),
    );
  }
  const setCharacters = (fn: (cs: Character[]) => Character[]) =>
    updateActive((sl) => ({ ...sl, characters: fn(sl.characters) }));
  const setSettings = (fn: (ss: Setting[]) => Setting[]) =>
    updateActive((sl) => ({ ...sl, settings: fn(sl.settings) }));
  const setScenarios = (fn: (xs: Scenario[]) => Scenario[]) =>
    updateActive((sl) => ({ ...sl, scenarios: fn(sl.scenarios) }));

  const [tab, setTab] = useState<LibraryTabKey>("scenarios");
  const [featuredId, setFeaturedId] = useState<string>("");
  const [query, setQuery] = useState("");
  const [expandedCharId, setExpandedCharId] = useState<string | null>(null);

  const [menuOpen, setMenuOpen] = useState(false);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [draft, setDraftState] = useState<Draft>({});
  const [generating, setGenerating] = useState(false);
  // Separate flag so the World Primer "Generate" button spins independently of
  // the "Draft with Velora" metadata draft.
  const [generatingPrimer, setGeneratingPrimer] = useState(false);
  // Character Creator: independent spinners for portrait prompts, portrait render,
  // stat proposal, and stat-apply, so each button spins on its own.
  const [generatingPrompts, setGeneratingPrompts] = useState(false);
  const [generatingPortrait, setGeneratingPortrait] = useState(false);
  const [generatingStats, setGeneratingStats] = useState(false);
  const [applyingStats, setApplyingStats] = useState(false);
  const [profileId, setProfileId] = useState<string | null>(null);
  const generateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- data loading ----
  /** Fetch a storyline's children once and merge them in; returns its scenarios. */
  async function hydrateStoryline(id: string): Promise<Scenario[]> {
    if (!id) return [];
    if (hydrated.current.has(id)) {
      return storylines.find((s) => s.id === id)?.scenarios ?? [];
    }
    const [chars, setts, scens] = await Promise.all([
      api.listCharacters(id),
      api.listSettings(id),
      api.listScenarios(id),
    ]);
    hydrated.current.add(id);
    setStorylines((sls) =>
      sls.map((sl) =>
        sl.id === id ? { ...sl, characters: chars, settings: setts, scenarios: scens } : sl,
      ),
    );
    return scens;
  }

  // No synchronous setState here: `loading` defaults to true for the first load,
  // and retry() sets it (from an event handler, not the effect).
  async function loadInitial() {
    try {
      const summaries = await api.listStorylines();
      if (summaries.length === 0) {
        setStorylines([]);
        setActiveStorylineId("");
        return;
      }
      const firstId = summaries[0].id;
      const [chars, setts, scens] = await Promise.all([
        api.listCharacters(firstId),
        api.listSettings(firstId),
        api.listScenarios(firstId),
      ]);
      hydrated.current = new Set([firstId]);
      setStorylines(
        summaries.map((s) =>
          s.id === firstId
            ? { ...emptyStoryline(s), characters: chars, settings: setts, scenarios: scens }
            : emptyStoryline(s),
        ),
      );
      setActiveStorylineId(firstId);
      setFeaturedId(scens[0]?.id ?? "");
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setLoading(false);
    }
  }

  function retry() {
    setLoading(true);
    setError(null);
    void loadInitial();
  }

  useEffect(() => {
    // Canonical mount data-fetch: loadInitial sets state only after awaiting the
    // API. The rule targets synchronous setState; a typed fetch layer (e.g.
    // TanStack Query) is the deferred long-term home for this (docs/architecture.md).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadInitial();
  }, []);

  // ---- derived ----
  const resolvedScenarios = useMemo(
    () => scenarios.map((s) => resolveScenario(s, characters, settings)),
    [scenarios, characters, settings],
  );
  const q = query.trim().toLowerCase();
  const matches = (...values: string[]) =>
    !q || values.some((v) => v.toLowerCase().includes(q));
  const filteredCharacters = characters.filter((c) =>
    matches(c.name, c.role, c.traits),
  );
  const filteredSettings = settings.filter((s) =>
    matches(s.name, s.type, s.desc),
  );
  const filteredScenarios = resolvedScenarios.filter((s) =>
    matches(s.title, s.genre, s.goal),
  );
  const featured =
    resolvedScenarios.find((s) => s.id === featuredId) ?? resolvedScenarios[0];
  const featuredIndex = Math.max(
    0,
    scenarios.findIndex((s) => s.id === featuredId),
  );

  // ---- read interactions ----
  function toggleExpand(id: string) {
    setExpandedCharId((prev) => (prev === id ? null : id));
  }
  function cycleFeatured(direction: number) {
    if (scenarios.length === 0) return;
    const i = scenarios.findIndex((s) => s.id === featuredId);
    const base = i < 0 ? 0 : i;
    const next =
      scenarios[(base + direction + scenarios.length) % scenarios.length];
    setFeaturedId(next.id);
  }

  // ---- storyline switching ----
  function resetForStoryline(firstScenarioId: string) {
    setFeaturedId(firstScenarioId);
    setExpandedCharId(null);
    setQuery("");
    setTab("scenarios");
    setMenuOpen(false);
  }
  async function switchStoryline(id: string) {
    if (id === activeStorylineId) {
      setMenuOpen(false);
      return;
    }
    setActiveStorylineId(id);
    setError(null);
    try {
      const scens = await hydrateStoryline(id);
      resetForStoryline(scens[0]?.id ?? "");
    } catch (e) {
      setError(messageOf(e));
      resetForStoryline("");
    }
  }
  /** Open the write-first storyline create modal (StorylineModal) on a blank draft. */
  function openCreateStoryline() {
    setDraftState({ ...STORYLINE_DRAFT, _stats: [], _statsOriginal: [] });
    setError(null);
    setModal({ type: "storyline", mode: "manual", editId: null });
    setMenuOpen(false);
    setGenerating(false);
    setGeneratingPrimer(false);
  }
  /** Open the storyline modal in edit mode, prefilled from an existing storyline. */
  function editStoryline(id: string) {
    const sl = storylines.find((s) => s.id === id);
    if (!sl) return;
    setDraftState({
      title: sl.title,
      genre: sl.genre,
      tagline: sl.tagline ?? "",
      premise: sl.premise ?? "",
      worldPrimer: sl.worldPrimer ?? "",
      symbol: sl.symbol ?? DEFAULT_SEAL_SYMBOL,
      symbolColor: sl.symbolColor ?? DEFAULT_SEAL_COLOR,
      _stats: [],
      _statsOriginal: [],
    });
    setError(null);
    setModal({ type: "storyline", mode: "manual", editId: id });
    setMenuOpen(false);
    setGenerating(false);
    setGeneratingPrimer(false);
    // Load the world's universal stats; keep an original snapshot so submit can
    // diff into create/update/delete calls. Best-effort — failure just shows none.
    void api
      .listStatDefinitions(id)
      .then((defs) =>
        setDraftState((prev) => ({ ...prev, _stats: defs, _statsOriginal: defs })),
      )
      .catch(() => {});
  }

  // ---- storyline agentic authoring (real model calls via the backend) ----
  /** Draft title/genre/tagline/premise from the one-sentence seed (draft._prompt). */
  async function draftStoryline() {
    if (!modal || modal.type !== "storyline") return;
    const seed = (draft._prompt ?? "").trim();
    if (!seed) return;
    const docsOverview = draft._docFiles?.length
      ? concatDocs(docsForDraft(draft._docFiles))
      : undefined;
    setGenerating(true);
    setError(null);
    try {
      const drafted = await api.draftStoryline(seed, docsOverview);
      setDraftState((prev) => ({
        ...prev,
        title: drafted.title || prev.title,
        genre: drafted.genre || prev.genre,
        tagline: drafted.tagline || prev.tagline,
        premise: drafted.premise || prev.premise,
        _ai: true,
      }));
      // On mobile the seam is its own tab — drop back to the form to reveal fields.
      setModal((prev) => (prev ? { ...prev, mode: "manual" } : prev));
    } catch (e) {
      setError(messageOf(e)); // keep the modal open so the author can retry
    } finally {
      setGenerating(false);
    }
  }
  /** Generate the agent-facing World Primer from the current seed + premise. */
  async function generatePrimer() {
    if (!modal || modal.type !== "storyline") return;
    const premise = (draft.premise ?? "").trim();
    const seed = (draft._prompt ?? "").trim();
    if (!premise && !seed) return;
    const docsOverview = draft._docFiles?.length
      ? concatDocs(docsForDraft(draft._docFiles))
      : undefined;
    setGeneratingPrimer(true);
    setError(null);
    try {
      const { worldPrimer } = await api.generateWorldPrimer({
        premise: premise || undefined,
        seed: seed || undefined,
        docsOverview,
      });
      setDraftState((prev) => ({ ...prev, worldPrimer }));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setGeneratingPrimer(false);
    }
  }
  /** Persist the universal-stat edits: diff `_stats` vs the loaded snapshot. */
  async function persistStats(storylineId: string) {
    const current = (draft._stats ?? []).filter(
      (s) => s.key.trim() && s.displayName.trim(),
    );
    const original = draft._statsOriginal ?? [];
    const currentKeys = new Set(current.map((s) => s.key));
    const originalByKey = new Map(original.map((s) => [s.key, s]));
    // Deletes first (a loaded stat dropped from the list), then creates/updates.
    for (const o of original) {
      if (!currentKeys.has(o.key)) await api.deleteStatDefinition(storylineId, o.key);
    }
    for (const s of current) {
      const prev = originalByKey.get(s.key);
      const fields = {
        displayName: s.displayName,
        description: s.description,
        min: s.min,
        max: s.max,
        default: s.default,
        bands: s.bands,
        visibility: s.visibility,
        appliesTo: s.appliesTo,
        guidance: s.guidance,
      };
      if (!prev) {
        await api.createStatDefinition(storylineId, { key: s.key, ...fields });
      } else if (JSON.stringify(prev) !== JSON.stringify(s)) {
        await api.updateStatDefinition(storylineId, s.key, fields);
      }
    }
  }

  /** Create (or, when editing, update) the storyline from the modal draft. */
  async function submitStoryline() {
    if (!modal || modal.type !== "storyline") return;
    if (!isStorylineDraftValid(draft)) return;
    const editId = modal.editId;
    setPending(true);
    setError(null);
    const title = (draft.title ?? "").trim();
    const genre = draft.genre?.trim() || "Uncharted";
    const symbol = draft.symbol || DEFAULT_SEAL_SYMBOL;
    const symbolColor = draft.symbolColor || DEFAULT_SEAL_COLOR;
    try {
      if (editId) {
        // Edit: empty tagline/premise/primer are sent as "" so they can be cleared.
        const updated = await api.updateStoryline(editId, {
          title,
          genre,
          tagline: draft.tagline?.trim() ?? "",
          premise: draft.premise?.trim() ?? "",
          worldPrimer: draft.worldPrimer?.trim() ?? "",
          symbol,
          symbolColor,
        });
        // Spread over the existing storyline so its hydrated children survive.
        setStorylines((sls) =>
          sls.map((sl) => (sl.id === editId ? { ...sl, ...updated } : sl)),
        );
        await persistStats(editId);
      } else {
        const created = await api.createStoryline({
          title,
          genre,
          tagline: draft.tagline?.trim() || undefined,
          premise: draft.premise?.trim() || undefined,
          worldPrimer: draft.worldPrimer?.trim() || undefined,
          symbol,
          symbolColor,
        });
        hydrated.current.add(created.id); // brand-new: no children to fetch
        await persistStats(created.id);
        setStorylines((sls) => [...sls, emptyStoryline(created)]);
        setActiveStorylineId(created.id);
        resetForStoryline("");
      }
      closeModal();
    } catch (e) {
      setError(messageOf(e)); // keep the modal open so the user can retry
    } finally {
      setPending(false);
    }
  }

  // ---- character agentic authoring (real model + ComfyUI calls via backend) ----
  /** Draft a full character (fields + base-identity prose) from the seed. */
  async function draftCharacter() {
    if (!modal || modal.type !== "character") return;
    const seed = (draft._prompt ?? "").trim();
    if (!seed) return;
    const docsOverview = draft._docFiles?.length
      ? concatDocs(docsForDraft(draft._docFiles))
      : undefined;
    setGenerating(true);
    setError(null);
    try {
      const d = await api.draftCharacter(seed, docsOverview, activeStorylineId || undefined);
      setDraftState((prev) => ({
        ...prev,
        name: d.name || prev.name,
        role: d.role || prev.role,
        traits: d.traits || prev.traits,
        speech: d.speech || prev.speech,
        goal: d.goal || prev.goal,
        secret: d.secret || prev.secret,
        appearance: d.appearance || prev.appearance,
        background: d.background || prev.background,
        personality: d.personality || prev.personality,
        color: d.color || prev.color,
        _ai: true,
      }));
      // On mobile the seam is its own tab — drop back to the form to reveal fields.
      setModal((prev) => (prev ? { ...prev, mode: "manual" } : prev));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setGenerating(false);
    }
  }
  /** Write the watercolor positive/negative portrait prompts (editable after). */
  async function generatePortraitPrompts() {
    if (!modal || modal.type !== "character") return;
    setGeneratingPrompts(true);
    setError(null);
    try {
      const r = await api.generatePortraitPrompts({
        name: draft.name,
        role: draft.role,
        appearance: draft.appearance,
        traits: draft.traits,
        personality: draft.personality,
      });
      setDraftState((prev) => ({
        ...prev,
        _portraitPositive: r.positive,
        _portraitNegative: r.negative,
      }));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setGeneratingPrompts(false);
    }
  }
  /** Render the portrait via ComfyUI from the current prompts → draft.portrait. */
  async function generatePortrait() {
    if (!modal || modal.type !== "character") return;
    const positive = (draft._portraitPositive ?? "").trim();
    if (!positive) return;
    setGeneratingPortrait(true);
    setError(null);
    try {
      const { portrait } = await api.generatePortrait({
        positive,
        negative: draft._portraitNegative?.trim() || undefined,
      });
      setDraftState((prev) => ({ ...prev, portrait }));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setGeneratingPortrait(false);
    }
  }
  /** Propose starting stats keyed to the active world's stat schema (review only). */
  async function proposeStartingStats() {
    if (!modal || modal.type !== "character" || !activeStorylineId) return;
    setGeneratingStats(true);
    setError(null);
    try {
      const { proposals } = await api.proposeStartingStats({
        storylineId: activeStorylineId,
        name: draft.name,
        role: draft.role,
        traits: draft.traits,
        personality: draft.personality,
        background: draft.background,
      });
      setDraftState((prev) => ({ ...prev, _startingStats: proposals }));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setGeneratingStats(false);
    }
  }
  /** Apply the proposed starting stats to an existing character (the "Save" action). */
  async function applyStartingStats(characterId: string) {
    const proposals = draft._startingStats ?? [];
    if (!characterId || proposals.length === 0) return;
    const values: Record<string, number> = {};
    for (const p of proposals) values[p.key] = p.value;
    setApplyingStats(true);
    setError(null);
    try {
      await api.setCharacterStats(characterId, values);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setApplyingStats(false);
    }
  }

  // ---- storyline delete (confirm → delete → reselect if it was active) ----
  const [deleteStorylineId, setDeleteStorylineId] = useState<string | null>(null);
  const storylineToDelete =
    storylines.find((s) => s.id === deleteStorylineId) ?? null;

  function requestDeleteStoryline(id: string) {
    setDeleteStorylineId(id);
    setError(null);
    setMenuOpen(false);
  }
  function cancelDeleteStoryline() {
    if (pending) return;
    setError(null);
    setDeleteStorylineId(null);
  }
  async function confirmDeleteStoryline() {
    const id = deleteStorylineId;
    if (!id) return;
    setPending(true);
    setError(null);
    try {
      await api.deleteStoryline(id);
      hydrated.current.delete(id);
      const remaining = storylines.filter((s) => s.id !== id);
      setStorylines(remaining);
      setDeleteStorylineId(null);
      // If the active world was deleted, fall back to the first remaining one.
      if (id === activeStorylineId) {
        const next = remaining[0];
        setActiveStorylineId(next?.id ?? "");
        if (next) {
          const scens = await hydrateStoryline(next.id);
          resetForStoryline(scens[0]?.id ?? "");
        } else {
          resetForStoryline("");
        }
      }
    } catch (e) {
      setError(messageOf(e)); // keep the confirm open so the user can retry
    } finally {
      setPending(false);
    }
  }

  // ---- modal lifecycle ----
  function setDraft(key: keyof Draft, value: unknown) {
    setDraftState((prev) => ({ ...prev, [key]: value }));
  }
  function setMode(mode: EditorMode) {
    setModal((prev) => (prev ? { ...prev, mode } : prev));
  }
  function closeModal() {
    if (generateTimer.current) clearTimeout(generateTimer.current);
    setGenerating(false);
    setGeneratingPrimer(false);
    setGeneratingPrompts(false);
    setGeneratingPortrait(false);
    setGeneratingStats(false);
    setApplyingStats(false);
    setError(null);
    setModal(null);
  }
  function openCreate(type: EntityType) {
    setDraftState({ ...DEFAULT_DRAFTS[type] });
    setError(null);
    setModal({ type, mode: "manual", editId: null });
    setMenuOpen(false);
    setGenerating(false);
  }
  function editCharacter(id: string) {
    const c = characters.find((x) => x.id === id);
    if (!c) return;
    setDraftState({
      name: c.name, role: c.role, color: c.color, traits: c.traits,
      speech: c.speech, goal: c.goal, secret: c.secret,
      appearance: c.appearance ?? "", background: c.background ?? "",
      personality: c.personality ?? "", portrait: c.portrait ?? null,
    });
    setError(null);
    setModal({ type: "character", mode: "manual", editId: id });
    setProfileId(null);
  }
  function editSetting(id: string) {
    const s = settings.find((x) => x.id === id);
    if (!s) return;
    setDraftState({ name: s.name, type: s.type, desc: s.desc });
    setError(null);
    setModal({ type: "setting", mode: "manual", editId: id });
  }
  function editScenario(id: string) {
    const s = scenarios.find((x) => x.id === id);
    if (!s) return;
    setDraftState({ title: s.title, genre: s.genre, tone: s.tone, goal: s.goal, cast: [...s.castIds], settingId: s.settingId, branches: [...s.branches] });
    setError(null);
    setModal({ type: "scenario", mode: "manual", editId: id });
  }
  function toggleDraftCast(id: string) {
    setDraftState((prev) => {
      const cast = prev.cast ?? [];
      return { ...prev, cast: cast.includes(id) ? cast.filter((x) => x !== id) : [...cast, id] };
    });
  }

  // ---- profile + begin ----
  function openProfile(id: string) {
    setProfileId(id);
  }
  function closeProfile() {
    setProfileId(null);
  }
  function openBegin(id: string) {
    setFeaturedId(id);
    setModal({ type: "begin", mode: "manual", editId: null });
    setMenuOpen(false);
  }

  // ---- agentic fake-draft (client-only; no model call) ----
  function generate() {
    if (!modal || modal.type === "begin" || modal.type === "storyline") return;
    const type = modal.type;
    setGenerating(true);
    if (generateTimer.current) clearTimeout(generateTimer.current);
    generateTimer.current = setTimeout(() => {
      let next: Draft;
      if (type === "character") {
        next = { ...pickUnused(AI_CHARACTERS, characters.map((c) => c.name), (c) => c.name), _ai: true };
      } else if (type === "setting") {
        next = { ...pickUnused(AI_SETTINGS, settings.map((s) => s.name), (s) => s.name), _ai: true };
      } else if (type === "scenario") {
        const base = pickUnused(AI_SCENARIOS, scenarios.map((s) => s.title), (s) => s.title);
        const ids = [...characters].sort(() => Math.random() - 0.5).slice(0, 3).map((c) => c.id);
        const settingId = settings[Math.floor(Math.random() * settings.length)]?.id ?? "";
        next = { ...base, cast: ids, settingId, branches: AI_BRANCHES.slice(0, 3).map((b) => ({ ...b })), _ai: true };
      } else {
        next = { ...AI_BRANCHES[Math.floor(Math.random() * AI_BRANCHES.length)], _ai: true };
      }
      setDraftState(next);
      setGenerating(false);
      setModal((prev) => (prev ? { ...prev, mode: "manual" } : prev));
    }, 850);
  }

  // ---- submit / delete (await the API, then splice the returned entity) ----
  async function submit() {
    if (!modal || modal.type === "begin" || modal.type === "storyline") return;
    const { type, editId } = modal;
    const d = draft;
    if (!isDraftValid(type, d)) return;
    setPending(true);
    setError(null);
    try {
      if (type === "character") {
        const body = {
          name: (d.name ?? "").trim(),
          role: d.role?.trim() || "Character",
          color: d.color || "#8E2B1C",
          traits: d.traits?.trim() || "Newly forged · unwritten",
          speech: d.speech?.trim() || "—",
          goal: d.goal?.trim() || "—",
          secret: d.secret?.trim() || "—",
          // Base-identity prose + portrait: empty → null (clears on edit, unset on create).
          appearance: d.appearance?.trim() || null,
          background: d.background?.trim() || null,
          personality: d.personality?.trim() || null,
          portrait: d.portrait || null,
        };
        // Proposed starting stats are applied with the save (the "save" the user
        // opted into); keyed/clamped server-side, skipped when there are none.
        const statValues = Object.fromEntries(
          (d._startingStats ?? []).map((p) => [p.key, p.value]),
        );
        if (editId) {
          const updated = await api.updateCharacter(editId, body);
          if (Object.keys(statValues).length) await api.setCharacterStats(editId, statValues);
          setCharacters((cs) => cs.map((c) => (c.id === editId ? updated : c)));
        } else {
          const created = await api.createCharacter(activeStorylineId, body);
          if (Object.keys(statValues).length) await api.setCharacterStats(created.id, statValues);
          setCharacters((cs) => [...cs, created]);
          setTab("characters");
          setExpandedCharId(created.id);
        }
      } else if (type === "setting") {
        const body = { name: (d.name ?? "").trim(), type: d.type || "Social Hub", desc: d.desc?.trim() || "A place yet to be described." };
        if (editId) {
          const updated = await api.updateSetting(editId, body);
          setSettings((xs) => xs.map((x) => (x.id === editId ? updated : x)));
        } else {
          const created = await api.createSetting(activeStorylineId, body);
          setSettings((xs) => [...xs, created]);
          setTab("settings");
        }
      } else if (type === "scenario") {
        const body = {
          title: (d.title ?? "").trim(),
          genre: d.genre?.trim() || "Custom",
          tone: d.tone?.trim() || "Unset",
          goal: d.goal?.trim() || "Goal to be set.",
          castIds: [...(d.cast ?? [])],
          settingId: d.settingId ?? "",
          branches: [...(d.branches ?? [])],
        };
        if (editId) {
          const updated = await api.updateScenario(editId, body);
          setScenarios((xs) => xs.map((x) => (x.id === editId ? updated : x)));
        } else {
          const created = await api.createScenario(activeStorylineId, {
            ...body,
            opening: "A new scene awaits its first line of narration…",
          });
          setScenarios((xs) => [...xs, created]);
          setTab("scenarios");
          setFeaturedId(created.id);
        }
      }
      closeModal();
    } catch (e) {
      setError(messageOf(e)); // keep the modal open so the user can retry
    } finally {
      setPending(false);
    }
  }

  async function deleteEntity() {
    if (!modal || modal.type === "begin" || modal.type === "storyline") return;
    const { type, editId } = modal;
    if (!editId) return;
    setPending(true);
    setError(null);
    try {
      if (type === "character") {
        await api.deleteCharacter(editId);
        setCharacters((cs) => cs.filter((c) => c.id !== editId));
        // The backend is authoritative and prunes castIds server-side; mirror it
        // locally so the UI is consistent without a refetch.
        setScenarios((xs) => xs.map((sc) => ({ ...sc, castIds: sc.castIds.filter((id) => id !== editId) })));
      } else if (type === "setting") {
        await api.deleteSetting(editId);
        setSettings((xs) => xs.filter((x) => x.id !== editId));
      } else if (type === "scenario") {
        await api.deleteScenario(editId);
        setScenarios((xs) => xs.filter((x) => x.id !== editId));
        if (featuredId === editId) {
          setFeaturedId(scenarios.find((x) => x.id !== editId)?.id ?? "");
        }
      }
      closeModal();
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setPending(false);
    }
  }

  const profileChar = characters.find((c) => c.id === profileId) ?? null;

  return {
    storylines, activeStorylineId, activeStoryline, switchStoryline,
    openCreateStoryline, editStoryline, submitStoryline,
    draftStoryline, generatePrimer, generatingPrimer,
    // character agentic authoring
    draftCharacter, generatePortraitPrompts, generatePortrait,
    proposeStartingStats, applyStartingStats,
    generatingPrompts, generatingPortrait, generatingStats, applyingStats,
    requestDeleteStoryline, confirmDeleteStoryline, cancelDeleteStoryline,
    storylineToDelete,
    characters, settings, scenarios, resolvedScenarios,
    filteredCharacters, filteredSettings, filteredScenarios,
    tab, setTab,
    featured, featuredId, setFeaturedId, featuredIndex,
    query, setQuery,
    expandedCharId, toggleExpand,
    cycleFeatured,
    // data-loading status
    loading, error, pending, retry,
    counts: {
      characters: characters.length,
      settings: settings.length,
      scenarios: scenarios.length,
    },
    // editor
    menuOpen, setMenuOpen,
    modal, draft, generating,
    isEditing: Boolean(
      modal && modal.type !== "begin" && modal.type !== "storyline" && modal.editId != null,
    ),
    isValid:
      modal && modal.type !== "begin" && modal.type !== "storyline"
        ? isDraftValid(modal.type, draft)
        : false,
    // storyline-specific validity for StorylineModal's submit button
    isStorylineValid: isStorylineDraftValid(draft),
    openCreate, editCharacter, editSetting, editScenario,
    setDraft, setMode, toggleDraftCast, generate, submit, deleteEntity, closeModal,
    // profile + begin
    profileId, profileChar, openProfile, closeProfile, openBegin,
  };
}
