import { ScenarioCard } from "@/components/feature/ScenarioCard";
import { ColumnEmpty, ColumnHeader } from "@/components/feature/ColumnChrome";
import { ScenarioColumnSkeleton } from "@/components/feature/LibrarySkeletons";
import type { ResolvedScenario } from "@/lib/types";
import { cn } from "@/lib/cn";

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
  onAdd,
  onClearQuery,
  loading = false,
  padX,
}: {
  scenarios: ResolvedScenario[];
  featuredId: string;
  query: string;
  onSelect: (id: string) => void;
  onEdit: (id: string) => void;
  onProfile: (id: string) => void;
  onAdd?: () => void;
  onClearQuery?: () => void;
  /** The world's scenarios are still being fetched — show the row placeholders. */
  loading?: boolean;
  padX?: string;
}) {
  return (
    <div>
      <ColumnHeader
        title="Scenarios"
        count={scenarios.length}
        hint="Select a scene — its cast & setting light up."
        onAdd={onAdd}
        addLabel="Add scenario"
        className={padX}
      />
      <div className={cn(padX)} aria-busy={loading || undefined}>
        {loading ? (
          <ScenarioColumnSkeleton />
        ) : scenarios.length === 0 ? (
          <ColumnEmpty
            query={query}
            noun="scenarios"
            invitation="A scenario is a scene to play — a setting, a cast, and something at stake."
            onAdd={onAdd}
            addLabel="New Scenario"
            onClearQuery={onClearQuery}
          />
        ) : (
          // `.reveal` fades each row in as it enters the column's own scroller,
          // via animation-timeline: view() — compositor-driven, so it does not
          // stutter while a turn is streaming elsewhere. The base style IS the
          // revealed state, so with no support (or under reduced motion) every
          // card is simply visible. There is no scroll progress bar or parallax
          // anywhere: Mytheca has no root scroll to measure.
          <div className="flex flex-col gap-[14px]">
            {scenarios.map((s) => (
              <div key={s.id} className="reveal">
              <ScenarioCard
                scenario={s}
                featured={s.id === featuredId}
                onSelect={() => onSelect(s.id)}
                onEdit={() => onEdit(s.id)}
                onProfile={onProfile}
              />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
