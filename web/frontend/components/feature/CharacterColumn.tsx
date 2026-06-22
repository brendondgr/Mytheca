import { CharacterCard } from "@/components/feature/CharacterCard";
import { ColumnEmpty, ColumnHeader } from "@/components/feature/ColumnChrome";
import type { Character } from "@/lib/types";

/**
 * Characters column — two characters per row. Members of the selected
 * scenario's cast are lit up via the card's `highlighted` state.
 */
export function CharacterColumn({
  characters,
  castIds,
  expandedId,
  query,
  onToggle,
  onEdit,
}: {
  characters: Character[];
  castIds: string[];
  expandedId: string | null;
  query: string;
  onToggle: (id: string) => void;
  onEdit: (id: string) => void;
}) {
  const cast = new Set(castIds);
  return (
    <div>
      <ColumnHeader title="Characters" count={characters.length} hint="The cast of this world." />
      {characters.length === 0 ? (
        <ColumnEmpty query={query} noun="characters" />
      ) : (
        <div className="grid grid-cols-1 gap-[14px] sm:grid-cols-2">
          {characters.map((c) => (
            <CharacterCard
              key={c.id}
              character={c}
              expanded={expandedId === c.id}
              highlighted={cast.has(c.id)}
              onToggle={() => onToggle(c.id)}
              onEdit={() => onEdit(c.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
