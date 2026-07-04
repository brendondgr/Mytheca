"use client";

import type { OptionsState } from "@/features/options/useOptionsSettings";
import { PromptOverridesEditor } from "@/components/feature/PromptOverridesEditor";

/**
 * Options › Prompts — edit the GLOBAL default writing prompts for the four core agents
 * (Character · Narrator · Director · Planner), grouped into upper sub-tabs. These are the
 * app-wide defaults; a storyline (and then a scenario) can override them further.
 */
export function PromptsTab({ opts }: { opts: OptionsState }) {
  const prompts = opts.settings?.prompts;
  if (!prompts) {
    return <p className="font-body text-[14px] text-ink-soft">Loading prompts…</p>;
  }

  return (
    <div className="flex flex-col gap-[14px]">
      <p className="font-body text-[14px] text-ink-soft">
        These are the global default prompts that shape how scenes are written. Edit any prompt
        to change tone, phrasing, and how the story progresses everywhere — a storyline or an
        individual scenario can override them further.
      </p>
      <PromptOverridesEditor
        idPrefix="opt-prompts"
        catalog={prompts.catalog}
        overrides={prompts.overrides}
        saveLabel="Save global prompts"
        onSave={async (map) => {
          // The global namespace merges (a blank value clears a key) — clear any override
          // that was removed, then set the current ones.
          const patch: Record<string, string> = {};
          for (const key of Object.keys(prompts.overrides)) if (!(key in map)) patch[key] = "";
          for (const [key, value] of Object.entries(map)) patch[key] = value;
          await opts.savePrompts({ overrides: patch });
        }}
      />
    </div>
  );
}
