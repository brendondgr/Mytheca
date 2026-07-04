"use client";

import { useEffect, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { PromptOverridesEditor } from "@/components/feature/PromptOverridesEditor";
import { getSettings, type PromptSpec } from "@/lib/api";

export interface PromptOverridesModalProps {
  open: boolean;
  onClose: () => void;
  /** Modal heading (e.g. "Embergate — writing prompts"). */
  heading: string;
  /** One-line description under the heading. */
  subtitle?: string;
  /** This layer's current overrides ({key → text}); absent keys inherit. */
  overrides: Record<string, string>;
  /**
   * The override layer(s) BELOW the global default (e.g. a storyline's overrides when
   * editing a scenario). Merged OVER the global overrides the modal fetches, so the
   * editor's inherited baseline reflects the full resolution below this layer.
   */
  baseline?: Record<string, string>;
  /** Save-button caption. */
  saveLabel?: string;
  /** Persist the layer's complete override map, then the modal closes. */
  onSave: (overrides: Record<string, string>) => Promise<void> | void;
}

/**
 * A modal wrapper around {@link PromptOverridesEditor}. Fetches the prompt catalog + the
 * global overrides from `/options` on open, so every surface (the per-storyline gear and
 * the per-scenario editor) renders the same up-to-date catalog. The inherited baseline is
 * the global overrides with any passed `baseline` layered on top.
 */
export function PromptOverridesModal({
  open,
  onClose,
  heading,
  subtitle,
  overrides,
  baseline,
  saveLabel,
  onSave,
}: PromptOverridesModalProps) {
  const [catalog, setCatalog] = useState<PromptSpec[] | null>(null);
  const [globalOverrides, setGlobalOverrides] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    // Reset to the loading state when the modal (re)opens, then fetch. The rule targets
    // synchronous setState; this is the canonical mount/open data-fetch (see useOptionsSettings).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCatalog(null);
    setLoadError(null);
    getSettings()
      .then((s) => {
        if (cancelled) return;
        setCatalog(s.prompts.catalog);
        setGlobalOverrides(s.prompts.overrides);
      })
      .catch((err: unknown) => {
        if (!cancelled) setLoadError(err instanceof Error ? err.message : "Could not load prompts.");
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  return (
    <Modal
      open={open}
      onClose={onClose}
      labelledBy="prompt-overrides-title"
      className="sm:w-[640px] lg:w-[760px]"
      externalClose
    >
      <div className="p-[22px_26px_24px]">
        <div id="prompt-overrides-title" className="font-display text-[22px] font-bold text-ink">
          {heading}
        </div>
        {subtitle ? <p className="mt-[4px] font-body text-[14px] text-ink-soft">{subtitle}</p> : null}
        <div className="my-[16px] h-[3px] border-t border-b border-t-ink border-b-hair-strong" />
        {loadError ? (
          <p role="alert" className="font-body text-[14px] text-danger">
            {loadError}
          </p>
        ) : null}
        {!catalog && !loadError ? (
          <p className="font-body text-[14px] text-ink-soft">Loading prompts…</p>
        ) : null}
        {catalog ? (
          <PromptOverridesEditor
            idPrefix="prompt-modal"
            catalog={catalog}
            overrides={overrides}
            baseline={{ ...globalOverrides, ...(baseline ?? {}) }}
            saveLabel={saveLabel}
            onSave={async (map) => {
              await onSave(map);
              onClose();
            }}
          />
        ) : null}
      </div>
    </Modal>
  );
}
