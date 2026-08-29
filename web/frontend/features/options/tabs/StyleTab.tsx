"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { deleteStylePreset, getStyleGuide, type StyleCatalog, type StylePreset } from "@/lib/api";

/**
 * Options › Narrative style — the saved-preset **library**.
 *
 * Deliberately not an editor and not a layer. There is no global style guide: one would
 * push a single voice onto every world, which is the opposite of what the feature is for.
 * What lives here is a shelf of reusable guides — the three built-ins, plus whatever the
 * author saved from a world — that can be applied *into* any storyline, where they become
 * that world's own editable text.
 *
 * So this tab lists and deletes. Writing happens where a guide is used.
 */
export function StyleTab() {
  const [catalog, setCatalog] = useState<StyleCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  function load() {
    setError(null);
    getStyleGuide()
      .then(setCatalog)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Could not load style presets."),
      );
  }

  useEffect(() => {
    // The canonical mount data-fetch; the lint rule targets synchronous setState.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, []);

  async function remove(preset: StylePreset) {
    setBusy(preset.id);
    setError(null);
    try {
      setCatalog(await deleteStylePreset(preset.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete that preset.");
    } finally {
      setBusy(null);
    }
  }

  const builtins = catalog?.presets.filter((p) => p.builtin) ?? [];
  const mine = catalog?.presets.filter((p) => !p.builtin) ?? [];

  return (
    <div className="flex flex-col gap-[18px]">
      <div>
        <SectionHeader title="Narrative style presets" />
        <p className="mt-[6px] font-body text-[13px] text-ink-soft">
          Reusable style guides — how a story is written, not what happens in it. Apply one to
          a world from its editor; it copies in and stays editable there, so changing a preset
          later never rewrites a world that already uses it.
        </p>
      </div>

      {error ? (
        <div className="flex flex-wrap items-center gap-[10px]">
          <p role="alert" className="font-body text-[14px] text-danger">
            {error}
          </p>
          <Button variant="secondary" onClick={load}>
            Try again
          </Button>
        </div>
      ) : null}

      {!catalog && !error ? (
        <p className="font-body text-[14px] text-ink-soft">Loading presets…</p>
      ) : null}

      {catalog ? (
        <>
          <div className="flex flex-col gap-[10px]">
            <span className="font-mono text-tag tracking-[0.08em] text-mute uppercase">
              Built in
            </span>
            {builtins.map((preset) => (
              <div
                key={preset.id}
                className="rounded-[4px] border border-cardbd bg-card2 p-[12px_14px]"
              >
                <div className="font-display text-[15px] font-semibold text-ink">
                  {preset.name}
                </div>
                <p className="mt-[2px] font-body text-[13px] text-ink-soft">{preset.blurb}</p>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-[10px]">
            <span className="font-mono text-tag tracking-[0.08em] text-mute uppercase">
              Saved by you
            </span>
            {mine.length === 0 ? (
              <p className="font-body text-[13px] text-mute2">
                None yet. Write a style guide on a world and choose “Save as preset” to reuse
                it elsewhere.
              </p>
            ) : (
              mine.map((preset) => (
                <div
                  key={preset.id}
                  className="flex items-center justify-between gap-[12px] rounded-[4px] border border-cardbd bg-card2 p-[12px_14px]"
                >
                  <div className="min-w-0">
                    <div className="truncate font-display text-[15px] font-semibold text-ink">
                      {preset.name}
                    </div>
                    <p className="mt-[2px] font-body text-[12.5px] text-mute2">
                      {Object.keys(preset.blocks).length} of 6 blocks
                    </p>
                  </div>
                  <Button
                    variant="secondary"
                    aria-label={`Delete ${preset.name}`}
                    disabled={busy === preset.id}
                    onClick={() => remove(preset)}
                  >
                    {busy === preset.id ? "Deleting…" : "Delete"}
                  </Button>
                </div>
              ))
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}
