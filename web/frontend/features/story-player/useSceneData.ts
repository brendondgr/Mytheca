"use client";

import { useEffect, useState } from "react";
import {
  getStoryline,
  listCharacters,
  listScenarios,
  listSettings,
  listContextDocumentIndex,
  listStatDefinitions,
} from "@/lib/api";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
  SEED_STAT_DEFS,
  SEED_STORYLINES,
} from "@/lib/seed-data";
import type {
  ContextDocumentIndexEntry,
  ResolvedScenario,
  StatDefinition,
  Character,
} from "@/lib/types";

/** The resolved scene + its world context, or a loading/error state. */
export type SceneData =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      scenario: ResolvedScenario;
      statDefs: StatDefinition[];
      storylineName: string;
      /** The storyline's context documents, taggable with `@` in the composer. */
      contextDocs: ContextDocumentIndexEntry[];
      /**
       * Every character in the storyline, not just this scene's cast. `resolveScenario`
       * narrows the list to `cast_ids`; the rail needs the rest of it to offer "Elsewhere
       * in the world" — the people a play-through can invite in.
       */
      storylineCast: Character[];
      /** How many places the storyline has — "Move the scene" needs somewhere to go. */
      settingCount: number;
    };

/** Resolve the scene from in-memory seed (offline/legacy fallback). */
function seedScene(storylineId: string, scenarioId: string): SceneData | null {
  const sc = SEED_SCENARIOS.find((s) => s.id === scenarioId);
  if (!sc) return null;
  const scenario = resolveScenario(sc, SEED_CHARACTERS, SEED_SETTINGS);
  const storyline =
    SEED_STORYLINES.find((s) => s.id === storylineId) ?? SEED_STORYLINES[0];
  return {
    status: "ready",
    scenario,
    statDefs: SEED_STAT_DEFS,
    storylineName: storyline?.title ?? "",
    // The seed demo has no persisted corpus, so `@` tagging is simply unavailable there.
    contextDocs: [],
    storylineCast: SEED_CHARACTERS,
    settingCount: SEED_SETTINGS.length,
  };
}

/**
 * Load a scene's real data from the backend: the storyline's cast, settings,
 * scenarios, and stat schema (+ its name). The requested scenario is resolved
 * into a `ResolvedScenario` (cast + setting). Falls back to the in-memory seed
 * when the scenario isn't in the backend or the backend is unreachable — so
 * the seed demo and legacy links keep working — and surfaces an error
 * otherwise. The transcript itself stays locally scripted (no stream yet).
 */
export function useSceneData(
  storylineId: string,
  scenarioId: string,
): SceneData & { reload: () => void } {
  const [state, setState] = useState<SceneData>({ status: "loading" });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // Reset to "loading" on each (re)fetch — the intended mount/refetch behavior.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setState({ status: "loading" });
    void (async () => {
      try {
        const [scenarios, characters, settings, statDefs, storyline, contextDocs] =
          await Promise.all([
            listScenarios(storylineId),
            listCharacters(storylineId),
            listSettings(storylineId),
            listStatDefinitions(storylineId).catch(() => [] as StatDefinition[]),
            getStoryline(storylineId).catch(() => null),
            // Names only, never bodies — and never a reason to fail the scene: no index
            // simply means the `@` menu has nothing to offer.
            listContextDocumentIndex(storylineId).catch(
              () => [] as ContextDocumentIndexEntry[],
            ),
          ]);
        if (cancelled) return;
        const sc = scenarios.find((s) => s.id === scenarioId);
        if (!sc) {
          const seed = seedScene(storylineId, scenarioId);
          setState(seed ?? { status: "error", message: "Scene not found." });
          return;
        }
        setState({
          status: "ready",
          scenario: resolveScenario(sc, characters, settings),
          statDefs,
          storylineName: storyline?.title ?? "",
          contextDocs,
          storylineCast: characters,
          settingCount: settings.length,
        });
      } catch (err) {
        if (cancelled) return;
        // Backend unreachable — fall back to seed if it has this scene, else error.
        const seed = seedScene(storylineId, scenarioId);
        setState(
          seed ?? {
            status: "error",
            message:
              err instanceof Error ? err.message : "Could not load the scene.",
          },
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [storylineId, scenarioId, nonce]);

  return { ...state, reload: () => setNonce((n) => n + 1) };
}
