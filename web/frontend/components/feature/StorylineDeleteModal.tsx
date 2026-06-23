"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { CloseButton } from "@/components/ui/CloseButton";
import { Eyebrow } from "@/components/ui/Eyebrow";
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
        <div className="flex items-start justify-between gap-[14px]">
          <div>
            <Eyebrow size={8.5} tracking="0.2em" color="#9A3520">
              Delete Storyline
            </Eyebrow>
            <div
              id="storyline-delete-title"
              className="mt-1 font-display text-[22px] font-bold text-ink"
            >
              Delete “{storyline.title}”?
            </div>
          </div>
          <CloseButton onClose={onCancel} />
        </div>

        <div className="my-[16px] h-[3px] border-t border-b border-t-ink border-b-hair-strong" />

        <p className="font-body text-[14.5px] leading-[1.5] text-ink">
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
          <p role="alert" className="mt-4 font-body text-[13px] text-accent">
            {error}
          </p>
        ) : null}

        <div className="mt-[22px] flex items-center justify-end gap-[10px]">
          <Button variant="ghost" onClick={onCancel} disabled={pending}>
            Cancel
          </Button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className="inline-flex cursor-pointer items-center justify-center rounded-[2px] px-[18px] py-[10px] font-mono text-[11px] tracking-[0.08em] text-[#F6ECDA] uppercase hover:brightness-[1.08] disabled:cursor-not-allowed disabled:opacity-60"
            style={{ background: "#9A3520" }}
          >
            {pending ? "Deleting…" : "Delete World"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
