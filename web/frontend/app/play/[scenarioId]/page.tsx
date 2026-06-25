import { redirect } from "next/navigation";
import { SEED_SCENARIOS, SEED_STORYLINES } from "@/lib/seed-data";

// Legacy `/play/[scenarioId]` → permanent redirect to the storyline-scoped URL
// `/{storylineId}/{scenarioId}`. Resolves the owning storyline from seed data
// (falling back to the first storyline) so old links/bookmarks keep working.
export default async function LegacyPlayRedirect({
  params,
}: {
  params: Promise<{ scenarioId: string }>;
}) {
  const { scenarioId } = await params;
  const owner = SEED_STORYLINES.find((sl) =>
    sl.scenarios.some((s) => s.id === scenarioId),
  );
  const fallbackScenario = SEED_SCENARIOS[0]?.id ?? scenarioId;
  const storylineId = owner?.id ?? SEED_STORYLINES[0]?.id ?? "";
  redirect(`/${storylineId}/${owner ? scenarioId : fallbackScenario}`);
}
