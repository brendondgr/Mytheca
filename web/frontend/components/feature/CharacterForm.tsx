import { Monogram } from "@/components/ui/Monogram";
import { TextField } from "@/components/ui/TextField";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { PALETTE } from "@/lib/seed-data";
import { monoOf } from "@/lib/monogram";
import type { Draft } from "@/features/library/editor";

const FIELDS: { key: keyof Draft; label: string; ph: string }[] = [
  { key: "name", label: "Display name", ph: "e.g. Captain Doran Hale" },
  { key: "role", label: "Role / archetype", ph: "e.g. Lawful Blocker" },
  { key: "traits", label: "Personality traits", ph: "Dutiful · Rigid · Honourable" },
  { key: "speech", label: "Voice / speech style", ph: "Formal and terse, by the book." },
  { key: "goal", label: "Goal", ph: "What do they want?" },
  { key: "secret", label: "Secret", ph: "What do they hide?" },
];

export function CharacterForm({
  draft,
  setDraft,
}: {
  draft: Draft;
  setDraft: (key: keyof Draft, value: unknown) => void;
}) {
  const color = draft.color || "#8E2B1C";
  return (
    <div className="flex gap-5">
      <div className="flex w-[128px] flex-none flex-col items-center gap-[11px]">
        <Monogram mono={monoOf(draft.name || "")} color={color} size={80} ring={3} fontSize={28} />
        <FieldLabel>Accent</FieldLabel>
        <div className="grid grid-cols-4 gap-[7px]">
          {PALETTE.map((col) => (
            <button
              key={col}
              type="button"
              aria-label={`Accent ${col}`}
              aria-pressed={draft.color === col}
              onClick={() => setDraft("color", col)}
              className="h-[24px] w-[24px] rounded-full"
              style={{
                background: col,
                boxShadow:
                  draft.color === col
                    ? `0 0 0 2px var(--modal-bg), 0 0 0 4px ${col}`
                    : "0 0 0 1px rgba(0,0,0,.15)",
              }}
            />
          ))}
        </div>
      </div>
      <div className="min-w-0 flex-1">
        {FIELDS.map((f) => (
          <TextField
            key={String(f.key)}
            label={f.label}
            placeholder={f.ph}
            value={(draft[f.key] as string) || ""}
            onChange={(e) => setDraft(f.key, e.target.value)}
            className="mb-[11px]"
          />
        ))}
      </div>
    </div>
  );
}
