import { TextField } from "@/components/ui/TextField";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { ToggleChip } from "@/components/ui/ToggleChip";
import { EVENT_TAGS } from "@/lib/seed-data";
import type { Draft } from "@/features/library/editor";

export function BranchForm({
  draft,
  setDraft,
  scenarioTitle,
}: {
  draft: Draft;
  setDraft: (key: keyof Draft, value: unknown) => void;
  scenarioTitle: string;
}) {
  return (
    <>
      <p className="mb-[14px] font-mono text-[9.5px] text-mute">
        Branch of “{scenarioTitle}”
      </p>
      <TextField
        label="Player approach"
        placeholder="e.g. Confront Maerin at her table"
        value={draft.label || ""}
        onChange={(e) => setDraft("label", e.target.value)}
        className="mb-[14px]"
      />
      <div className="mb-[14px] flex gap-3">
        <TextField
          label="Check"
          placeholder="Insight · DC 15"
          value={draft.check || ""}
          onChange={(e) => setDraft("check", e.target.value)}
          className="flex-1"
        />
        <TextField
          label="Outcome"
          placeholder="She lets a name slip — Suspicion +2"
          value={draft.outcome || ""}
          onChange={(e) => setDraft("outcome", e.target.value)}
          className="flex-[1.4]"
        />
      </div>
      <div>
        <FieldLabel>Event type</FieldLabel>
        <div className="flex flex-wrap gap-[7px]">
          {EVENT_TAGS.map((t) => (
            <ToggleChip
              key={t}
              selected={draft.tag === t}
              onClick={() => setDraft("tag", t)}
              className="font-mono text-[10px] tracking-[0.05em]"
            >
              {t}
            </ToggleChip>
          ))}
        </div>
      </div>
    </>
  );
}
