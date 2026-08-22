"use client";

import { FieldLabel } from "@/components/ui/FieldLabel";
import { TextField } from "@/components/ui/TextField";
import { SceneControlSelect } from "@/components/ui/SceneControlSelect";
import { VERB_GROUPS, VERB_GROUP_LABELS, type AuthoredVerb, type VerbGroup } from "@/lib/sceneVerbs";

/** Past a handful the bar becomes the wall of buttons the grouping exists to avoid. */
export const MAX_SCENE_VERBS = 8;

/**
 * The scene's own one-tap direction verbs, edited by the author.
 *
 * Three fields, and the split between two of them is the point: **`label` is the chip,
 * `text` is the phrasing** written into the direction box for the player to edit. An author
 * who types the same thing twice gets a command to fire rather than a sentence to argue
 * with, which is the failure mode the whole verb surface was rebuilt to avoid — so the
 * placeholder says so.
 */
export function DirectionVerbsEditor({
  verbs,
  onChange,
}: {
  verbs: AuthoredVerb[];
  onChange: (next: AuthoredVerb[]) => void;
}) {
  const set = (i: number, patch: Partial<AuthoredVerb>) =>
    onChange(verbs.map((v, j) => (i === j ? { ...v, ...patch } : v)));

  return (
    <section className="mb-[14px]">
      <FieldLabel>Direction verbs — this scene&apos;s own</FieldLabel>
      <p className="mt-[2px] mb-[8px] font-body text-[11.5px] leading-[1.45] text-mute2">
        One-tap phrasings added to the player&apos;s direction bar, alongside the built-in
        ones. The <em>chip</em> is the short name; the <em>phrasing</em> is what gets written
        into their direction box for them to edit.
      </p>

      <ul className="grid gap-[8px]">
        {verbs.map((verb, i) => (
          <li key={i} className="grid gap-[6px] rounded-[8px] border border-field-bd p-[8px]">
            <div className="flex flex-wrap gap-[6px]">
              <TextField
                label="Chip"
                placeholder="Ring the bell"
                value={verb.label}
                onChange={(e) => set(i, { label: e.target.value })}
                className="min-w-[120px] flex-1"
              />
              <SceneControlSelect
                label={`Group for ${verb.label || "this verb"}`}
                value={verb.group}
                onChange={(next) => set(i, { group: next as VerbGroup })}
                options={VERB_GROUPS.map((g) => ({
                  value: g,
                  label: VERB_GROUP_LABELS[g],
                }))}
                className="min-w-[110px]"
              />
            </div>
            <TextField
              label="Phrasing"
              placeholder="The harbour bell starts ringing, and everyone hears it."
              value={verb.text}
              onChange={(e) => set(i, { text: e.target.value })}
            />
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => onChange(verbs.filter((_, j) => j !== i))}
                aria-label={`Remove ${verb.label || "this verb"}`}
                className="min-h-[24px] rounded-[6px] border border-field-bd px-[8px] font-mono text-[9px] tracking-[0.08em] text-mute uppercase hover:bg-hover hover:text-ink"
              >
                Remove
              </button>
            </div>
          </li>
        ))}
      </ul>

      {verbs.length < MAX_SCENE_VERBS ? (
        <button
          type="button"
          onClick={() => onChange([...verbs, { label: "", group: "event", text: "" }])}
          className="mt-[8px] min-h-[28px] rounded-[6px] border border-field-bd px-[10px] font-mono text-[9px] tracking-[0.08em] text-mute uppercase hover:bg-hover hover:text-ink"
        >
          + Add a verb
        </button>
      ) : (
        <p className="mt-[8px] font-mono text-[9px] tracking-[0.1em] text-mute2 uppercase">
          {MAX_SCENE_VERBS} is the limit — the bar is a glance-and-tap surface
        </p>
      )}
    </section>
  );
}
