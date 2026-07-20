import type { Metadata } from "next";
import { SEED_SCENARIOS } from "@/lib/seed-data";
import { StoryPlayerRoute } from "@/features/story-player/StoryPlayerRoute";

/** Best-effort title from the seed (real title fills in client-side on load). */
function seedTitle(scenarioId: string): string {
  return SEED_SCENARIOS.find((s) => s.id === scenarioId)?.title ?? "Scene";
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ storylineId: string; scenarioId: string }>;
}): Promise<Metadata> {
  const { scenarioId } = await params;
  return { title: `${seedTitle(scenarioId)} · Mytheca` };
}

// `/{storylineId}/{scenarioId}` — the live story player. The scenario id resolves
// the scene from the backend (real cast + portraits, setting + scene art, stat
// schema), with a seed fallback; the storyline id is the "‹ Library" back-link
// target. The transcript itself is still locally scripted (no stream yet).
export default async function PlayPage({
  params,
}: {
  params: Promise<{ storylineId: string; scenarioId: string }>;
}) {
  const { storylineId, scenarioId } = await params;
  return (
    <StoryPlayerRoute
      storylineId={storylineId}
      scenarioId={scenarioId}
      backHref={`/${storylineId}`}
    />
  );
}
