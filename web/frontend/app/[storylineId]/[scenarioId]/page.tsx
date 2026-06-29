import type { Metadata } from "next";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
  SEED_STAT_DEFS,
} from "@/lib/seed-data";
import { StoryPlayerView } from "@/features/story-player/StoryPlayerView";

function pickScenario(scenarioId: string) {
  return SEED_SCENARIOS.find((s) => s.id === scenarioId) ?? SEED_SCENARIOS[0];
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ storylineId: string; scenarioId: string }>;
}): Promise<Metadata> {
  const { scenarioId } = await params;
  return { title: `${pickScenario(scenarioId).title} · Velora` };
}

// `/{storylineId}/{scenarioId}` — the live story player. The scenario id resolves
// the scene (client seed data for now); the storyline id is the "‹ Library"
// back-link target. Unknown scenario ids fall back to the default scenario.
export default async function PlayPage({
  params,
}: {
  params: Promise<{ storylineId: string; scenarioId: string }>;
}) {
  const { storylineId, scenarioId } = await params;
  const scenario = resolveScenario(
    pickScenario(scenarioId),
    SEED_CHARACTERS,
    SEED_SETTINGS,
  );
  return (
    <StoryPlayerView
      scenario={scenario}
      statDefs={SEED_STAT_DEFS}
      backHref={`/${storylineId}`}
    />
  );
}
