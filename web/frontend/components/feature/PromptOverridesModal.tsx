"use client";

import { useEffect, useRef, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { PromptOverridesEditor } from "@/components/feature/PromptOverridesEditor";
import { resolveLayers } from "@/lib/promptLayers";
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
  /**
   * The storyline layer, when this modal is editing the SCENARIO layer. The modal already
   * fetches the global layer and holds the scenario's own, so this is the one piece it
   * cannot know — and without it the origin badges would credit "This world" to "This
   * scene". Omit it and no badges render at all, which is honest: a modal that cannot see
   * every layer should not claim to name one.
   */
  storylineOverrides?: Record<string, string> | null;
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
  storylineOverrides,
  saveLabel,
  onSave,
}: PromptOverridesModalProps) {
  const [catalog, setCatalog] = useState<PromptSpec[] | null>(null);
  const [globalOverrides, setGlobalOverrides] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  // Guards a stale response — from either the mount-fetch or a manual Retry —
  // against landing after the modal has closed or reopened.
  const cancelledRef = useRef(false);

  // The catalog fetch, factored out of the effect so Retry can re-run the exact
  // same request instead of the modal being a dead end on failure.
  function loadCatalog() {
    cancelledRef.current = false;
    setCatalog(null);
    setLoadError(null);
    getSettings()
      .then((s) => {
        if (cancelledRef.current) return;
        setCatalog(s.prompts.catalog);
        setGlobalOverrides(s.prompts.overrides);
      })
      .catch((err: unknown) => {
        if (!cancelledRef.current) {
          setLoadError(err instanceof Error ? err.message : "Could not load prompts.");
        }
      });
  }

  useEffect(() => {
    if (!open) return;
    // Reset to the loading state when the modal (re)opens, then fetch. The rule targets
    // synchronous setState; this is the canonical mount/open data-fetch (see useOptionsSettings).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadCatalog();
    return () => {
      cancelledRef.current = true;
    };
  }, [open]);

  // Only when every layer is known. See `storylineOverrides`.
  const sources =
    catalog && storylineOverrides !== undefined
      ? resolveLayers(catalog.map((spec) => spec.key), {
          global: globalOverrides,
          storyline: storylineOverrides,
          scenario: overrides,
        })
      : undefined;

  return (
    <Modal
      open={open}
      onClose={onClose}
      labelledBy="prompt-overrides-title"
      className="sm:w-[640px] lg:w-[760px]"
      externalClose
    >
      <div className="p-[22px_26px_24px]">
        <div id="prompt-overrides-title" className="font-display text-step-2 font-bold text-ink">
          {heading}
        </div>
        {subtitle ? <p className="mt-2xs font-body text-body-sm text-ink-soft">{subtitle}</p> : null}
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
          <p className="font-body text-body-sm text-ink-soft">Loading prompts…</p>
        ) : null}
        {catalog ? (
          <PromptOverridesEditor
            idPrefix="prompt-modal"
            catalog={catalog}
            overrides={overrides}
            baseline={{ ...globalOverrides, ...(baseline ?? {}) }}
            sources={sources}
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
