"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { CloseButton } from "@/components/ui/CloseButton";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { cn } from "@/lib/cn";
import { useDelayedFlag } from "@/hooks/use-delayed-flag";
import type { ResolvedScenario } from "@/lib/types";

/**
 * Confirmation for deleting a scenario, opened by the trash square on the card.
 * Deleting a scene is not a world delete: the cast and the setting are shared
 * with the rest of the storyline and stay exactly where they are, so this says
 * so — the fear it exists to answer is "will this take my characters with it?".
 */
export function ScenarioDeleteModal({
  scenario,
  pending,
  error,
  onConfirm,
  onCancel,
}: {
  scenario: ResolvedScenario | null;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  // Delayed so a delete that resolves quickly never flashes a spinner.
  const busy = useDelayedFlag(pending);
  if (!scenario) return null;

  return (
    <Modal
      open
      onClose={onCancel}
      labelledBy="scenario-delete-title"
      className="sm:w-[440px]"
    >
      <div className="p-[22px_26px_24px]">
        <div className="flex items-start justify-between gap-lg">
          <div>
            <Eyebrow tracking="0.2em" entity="#9A3520">
              Delete Scenario
            </Eyebrow>
            <div
              id="scenario-delete-title"
              className="mt-1 font-display text-step-2 font-bold text-ink"
            >
              Delete “{scenario.title}”?
            </div>
          </div>
          <CloseButton onClose={onCancel} />
        </div>

        <div className="my-lg h-[3px] border-t border-b border-t-ink border-b-hair-strong" />

        <p className="font-body text-body-sm leading-[1.5] text-ink">
          This permanently removes the scene and any playthroughs of it. Its cast
          {scenario.cast.length > 0 ? (
            <>
              {" "}
              — {scenario.cast.length} character
              {scenario.cast.length === 1 ? "" : "s"}
            </>
          ) : null}{" "}
          and the setting “{scenario.setting.name}” are kept. This can’t be undone.
        </p>

        {error ? (
          <p role="alert" className="mt-4 font-body text-label text-accent-ink">
            {error}
          </p>
        ) : null}

        <div
          className="mt-xl flex items-center justify-end gap-sm"
          aria-busy={pending || undefined}
        >
          <Button variant="ghost" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            aria-busy={busy || undefined}
            aria-label={busy ? "Deleting scenario" : undefined}
            className="relative inline-flex cursor-pointer items-center justify-center rounded-xs px-lg py-sm font-mono text-eyebrow tracking-[0.08em] text-[#F6ECDA] uppercase hover:brightness-[1.3] disabled:cursor-not-allowed disabled:opacity-60"
            style={{ background: "#9A3520" }}
          >
            <span className={cn("inline-flex items-center", busy && "invisible")}>
              Delete Scenario
            </span>
            {busy ? (
              <span className="absolute inset-0 flex items-center justify-center">
                <Spinner size={14} />
              </span>
            ) : null}
          </button>
        </div>
      </div>
    </Modal>
  );
}
