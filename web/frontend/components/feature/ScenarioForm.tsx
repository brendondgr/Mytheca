import { mediaUrl } from "@/lib/api";
import { TextField } from "@/components/ui/TextField";
import { MultiSelect, type MultiSelectOption } from "@/components/ui/MultiSelect";
import type { Character, Setting } from "@/lib/types";
import type { Draft } from "@/features/library/editor";
import { DirectionVerbsEditor } from "@/components/feature/DirectionVerbsEditor";
import type { AuthoredVerb } from "@/lib/sceneVerbs";

export function ScenarioForm({
  draft,
  setDraft,
  characters,
  settings,
}: {
  draft: Draft;
  setDraft: (key: keyof Draft, value: unknown) => void;
  characters: Character[];
  settings: Setting[];
}) {
  const cast = draft.cast ?? [];
  const castOptions: MultiSelectOption[] = characters.map((c) => ({
    id: c.id,
    label: c.name,
    mono: c.mono,
    color: c.color,
    portrait: c.portrait ? mediaUrl(c.portrait) : null,
    sublabel: c.role || undefined,
  }));
  const settingOptions: MultiSelectOption[] = settings.map((s) => ({
    id: s.id,
    label: s.name,
    seal: true,
  }));

  return (
    <>
      <TextField
        label="Title"
        placeholder="e.g. The Embergate Conspiracy"
        value={draft.title || ""}
        onChange={(e) => setDraft("title", e.target.value)}
        className="mb-lg"
      />
      <div className="mb-lg flex gap-3">
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
        className="mb-lg"
      />
      <MultiSelect
        multiple
        label="Cast — choose who appears"
        placeholder="Add characters…"
        emptyText="No characters yet — add one first"
        options={castOptions}
        selected={cast}
        onChange={(next) => setDraft("cast", next)}
        className="mb-lg"
      />
      <DirectionVerbsEditor
        verbs={(draft.directionVerbs as AuthoredVerb[] | undefined) ?? []}
        onChange={(next) => setDraft("directionVerbs", next)}
      />
      <MultiSelect
        label="Setting — choose one"
        placeholder="Pick a setting…"
        emptyText="No settings yet"
        options={settingOptions}
        selected={draft.settingId ? [draft.settingId] : []}
        onChange={(next) => setDraft("settingId", next[0] ?? "")}
      />
    </>
  );
}
