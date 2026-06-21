import { Monogram } from "@/components/ui/Monogram";
import { TextField } from "@/components/ui/TextField";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { ToggleChip } from "@/components/ui/ToggleChip";
import type { Character, Setting } from "@/lib/types";
import type { Draft } from "@/features/library/editor";

export function ScenarioForm({
  draft,
  setDraft,
  toggleCast,
  characters,
  settings,
}: {
  draft: Draft;
  setDraft: (key: keyof Draft, value: unknown) => void;
  toggleCast: (id: string) => void;
  characters: Character[];
  settings: Setting[];
}) {
  const cast = draft.cast ?? [];
  return (
    <>
      <TextField
        label="Title"
        placeholder="e.g. The Embergate Conspiracy"
        value={draft.title || ""}
        onChange={(e) => setDraft("title", e.target.value)}
        className="mb-[14px]"
      />
      <div className="mb-[14px] flex gap-3">
        <TextField
          label="Genre"
          placeholder="Intrigue"
          value={draft.genre || ""}
          onChange={(e) => setDraft("genre", e.target.value)}
          className="flex-1"
        />
        <TextField
          label="Tone"
          placeholder="Tension · rising"
          value={draft.tone || ""}
          onChange={(e) => setDraft("tone", e.target.value)}
          className="flex-1"
        />
      </div>
      <TextField
        label="Scene goal"
        placeholder="What is at stake in this scene?"
        value={draft.goal || ""}
        onChange={(e) => setDraft("goal", e.target.value)}
        className="mb-[14px]"
      />
      <div className="mb-[14px]">
        <FieldLabel>Cast — choose who appears</FieldLabel>
        <div className="flex flex-wrap gap-[7px]">
          {characters.map((c) => (
            <ToggleChip key={c.id} selected={cast.includes(c.id)} onClick={() => toggleCast(c.id)}>
              <Monogram mono={c.mono} color={c.color} size={20} ring={1.5} fontSize={9} />
              {c.name}
            </ToggleChip>
          ))}
        </div>
      </div>
      <div>
        <FieldLabel>Setting — choose one</FieldLabel>
        <div className="flex flex-wrap gap-[7px]">
          {settings.map((s) => (
            <ToggleChip
              key={s.id}
              selected={draft.settingId === s.id}
              onClick={() => setDraft("settingId", s.id)}
            >
              ◆ {s.name}
            </ToggleChip>
          ))}
        </div>
      </div>
    </>
  );
}
