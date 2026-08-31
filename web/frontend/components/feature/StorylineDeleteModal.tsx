"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Spinner } from "@/components/ui/Spinner";
import { CloseButton } from "@/components/ui/CloseButton";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { cn } from "@/lib/cn";
import { useDelayedFlag } from "@/hooks/use-delayed-flag";
import type { Storyline } from "@/lib/types";

/**
 * Confirmation for deleting a storyline. Deleting a world cascades to all of its
 * scenarios, characters, and settings (server-side), so this asks first and
 * spells out what goes with it.
 */
export function StorylineDeleteModal({
  storyline,
  pending,
  error,
  onConfirm,
  onCancel,
}: {
  storyline: Storyline | null;
  pending: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  // Delayed so a delete that resolves quickly never flashes a spinner.
  const busy = useDelayedFlag(pending);
  if (!storyline) return null;
  const { scenarios, characters, settings } = storyline;
  const total = scenarios.length + characters.length + settings.length;

  return (
    <Modal
      open
      onClose={onCancel}
      labelledBy="storyline-delete-title"
      className="sm:w-[440px]"
    >
      <div className="p-[22px_26px_24px]">
        <div className="flex items-start justify-between gap-lg">
          <div>
            <Eyebrow tracking="0.2em" entity="#9A3520">
              Delete Storyline
            </Eyebrow>
            <div
              id="storyline-delete-title"
              className="mt-1 font-display text-step-2 font-bold text-ink"
            >
              Delete “{storyline.title}”?
            </div>
          </div>
          <CloseButton onClose={onCancel} />
        </div>

        <div className="my-lg h-[3px] border-t border-b border-t-ink border-b-hair-strong" />

        <p className="font-body text-body-sm leading-[1.5] text-ink">
          This permanently removes the storyline and everything inside it
          {total > 0 ? (
            <>
              {" "}
              — its {scenarios.length} scenario{scenarios.length === 1 ? "" : "s"},{" "}
              {characters.length} character{characters.length === 1 ? "" : "s"}, and{" "}
              {settings.length} setting{settings.length === 1 ? "" : "s"}
            </>
          ) : null}
          . This can’t be undone.
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
            aria-label={busy ? "Deleting storyline" : undefined}
            className="relative inline-flex cursor-pointer items-center justify-center rounded-xs px-lg py-sm font-mono text-eyebrow tracking-[0.08em] text-[#F6ECDA] uppercase hover:brightness-[1.3] disabled:cursor-not-allowed disabled:opacity-60"
            style={{ background: "#9A3520" }}
          >
            <span className={cn("inline-flex items-center", busy && "invisible")}>
              Delete World
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
