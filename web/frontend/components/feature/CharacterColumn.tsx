import { CharacterCard } from "@/components/feature/CharacterCard";
import { ColumnEmpty, ColumnHeader } from "@/components/feature/ColumnChrome";
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
  padX,
}: {
  characters: Character[];
  castIds: string[];
  query: string;
  onPreview: (id: string) => void;
  onEdit: (id: string) => void;
  onAdd?: () => void;
  padX?: string;
}) {
  const cast = new Set(castIds);
  return (
    <div>
      <ColumnHeader title="Characters" count={characters.length} hint="The cast of this world." onAdd={onAdd} addLabel="Add character" className={padX} />
      <div className={cn(padX)}>
        {characters.length === 0 ? (
          <ColumnEmpty query={query} noun="characters" />
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
