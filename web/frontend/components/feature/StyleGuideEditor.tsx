"use client";

import { useMemo, useState } from "react";
import type { StyleBlockSpec, StylePreset } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { TextField } from "@/components/ui/TextField";
import { cn } from "@/lib/cn";
import {
  STYLE_LAYER_LABELS,
  packBlocks,
  resolveStyleLayers,
  sameBlocks,
  type StyleLayer,
} from "@/lib/styleBlocks";

export interface StyleGuideEditorProps {
  /** The six blocks and their metadata (from `/options/style-guide`). */
  catalog: StyleBlockSpec[];
  /** Presets the author can apply — built-ins first, then their own. */
  presets: StylePreset[];
  /** This layer's own blocks ({id → text}); an absent or blank block inherits. */
  blocks: Record<string, string>;
  /**
   * The layer BELOW this one — the storyline's guide when editing a scenario. Shown as the
   * inherited text behind an empty field, so "empty" reads as *inherit* rather than as
   * *nothing*, which is the one thing an override editor has to make obvious.
   */
  inherited?: Record<string, string>;
  /** Which layer this editor edits. Decides the wording, not the behaviour. */
  layer?: "storyline" | "scenario";
  /** Persist this layer's complete block map. */
  onSave: (blocks: Record<string, string>) => Promise<void> | void;
  /** Offered only where saving makes sense (the world level). Named by the author. */
  onSavePreset?: (name: string, blocks: Record<string, string>) => Promise<void> | void;
  /**
   * Ask the model to revise the draft. Returns the COMPLETE revised guide; an empty object
   * means "leave it alone", which is how a failure arrives — never a silent wipe.
   */
  onRevise?: (instruction: string, blocks: Record<string, string>) => Promise<Record<string, string>>;
  saveLabel?: string;
}

/**
 * The narrative style guide editor: one field per block, with its inheritance visible.
 *
 * Deliberately NOT built like {@link PromptOverridesEditor}, which prefills every field
 * with the inherited text. That is right for prompts, where a field always has a live
 * value and "reset" means "put the default back". It is wrong here: a style guide is
 * *optional*, and most blocks of most worlds are genuinely unset. Prefilling would make
 * every world look styled and turn "clear this block" into an act of deleting text that
 * reappears. So a field holds only THIS layer's own text, and what it would inherit sits
 * behind it as placeholder and preview.
 *
 * Applying a preset fills the fields and leaves them editable — it never stores a
 * reference, so a preset edited later cannot rewrite a world that already shipped.
 *
 * `blocks` seeds the draft on mount and is not re-read afterwards, so a caller that can
 * swap the incoming guide under a mounted editor must remount it — {@link StyleGuideModal}
 * keys on the guide for exactly that reason. Re-syncing from props instead would mean a
 * background refresh could silently discard whatever the author was part-way through typing.
 */
export function StyleGuideEditor({
  catalog,
  presets,
  blocks,
  inherited,
  layer = "storyline",
  onSave,
  onSavePreset,
  onRevise,
  saveLabel = "Save style",
}: StyleGuideEditorProps) {
  const [draft, setDraft] = useState<Record<string, string>>(() => ({ ...blocks }));
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<{ kind: "saved" | "error"; msg: string } | null>(null);
  const [instruction, setInstruction] = useState("");
  const [revising, setRevising] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [namingPreset, setNamingPreset] = useState(false);

  const sources = useMemo(
    () =>
      resolveStyleLayers(
        catalog.map((b) => b.id),
        layer === "scenario"
          ? { storyline: inherited, scenario: draft }
          : { storyline: draft },
      ),
    [catalog, draft, inherited, layer],
  );

  const dirty = !sameBlocks(draft, blocks);
  const anySet = Object.keys(packBlocks(draft)).length > 0;

  function setBlock(id: string, text: string) {
    setDraft((prev) => ({ ...prev, [id]: text }));
  }

  function applyPreset(preset: StylePreset) {
    // Copied, not referenced — see the component doc. Every field stays editable after.
    setDraft({ ...preset.blocks });
    setStatus(null);
  }

  async function revise() {
    const ask = instruction.trim();
    if (!ask || !onRevise) return;
    setRevising(true);
    setStatus(null);
    try {
      const next = await onRevise(ask, packBlocks(draft));
      if (Object.keys(next).length) {
        setDraft(next);
        setInstruction("");
        setStatus({ kind: "saved", msg: "Revised — review it, then save." });
      } else {
        // Empty means the model could not be reached or answered with nothing usable.
        // Say so rather than blanking the fields, which is the one thing that cannot be undone.
        setStatus({ kind: "error", msg: "No revision came back — your guide is unchanged." });
      }
    } catch (err) {
      setStatus({ kind: "error", msg: err instanceof Error ? err.message : "Could not revise." });
    } finally {
      setRevising(false);
    }
  }

  async function run(action: () => Promise<void> | void, done: string) {
    setSaving(true);
    setStatus(null);
    try {
      await action();
      setStatus({ kind: "saved", msg: done });
    } catch (err) {
      setStatus({ kind: "error", msg: err instanceof Error ? err.message : "Could not save." });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-lg">
      <div className="flex flex-col gap-sm border-b border-hair pb-md">
        <p className="font-body text-label text-ink-soft">
          {layer === "scenario"
            ? "How this scene is written, where it differs from the world. Leave a field empty to keep the world's."
            : "How this story is written — not what happens in it. Every field is optional; leave one empty and nothing is said about it."}
        </p>
        {presets.length ? (
          <div className="flex flex-wrap items-center gap-sm">
            <span className="font-mono text-tag tracking-[0.06em] text-mute uppercase">
              Start from
            </span>
            {presets.map((preset) => (
              <button
                key={preset.id}
                type="button"
                title={preset.blurb || preset.name}
                onClick={() => applyPreset(preset)}
                className="cursor-pointer rounded-xs border border-cardbd bg-card px-sm py-2xs font-mono text-eyebrow tracking-[0.06em] text-ink-soft uppercase hover:border-accent hover:bg-hover hover:text-ink"
              >
                {preset.name}
              </button>
            ))}
          </div>
        ) : null}
        {onRevise ? (
          <div className="flex flex-wrap items-end gap-sm">
            <label className="min-w-[220px] flex-1">
              <span className="mb-2xs block font-mono text-tag tracking-[0.06em] text-mute uppercase">
                Ask for a change
              </span>
              <TextArea
                aria-label="Ask the model to revise this style guide"
                rows={2}
                value={instruction}
                placeholder="e.g. make the voice colder, and drop the Never block"
                onChange={(event) => setInstruction(event.target.value)}
                onKeyDown={(event) => {
                  // Enter sends; Shift+Enter is a newline. A two-row box invites one
                  // sentence, and reaching for the mouse to send it is friction.
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void revise();
                  }
                }}
              />
            </label>
            <Button variant="secondary" onClick={revise} disabled={revising || !instruction.trim()}>
              {revising ? "Asking…" : "❖ Ask"}
            </Button>
          </div>
        ) : null}
      </div>

      {catalog.map((block) => {
        const own = draft[block.id] ?? "";
        const below = (inherited?.[block.id] ?? "").trim();
        const source: StyleLayer = sources[block.id] ?? "none";
        const showingInherited = !own.trim() && Boolean(below);
        return (
          <div key={block.id} className="flex flex-col gap-xs">
            <div className="flex items-center justify-between gap-sm">
              <span className="font-display text-body-sm font-semibold text-ink">
                {block.label}
                <span
                  className={cn(
                    "ml-sm font-mono text-tag tracking-[0.06em] uppercase",
                    source === "none" ? "text-mute2" : "text-accent-ink",
                  )}
                >
                  {STYLE_LAYER_LABELS[source]}
                </span>
              </span>
              <button
                type="button"
                // Named per block, not just labelled by its visible text: six buttons all
                // reading "Clear" is a list of identical controls to anyone navigating by
                // button, with nothing to say which block each one empties.
                aria-label={
                  layer === "scenario"
                    ? `Use the world's ${block.label}`
                    : `Clear ${block.label}`
                }
                onClick={() => setBlock(block.id, "")}
                disabled={!own.trim()}
                className="cursor-pointer font-mono text-eyebrow tracking-[0.08em] text-mute uppercase hover:text-accent-ink disabled:cursor-not-allowed disabled:opacity-40"
              >
                {layer === "scenario" ? "Use the world's" : "Clear"}
              </button>
            </div>
            <p className="font-body text-label text-ink-soft">{block.helper}</p>
            <TextArea
              aria-label={`${block.label} — style`}
              rows={block.placement === "tail" ? 2 : 5}
              value={own}
              placeholder={below || block.placeholder}
              onChange={(event) => setBlock(block.id, event.target.value)}
            />
            {showingInherited ? (
              <p className="font-body text-eyebrow text-mute2">
                Inheriting from the world. Type here to change it for this scene only.
              </p>
            ) : null}
          </div>
        );
      })}

      <div className="flex flex-wrap items-center gap-md">
        <Button onClick={() => run(() => onSave(packBlocks(draft)), "Saved.")} disabled={saving || !dirty}>
          {saving ? "Saving…" : saveLabel}
        </Button>
        {onSavePreset && !namingPreset ? (
          <Button variant="secondary" onClick={() => setNamingPreset(true)} disabled={!anySet}>
            Save as preset…
          </Button>
        ) : null}
        {onSavePreset && namingPreset ? (
          <div className="flex flex-wrap items-center gap-sm">
            <TextField
              aria-label="Preset name"
              value={presetName}
              placeholder="Name this preset — e.g. Slow Burn"
              onChange={(event) => setPresetName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && presetName.trim()) {
                  event.preventDefault();
                  void run(
                    () => onSavePreset(presetName.trim(), packBlocks(draft)),
                    `Saved “${presetName.trim()}”.`,
                  ).then(() => {
                    setNamingPreset(false);
                    setPresetName("");
                  });
                }
              }}
            />
            <Button
              variant="secondary"
              disabled={saving || !presetName.trim()}
              onClick={async () => {
                const name = presetName.trim();
                await run(() => onSavePreset(name, packBlocks(draft)), `Saved “${name}”.`);
                setNamingPreset(false);
                setPresetName("");
              }}
            >
              {saving ? "Saving…" : "Save preset"}
            </Button>
            <button
              type="button"
              onClick={() => {
                setNamingPreset(false);
                setPresetName("");
              }}
              className="cursor-pointer font-mono text-eyebrow tracking-[0.08em] text-mute uppercase hover:text-accent-ink"
            >
              Cancel
            </button>
          </div>
        ) : null}
        {status ? (
          <span
            role={status.kind === "error" ? "alert" : "status"}
            className={cn(
              "font-body text-label",
              status.kind === "error" ? "text-danger-ink" : "text-ink-soft",
            )}
          >
            {status.msg}
          </span>
        ) : null}
      </div>
    </div>
  );
}
