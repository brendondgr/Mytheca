"use client";

import { useEffect, useRef, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { StyleGuideEditor } from "@/components/feature/StyleGuideEditor";
import {
  getStyleGuide,
  reviseStyleGuide,
  saveStylePreset,
  type StyleCatalog,
} from "@/lib/api";

export interface StyleGuideModalProps {
  open: boolean;
  onClose: () => void;
  /** Modal heading (e.g. "Harrow Lane — narrative style"). */
  heading: string;
  subtitle?: string;
  /** This layer's own blocks ({id → text}). */
  blocks: Record<string, string>;
  /** The storyline's blocks, when this modal edits the SCENARIO layer. */
  inherited?: Record<string, string>;
  layer?: "storyline" | "scenario";
  saveLabel?: string;
  /** Persist this layer's complete block map, then the modal closes. */
  onSave: (blocks: Record<string, string>) => Promise<void> | void;
}

/**
 * A modal wrapper around {@link StyleGuideEditor}. Fetches the block catalog + presets from
 * `/options/style-guide` on open, so every surface renders the same up-to-date list —
 * including presets the author saved from another world, which is the whole point of the
 * library being app-wide.
 *
 * "Save as preset" is offered at the world layer only. A scene's guide is a delta — a
 * handful of blocks that mean something *relative to* the world's — so saving one as a
 * standalone preset would produce a library entry that reads as a complete guide and is not.
 */
export function StyleGuideModal({
  open,
  onClose,
  heading,
  subtitle,
  blocks,
  inherited,
  layer = "storyline",
  saveLabel,
  onSave,
}: StyleGuideModalProps) {
  const [catalog, setCatalog] = useState<StyleCatalog | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  // Guards a stale response — from the open-fetch or a manual Retry — against landing
  // after the modal has closed or reopened.
  const cancelledRef = useRef(false);

  function loadCatalog() {
    cancelledRef.current = false;
    setCatalog(null);
    setLoadError(null);
    getStyleGuide()
      .then((next) => {
        if (!cancelledRef.current) setCatalog(next);
      })
      .catch((err: unknown) => {
        if (!cancelledRef.current) {
          setLoadError(err instanceof Error ? err.message : "Could not load the style guide.");
        }
      });
  }

  useEffect(() => {
    if (!open) return;
    // Reset to the loading state when the modal (re)opens, then fetch. The rule targets
    // synchronous setState; this is the canonical mount/open data-fetch.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadCatalog();
    return () => {
      cancelledRef.current = true;
    };
  }, [open]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      labelledBy="style-guide-title"
      className="sm:w-[640px] lg:w-[760px]"
      externalClose
    >
      <div className="p-[22px_26px_24px]">
        <div id="style-guide-title" className="font-display text-step-2 font-bold text-ink">
          {heading}
        </div>
        {subtitle ? (
          <p className="mt-2xs font-body text-body-sm text-ink-soft">{subtitle}</p>
        ) : null}
        <div className="my-lg h-[3px] border-t border-b border-t-ink border-b-hair-strong" />
        {loadError ? (
          <div className="flex flex-wrap items-center gap-sm">
            <p role="alert" className="font-body text-body-sm text-danger-ink">
              {loadError}
            </p>
            <Button variant="secondary" onClick={loadCatalog}>
              Try again
            </Button>
          </div>
        ) : null}
        {!catalog && !loadError ? (
          <p className="font-body text-body-sm text-ink-soft">Loading the style guide…</p>
        ) : null}
        {catalog ? (
          <StyleGuideEditor
            // The editor seeds its draft on mount only, so a changed incoming guide has to
            // remount it. Keying on the guide's content does that and nothing more: an
            // ordinary re-render with the same blocks produces the same key and keeps the
            // author's in-progress edits.
            key={JSON.stringify(blocks)}
            catalog={catalog.blocks}
            presets={catalog.presets}
            blocks={blocks}
            inherited={inherited}
            layer={layer}
            saveLabel={saveLabel}
            onSave={async (next) => {
              await onSave(next);
              onClose();
            }}
            // The author names the preset; the id is a slug of THAT name, not of the
            // modal heading — two worlds saving "Slow Burn" should collide on one entry
            // rather than silently making two called the same thing.
            onSavePreset={
              layer === "storyline"
                ? async (name, next) => {
                    const id =
                      name
                        .toLowerCase()
                        .replace(/[^a-z0-9]+/g, "-")
                        .replace(/^-+|-+$/g, "")
                        .slice(0, 40) || "saved-style";
                    await saveStylePreset({ id, name, blocks: next });
                  }
                : undefined
            }
            onRevise={async (instruction, current) => {
              const { styleBlocks } = await reviseStyleGuide({ instruction, current });
              return styleBlocks ?? {};
            }}
          />
        ) : null}
      </div>
    </Modal>
  );
}
