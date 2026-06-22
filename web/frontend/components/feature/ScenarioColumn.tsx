import { ScenarioCard } from "@/components/feature/ScenarioCard";
import { ColumnEmpty, ColumnHeader } from "@/components/feature/ColumnChrome";
import type { ResolvedScenario } from "@/lib/types";

/**
 * Scenarios column — one scenario per row. Selecting a row features that
 * scenario, which drives the hero and the cross-highlights in the other two
 * columns.
 */
export function ScenarioColumn({
  scenarios,
  featuredId,
  query,
  onSelect,
  onEdit,
  onProfile,
}: {
  scenarios: ResolvedScenario[];
  featuredId: string;
  query: string;
  onSelect: (id: string) => void;
  onEdit: (id: string) => void;
  onProfile: (id: string) => void;
}) {
  return (
    <div>
      <ColumnHeader
        title="Scenarios"
        count={scenarios.length}
        hint="Select a scene — its cast & setting light up."
      />
      {scenarios.length === 0 ? (
        <ColumnEmpty query={query} noun="scenarios" />
      ) : (
        <div className="flex flex-col gap-[14px]">
          {scenarios.map((s) => (
            <ScenarioCard
              key={s.id}
              scenario={s}
              featured={s.id === featuredId}
              onSelect={() => onSelect(s.id)}
              onEdit={() => onEdit(s.id)}
              onProfile={onProfile}
            />
          ))}
        </div>
      )}
    </div>
  );
}
