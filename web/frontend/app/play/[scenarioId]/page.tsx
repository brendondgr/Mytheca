import type { Metadata } from "next";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
} from "@/lib/seed-data";
import { StoryPlayerView } from "@/features/story-player/StoryPlayerView";

function pickScenario(scenarioId: string) {
  return SEED_SCENARIOS.find((s) => s.id === scenarioId) ?? SEED_SCENARIOS[0];
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ scenarioId: string }>;
}): Promise<Metadata> {
  const { scenarioId } = await params;
  return { title: `${pickScenario(scenarioId).title} · Velora` };
}

// `/play/[scenarioId]` — the live story player. Unknown ids fall back to the
// default scenario (client-only seed data for now).
export default async function PlayPage({
  params,
}: {
  params: Promise<{ scenarioId: string }>;
}) {
  const { scenarioId } = await params;
  const scenario = resolveScenario(
    pickScenario(scenarioId),
    SEED_CHARACTERS,
    SEED_SETTINGS,
  );
  return <StoryPlayerView scenario={scenario} />;
}
