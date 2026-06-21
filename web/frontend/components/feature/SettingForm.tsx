import { TextField } from "@/components/ui/TextField";
import { TextArea } from "@/components/ui/TextArea";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { ToggleChip } from "@/components/ui/ToggleChip";
import { SETTING_TYPES } from "@/lib/seed-data";
import type { Draft } from "@/features/library/editor";

export function SettingForm({
  draft,
  setDraft,
}: {
  draft: Draft;
  setDraft: (key: keyof Draft, value: unknown) => void;
}) {
  return (
    <>
      <TextField
        label="Name"
        placeholder="e.g. The Drowned Market"
        value={draft.name || ""}
        onChange={(e) => setDraft("name", e.target.value)}
        className="mb-[14px]"
      />
      <div className="mb-[14px]">
        <FieldLabel>Type</FieldLabel>
        <div className="flex flex-wrap gap-[7px]">
          {SETTING_TYPES.map((t) => (
            <ToggleChip
              key={t}
              selected={draft.type === t}
              onClick={() => setDraft("type", t)}
              className="font-mono text-[10px] tracking-[0.05em] uppercase"
            >
              {t}
            </ToggleChip>
          ))}
        </div>
      </div>
      <TextArea
        label="Description"
        placeholder="A line of mood — what the place feels like."
        rows={3}
        value={draft.desc || ""}
        onChange={(e) => setDraft("desc", e.target.value)}
      />
    </>
  );
}
