import { CharacterCard } from "@/components/feature/CharacterCard";
import { ColumnEmpty, ColumnHeader } from "@/components/feature/ColumnChrome";
import { CharacterColumnSkeleton } from "@/components/feature/LibrarySkeletons";
import type { Character } from "@/lib/types";
import { cn } from "@/lib/cn";

/**
 * Characters column — three characters per row (two on the narrowest widths).
 * Members of the selected scenario's cast are lit up via the card's
 * `highlighted` state. Clicking a card opens the character profile modal.
 */
export function CharacterColumn({
  characters,
  castIds,
  query,
  onPreview,
  onEdit,
  onAdd,
  onClearQuery,
  loading = false,
  padX,
}: {
  characters: Character[];
  castIds: string[];
  query: string;
  onPreview: (id: string) => void;
  onEdit: (id: string) => void;
  onAdd?: () => void;
  onClearQuery?: () => void;
  /** The world's cast is still being fetched — show the tile placeholders. */
  loading?: boolean;
  padX?: string;
}) {
  const cast = new Set(castIds);
  return (
    <div>
      <ColumnHeader title="Characters" count={characters.length} hint="The cast of this world." onAdd={onAdd} addLabel="Add character" className={padX} />
      <div className={cn(padX)} aria-busy={loading || undefined}>
        {loading ? (
          <CharacterColumnSkeleton />
        ) : characters.length === 0 ? (
          <ColumnEmpty
            query={query}
            noun="characters"
            invitation="A character is someone your scenes can be played with — a voice, a manner, and a stake in what happens."
            onAdd={onAdd}
            addLabel="Forge Character"
            onClearQuery={onClearQuery}
          />
        ) : (
          <div className="grid grid-cols-2 gap-[12px] sm:grid-cols-3">
            {characters.map((c) => (
              <CharacterCard
                key={c.id}
                character={c}
                highlighted={cast.has(c.id)}
                onPreview={() => onPreview(c.id)}
                onEdit={() => onEdit(c.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
