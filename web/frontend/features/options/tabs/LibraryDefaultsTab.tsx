"use client";

import { useEffect, useState } from "react";
import { listStorylines, type StorylineSummary } from "@/lib/api";
import { FieldLabel } from "@/components/ui/FieldLabel";
import type { OptionsState } from "@/features/options/useOptionsSettings";

/** Non-sensitive UI defaults: which storyline opens on load, and startup behavior. */
export function LibraryDefaultsTab({ opts }: { opts: OptionsState }) {
  const [storylines, setStorylines] = useState<StorylineSummary[]>([]);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listStorylines()
      .then((data) => {
        if (!cancelled) setStorylines(data);
      })
      .catch(() => {
        /* Non-fatal: the select just stays empty. */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const library = opts.settings?.library;

  async function save(patch: Parameters<OptionsState["saveLibrary"]>[0]) {
    setStatus(null);
    try {
      await opts.saveLibrary(patch);
      setStatus("Saved.");
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "Could not save.");
    }
  }

  if (!library) {
    return <p className="font-body text-body-sm text-mute">Loading defaults…</p>;
  }

  return (
    <section aria-labelledby="library-heading">
      <h2 id="library-heading" className="font-display text-step-1 font-semibold text-ink">
        Library defaults
      </h2>
      <p className="mt-2xs mb-lg font-body text-body-sm text-ink-soft">
        Control what the Library shows when it first loads.
      </p>

      <label className="mb-lg block max-w-[420px]">
        <FieldLabel>Default storyline</FieldLabel>
        <select
          value={library.defaultStorylineId ?? ""}
          onChange={(e) => save({ defaultStorylineId: e.target.value || null })}
          className="w-full rounded-xs border border-field-bd bg-field px-md py-sm font-body text-field text-ink focus:border-accent focus:outline-none"
        >
          <option value="">Most recent</option>
          {storylines.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title}
            </option>
          ))}
        </select>
      </label>

      <label className="flex max-w-[420px] items-center gap-sm">
        <input
          type="checkbox"
          checked={library.openLastStoryline}
          onChange={(e) => save({ openLastStoryline: e.target.checked })}
          className="h-[16px] w-[16px] accent-[var(--accent)]"
        />
        <span className="font-body text-body-sm text-ink">
          Reopen the last storyline I used on startup
        </span>
      </label>

      {status ? (
        <p aria-live="polite" className="mt-lg font-mono text-eyebrow tracking-[0.06em] text-ink-soft">
          {status}
        </p>
      ) : null}
    </section>
  );
}
