"use client";

import { useMemo, useRef, useState } from "react";
import {
  AI_BRANCHES,
  AI_CHARACTERS,
  AI_SCENARIOS,
  AI_SETTINGS,
  resolveScenario,
  SEED_STORYLINES,
} from "@/lib/seed-data";
import { monoOf } from "@/lib/monogram";
import type { Character, Scenario, Setting, Storyline } from "@/lib/types";
import {
  DEFAULT_DRAFTS,
  isDraftValid,
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

let idCounter = 0;
function newId(prefix: string): string {
  idCounter += 1;
  return `${prefix}${Date.now()}-${idCounter}`;
}

export function useLibraryState() {
  // State is storyline-scoped: we hold every storyline and an "active" id; the
  // cast/settings/scenarios shown are the active storyline's own. Switching in
  // the header swaps the entire working set.
  const [storylines, setStorylines] = useState<Storyline[]>(SEED_STORYLINES);
  const [activeStorylineId, setActiveStorylineId] = useState<string>(
    SEED_STORYLINES[0]?.id ?? "",
  );
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
  const [featuredId, setFeaturedId] = useState<string>(
    SEED_STORYLINES[0]?.scenarios[0]?.id ?? "",
  );
  const [query, setQuery] = useState("");
  const [expandedCharId, setExpandedCharId] = useState<string | null>(null);

  const [menuOpen, setMenuOpen] = useState(false);
  const [modal, setModal] = useState<ModalState | null>(null);
  const [draft, setDraftState] = useState<Draft>({});
  const [generating, setGenerating] = useState(false);
  const [profileId, setProfileId] = useState<string | null>(null);
  const generateTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
  function switchStoryline(id: string) {
    if (id === activeStorylineId) {
      setMenuOpen(false);
      return;
    }
    const next = storylines.find((s) => s.id === id);
    setActiveStorylineId(id);
    resetForStoryline(next?.scenarios[0]?.id ?? "");
  }
  function createStoryline() {
    const id = newId("sl");
    const story: Storyline = {
      id,
      title: "Untitled Storyline",
      genre: "Uncharted",
      tagline: "A blank world, waiting for its first scene.",
      characters: [],
      settings: [],
      scenarios: [],
    };
    setStorylines((sls) => [...sls, story]);
    setActiveStorylineId(id);
    resetForStoryline("");
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
    setModal(null);
  }
  function openCreate(type: EntityType) {
    setDraftState({ ...DEFAULT_DRAFTS[type] });
    setModal({
      type,
      mode: "manual",
      editId: null,
      scnId: type === "branch" ? featuredId : undefined,
    });
    setMenuOpen(false);
    setGenerating(false);
  }
  function editCharacter(id: string) {
    const c = characters.find((x) => x.id === id);
    if (!c) return;
    setDraftState({ name: c.name, role: c.role, color: c.color, traits: c.traits, speech: c.speech, goal: c.goal, secret: c.secret });
    setModal({ type: "character", mode: "manual", editId: id });
    setProfileId(null);
  }
  function editSetting(id: string) {
    const s = settings.find((x) => x.id === id);
    if (!s) return;
    setDraftState({ name: s.name, type: s.type, desc: s.desc });
    setModal({ type: "setting", mode: "manual", editId: id });
  }
  function editScenario(id: string) {
    const s = scenarios.find((x) => x.id === id);
    if (!s) return;
    setDraftState({ title: s.title, genre: s.genre, tone: s.tone, goal: s.goal, cast: [...s.castIds], settingId: s.settingId, branches: [...s.branches] });
    setModal({ type: "scenario", mode: "manual", editId: id });
  }
  function editBranch(scnId: string, index: number) {
    const s = scenarios.find((x) => x.id === scnId);
    const b = s?.branches[index];
    if (!b) return;
    setDraftState({ label: b.label, check: b.check, outcome: b.outcome, tag: b.tag });
    setModal({ type: "branch", mode: "manual", editId: String(index), scnId });
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

  // ---- agentic fake-draft ----
  function generate() {
    if (!modal || modal.type === "begin") return;
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

  // ---- submit / delete ----
  function submit() {
    if (!modal || modal.type === "begin") return;
    const { type, editId, scnId } = modal;
    const d = draft;
    if (!isDraftValid(type, d)) return;

    if (type === "character") {
      const base = {
        name: (d.name ?? "").trim(),
        role: d.role?.trim() || "Character",
        color: d.color || "#8E2B1C",
        mono: monoOf(d.name ?? ""),
        traits: d.traits?.trim() || "Newly forged · unwritten",
        speech: d.speech?.trim() || "—",
        goal: d.goal?.trim() || "—",
        secret: d.secret?.trim() || "—",
      };
      if (editId) {
        setCharacters((cs) => cs.map((c) => (c.id === editId ? { ...c, ...base } : c)));
      } else {
        const id = newId("c");
        setCharacters((cs) => [...cs, { id, ...base }]);
        setTab("characters");
        setExpandedCharId(id);
      }
    } else if (type === "setting") {
      const base = { name: (d.name ?? "").trim(), type: d.type || "Social Hub", desc: d.desc?.trim() || "A place yet to be described." };
      if (editId) setSettings((xs) => xs.map((x) => (x.id === editId ? { ...x, ...base } : x)));
      else {
        setSettings((xs) => [...xs, { id: newId("s"), ...base }]);
        setTab("settings");
      }
    } else if (type === "scenario") {
      const base = {
        title: (d.title ?? "").trim(),
        genre: d.genre?.trim() || "Custom",
        tone: d.tone?.trim() || "Unset",
        goal: d.goal?.trim() || "Goal to be set.",
        castIds: [...(d.cast ?? [])],
        settingId: d.settingId ?? "",
        branches: [...(d.branches ?? [])],
      };
      if (editId) {
        setScenarios((xs) => xs.map((x) => (x.id === editId ? { ...x, ...base } : x)));
      } else {
        const id = newId("sc");
        setScenarios((xs) => [...xs, { id, opening: "A new scene awaits its first line of narration…", ...base }]);
        setTab("scenarios");
        setFeaturedId(id);
      }
    } else if (type === "branch") {
      const nb = { label: (d.label ?? "").trim(), check: d.check?.trim() || "—", outcome: d.outcome?.trim() || "—", tag: d.tag ?? ("check_request" as const) };
      const targetId = scnId ?? featuredId;
      const idx = editId == null ? null : Number(editId);
      setScenarios((xs) =>
        xs.map((sc) =>
          sc.id !== targetId
            ? sc
            : { ...sc, branches: idx == null ? [...sc.branches, nb] : sc.branches.map((b, i) => (i === idx ? nb : b)) },
        ),
      );
    }
    closeModal();
  }

  function deleteEntity() {
    if (!modal || modal.type === "begin") return;
    const { type, editId } = modal;
    if (!editId) return;
    if (type === "character") {
      setCharacters((cs) => cs.filter((c) => c.id !== editId));
      setScenarios((xs) => xs.map((sc) => ({ ...sc, castIds: sc.castIds.filter((id) => id !== editId) })));
    } else if (type === "setting") {
      setSettings((xs) => xs.filter((x) => x.id !== editId));
    } else if (type === "scenario") {
      setScenarios((xs) => {
        const left = xs.filter((x) => x.id !== editId);
        if (featuredId === editId) setFeaturedId(left[0]?.id ?? "");
        return left;
      });
    }
    closeModal();
  }
  function deleteBranch(scnId: string, index: number) {
    setScenarios((xs) =>
      xs.map((sc) =>
        sc.id !== scnId ? sc : { ...sc, branches: sc.branches.filter((_, i) => i !== index) },
      ),
    );
  }

  const profileChar = characters.find((c) => c.id === profileId) ?? null;

  return {
    storylines, activeStorylineId, activeStoryline, switchStoryline, createStoryline,
    characters, settings, scenarios, resolvedScenarios,
    filteredCharacters, filteredSettings, filteredScenarios,
    tab, setTab,
    featured, featuredId, setFeaturedId, featuredIndex,
    query, setQuery,
    expandedCharId, toggleExpand,
    cycleFeatured,
    counts: {
      characters: characters.length,
      settings: settings.length,
      scenarios: scenarios.length,
      branches: featured?.branches.length ?? 0,
    },
    // editor
    menuOpen, setMenuOpen,
    modal, draft, generating,
    isEditing: Boolean(modal && modal.type !== "begin" && modal.editId != null),
    isValid: modal && modal.type !== "begin" ? isDraftValid(modal.type, draft) : false,
    openCreate, editCharacter, editSetting, editScenario, editBranch,
    setDraft, setMode, toggleDraftCast, generate, submit, deleteEntity, deleteBranch, closeModal,
    // profile + begin
    profileId, profileChar, openProfile, closeProfile, openBegin,
  };
}
