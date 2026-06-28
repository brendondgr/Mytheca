"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { resolveScenario } from "@/lib/seed-data";
import * as api from "@/lib/api";
import { concatDocs, docsForDraft } from "@/lib/readDocs";
import type { Character, Scenario, Setting, Storyline } from "@/lib/types";
import {
  DEFAULT_DRAFTS,
  isDraftValid,
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

/**
 * Cosmetically reflect the active storyline in the URL as `/{id}` without a Next
 * navigation (no remount, no extra fetch) — deep links still resolve via
 * `initialStorylineId` on a fresh load. SSR-guarded.
 */
function syncStorylineUrl(id: string) {
  if (typeof window !== "undefined" && id) {
    window.history.replaceState(window.history.state, "", `/${id}`);
  }
}

export function useLibraryState(initialStorylineId?: string) {
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
  // Character Creator: independent spinners for portrait prompts, portrait render,
  // stat proposal, and stat-apply, so each button spins on its own.
  const [generatingPrompts, setGeneratingPrompts] = useState(false);
  const [generatingPortrait, setGeneratingPortrait] = useState(false);
  const [generatingStats, setGeneratingStats] = useState(false);
  const [applyingStats, setApplyingStats] = useState(false);
  const [profileId, setProfileId] = useState<string | null>(null);

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
      // Deep-link target wins when it names a real storyline; else the first.
      const target =
        initialStorylineId && summaries.some((s) => s.id === initialStorylineId)
          ? initialStorylineId
          : summaries[0].id;
      const [chars, setts, scens] = await Promise.all([
        api.listCharacters(target),
        api.listSettings(target),
        api.listScenarios(target),
      ]);
      hydrated.current = new Set([target]);
      setStorylines(
        summaries.map((s) =>
          s.id === target
            ? { ...emptyStoryline(s), characters: chars, settings: setts, scenarios: scens }
            : emptyStoryline(s),
        ),
      );
      setActiveStorylineId(target);
      setFeaturedId(scens[0]?.id ?? "");
      syncStorylineUrl(target);
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
    syncStorylineUrl(id);
    setError(null);
    try {
      const scens = await hydrateStoryline(id);
      resetForStoryline(scens[0]?.id ?? "");
    } catch (e) {
      setError(messageOf(e));
      resetForStoryline("");
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
      // Auto-propose starting stats from the drafted fields (best-effort).
      if (activeStorylineId) {
        setGeneratingStats(true);
        try {
          const { proposals } = await api.proposeStartingStats({
            storylineId: activeStorylineId,
            name: d.name,
            role: d.role,
            traits: d.traits,
            personality: d.personality,
            background: d.background,
          });
          setDraftState((prev) => ({ ...prev, _startingStats: proposals }));
        } catch {
          // silent — stat proposal is best-effort; draft already succeeded
        } finally {
          setGeneratingStats(false);
        }
      }
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

  // ---- setting agentic authoring (real model + ComfyUI calls via backend) ----
  /** Draft a full setting (fields + §4.1 node metadata) from the seed. */
  async function draftSetting() {
    if (!modal || modal.type !== "setting") return;
    const seed = (draft._prompt ?? "").trim();
    if (!seed) return;
    const docsOverview = draft._docFiles?.length
      ? concatDocs(docsForDraft(draft._docFiles))
      : undefined;
    setGenerating(true);
    setError(null);
    try {
      const s = await api.draftSetting(seed, docsOverview, activeStorylineId || undefined);
      setDraftState((prev) => ({
        ...prev,
        name: s.name || prev.name,
        type: s.type || prev.type,
        desc: s.desc || prev.desc,
        atmosphere: s.atmosphere || prev.atmosphere,
        features: s.features || prev.features,
        currentState: s.currentState || prev.currentState,
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
  /** Write the watercolor positive/negative scene-art prompts (editable after). */
  async function generateSceneArtPrompts() {
    if (!modal || modal.type !== "setting") return;
    setGeneratingPrompts(true);
    setError(null);
    try {
      const r = await api.generateSceneArtPrompts({
        name: draft.name,
        type: draft.type,
        desc: draft.desc,
        atmosphere: draft.atmosphere,
        features: draft.features,
        currentState: draft.currentState,
      });
      setDraftState((prev) => ({
        ...prev,
        _sceneArtPositive: r.positive,
        _sceneArtNegative: r.negative,
      }));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setGeneratingPrompts(false);
    }
  }
  /** Render the establishing image via ComfyUI from the current prompts → draft.image. */
  async function generateSceneArt() {
    if (!modal || modal.type !== "setting") return;
    const positive = (draft._sceneArtPositive ?? "").trim();
    if (!positive) return;
    setGeneratingPortrait(true);
    setError(null);
    try {
      const { image } = await api.generateSceneArt({
        positive,
        negative: draft._sceneArtNegative?.trim() || undefined,
      });
      setDraftState((prev) => ({ ...prev, image }));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setGeneratingPortrait(false);
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
        syncStorylineUrl(next?.id ?? "");
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
    setGenerating(false);
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
    setDraftState({
      name: s.name, type: s.type, desc: s.desc,
      atmosphere: s.atmosphere ?? "", features: s.features ?? "",
      currentState: s.currentState ?? "", image: s.image ?? null,
      timeline: s.timeline ?? [],
    });
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

  // ---- scenario agentic authoring (real model call via backend) ----
  /** Draft a scenario (fields + a roster-grounded cast & setting) from the seed. */
  async function draftScenario() {
    if (!modal || modal.type !== "scenario") return;
    const seed = (draft._prompt ?? "").trim();
    if (!seed) return;
    const docsOverview = draft._docFiles?.length
      ? concatDocs(docsForDraft(draft._docFiles))
      : undefined;
    setGenerating(true);
    setError(null);
    try {
      const s = await api.draftScenario(seed, activeStorylineId || undefined, docsOverview);
      setDraftState((prev) => ({
        ...prev,
        title: s.title || prev.title,
        genre: s.genre || prev.genre,
        tone: s.tone || prev.tone,
        goal: s.goal || prev.goal,
        opening: s.opening || prev.opening,
        // Cast + setting are real members of the active world (resolved server-side).
        cast: s.castIds,
        settingId: s.settingId,
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
        const body = {
          name: (d.name ?? "").trim(),
          type: d.type || "Social Hub",
          desc: d.desc?.trim() || "A place yet to be described.",
          // §4.1 node metadata: empty → null (clears on edit, unset on create).
          atmosphere: d.atmosphere?.trim() || null,
          features: d.features?.trim() || null,
          currentState: d.currentState?.trim() || null,
          image: d.image || null,
        };
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
          opening: d.opening?.trim() || "A new scene awaits its first line of narration…",
          branches: [...(d.branches ?? [])],
        };
        if (editId) {
          const updated = await api.updateScenario(editId, body);
          setScenarios((xs) => xs.map((x) => (x.id === editId ? updated : x)));
        } else {
          const created = await api.createScenario(activeStorylineId, body);
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
    // character agentic authoring
    draftCharacter, generatePortraitPrompts, generatePortrait,
    proposeStartingStats, applyStartingStats,
    generatingPrompts, generatingPortrait, generatingStats, applyingStats,
    // setting agentic authoring
    draftSetting, generateSceneArtPrompts, generateSceneArt,
    // scenario agentic authoring
    draftScenario,
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
    openCreate, editCharacter, editSetting, editScenario,
    setDraft, setMode, toggleDraftCast, submit, deleteEntity, closeModal,
    // profile + begin
    profileId, profileChar, openProfile, closeProfile, openBegin,
  };
}
