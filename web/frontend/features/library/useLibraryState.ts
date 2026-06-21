"use client";

import { useMemo, useState } from "react";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
} from "@/lib/seed-data";
import type { Character, Scenario, Setting } from "@/lib/types";

export type LibraryTabKey =
  | "scenarios"
  | "characters"
  | "settings"
  | "storylines";

/**
 * Client state for the Library surface. In this phase the data is the static
 * seed (read-only); Phase 5 layers create/edit/delete onto the same hook.
 */
export function useLibraryState() {
  const [characters] = useState<Character[]>(SEED_CHARACTERS);
  const [settings] = useState<Setting[]>(SEED_SETTINGS);
  const [scenarios] = useState<Scenario[]>(SEED_SCENARIOS);

  const [tab, setTab] = useState<LibraryTabKey>("scenarios");
  const [featuredId, setFeaturedId] = useState<string>(
    SEED_SCENARIOS[0]?.id ?? "",
  );
  const [query, setQuery] = useState("");
  const [expandedCharId, setExpandedCharId] = useState<string | null>(null);

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

  function toggleExpand(id: string) {
    setExpandedCharId((prev) => (prev === id ? null : id));
  }

  function cycleFeatured(direction: number) {
    if (scenarios.length === 0) return;
    const i = scenarios.findIndex((s) => s.id === featuredId);
    const base = i < 0 ? 0 : i;
    const next = scenarios[(base + direction + scenarios.length) % scenarios.length];
    setFeaturedId(next.id);
  }

  return {
    characters,
    settings,
    scenarios,
    resolvedScenarios,
    filteredCharacters,
    filteredSettings,
    filteredScenarios,
    tab,
    setTab,
    featured,
    featuredId,
    setFeaturedId,
    featuredIndex,
    query,
    setQuery,
    expandedCharId,
    toggleExpand,
    cycleFeatured,
    counts: {
      characters: characters.length,
      settings: settings.length,
      scenarios: scenarios.length,
      branches: featured?.branches.length ?? 0,
    },
  };
}
