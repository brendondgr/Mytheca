"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { CloseButton } from "@/components/ui/CloseButton";
import { Eyebrow } from "@/components/ui/Eyebrow";
import type { PopulateOptions } from "@/lib/types";

/**
 * The Create World confirmation: does the assistant also build this world's cast
 * and settings, and should it paint them?
 *
 * Population is the expensive half of creation (one generation per character and
 * place), so the author is asked rather than surprised — and artwork is a separate,
 * default-off opt-in because every image is a full ComfyUI render on top of that.
 * Declining still creates the world; only the population step is skipped.
 */
export function BuildWorldModal({
  open,
  defaults,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  defaults: PopulateOptions;
  onCancel: () => void;
  onConfirm: (options: PopulateOptions) => void;
}) {
  const [enabled, setEnabled] = useState(defaults.enabled);
  const [withArtwork, setWithArtwork] = useState(defaults.withArtwork);

  if (!open) return null;

  return (
    <Modal open onClose={onCancel} labelledBy="build-world-title" className="sm:w-[460px]">
      <div className="p-[22px_26px_24px]">
        <div className="flex items-start justify-between gap-[14px]">
          <div>
            {/* `--mute` rather than the Eyebrow default `--mute2`: at 10px uppercase
                on the modal panel, mute2 measures ~3.9:1 — under AA. */}
            <Eyebrow tracking="0.2em" color="var(--mute)">
              Create World
            </Eyebrow>
            <h2
              id="build-world-title"
              className="mt-1 font-display text-[22px] font-bold text-ink"
            >
              Build the cast and settings?
            </h2>
          </div>
          <CloseButton onClose={onCancel} />
        </div>

        <div className="my-[16px] h-[3px] border-t border-b border-t-ink border-b-hair-strong" />

        <p className="font-body text-[14.5px] leading-[1.5] text-ink">
          Mytheca can populate this world as it is created — writing a starting cast and
          the places your scenes will return to, grounded in the premise, the World
          Primer, and the context files you selected for Draft.
        </p>

        <fieldset className="mt-[18px] flex flex-col gap-[12px] border-0 p-0">
          <legend className="sr-only">What to build</legend>

          <label className="flex cursor-pointer items-start gap-[10px]">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              className="mt-[3px] h-[15px] w-[15px] shrink-0 accent-[var(--accent)]"
            />
            <span className="font-body text-[14px] leading-[1.45] text-ink">
              Write the characters and settings
              <span className="block font-body text-[12.5px] text-ink-soft">
                A few minutes — one generation per character and place.
              </span>
            </span>
          </label>

          <label className="flex cursor-pointer items-start gap-[10px]">
            <input
              type="checkbox"
              checked={withArtwork}
              disabled={!enabled}
              onChange={(e) => setWithArtwork(e.target.checked)}
              className="mt-[3px] h-[15px] w-[15px] shrink-0 accent-[var(--accent)] disabled:opacity-40"
            />
            <span
              className={
                enabled
                  ? "font-body text-[14px] leading-[1.45] text-ink"
                  : "font-body text-[14px] leading-[1.45] text-mute"
              }
            >
              Also paint portraits and scene art
              <span className="block font-body text-[12.5px] text-ink-soft">
                Needs a running ComfyUI server, and adds a render per entity. Skipped
                automatically if it can’t be reached — you can paint them later.
              </span>
            </span>
          </label>
        </fieldset>

        <div className="mt-[22px] flex flex-wrap items-center justify-end gap-[10px]">
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            variant="secondary"
            onClick={() => onConfirm({ enabled: false, withArtwork: false })}
          >
            Just the world
          </Button>
          <Button onClick={() => onConfirm({ enabled, withArtwork: enabled && withArtwork })}>
            {enabled ? "Create & Build" : "Create World"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
