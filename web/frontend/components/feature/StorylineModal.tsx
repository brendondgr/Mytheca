"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { CloseButton } from "@/components/ui/CloseButton";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TextField } from "@/components/ui/TextField";
import { TextArea } from "@/components/ui/TextArea";
import type { useLibraryState } from "@/features/library/useLibraryState";

/**
 * Write-first storyline creation modal. Replaces the old one-shot "Untitled
 * Storyline" create: the author writes the world here — a title, genre, one-line
 * tagline, and a multi-paragraph premise — before it's persisted. The
 * drag-and-drop context-files zone and the agentic "Draft with Velora" panel are
 * added as visible seams in a later phase.
 */
export function StorylineModal({ lib }: { lib: ReturnType<typeof useLibraryState> }) {
  const m = lib.modal;
  if (!m || m.type !== "storyline") return null;
  const d = lib.draft;

  return (
    <Modal
      open
      onClose={lib.closeModal}
      labelledBy="storyline-modal-title"
      className="sm:w-[560px]"
    >
      <div className="p-[22px_26px_24px]">
        <div className="flex items-start justify-between gap-[14px]">
          <div>
            <Eyebrow size={8.5} tracking="0.2em" color="#A8762A">
              New Storyline
            </Eyebrow>
            <div
              id="storyline-modal-title"
              className="mt-1 font-display text-[22px] font-bold text-ink"
            >
              Forge a New World
            </div>
          </div>
          <CloseButton onClose={lib.closeModal} />
        </div>

        <div className="my-[16px] h-[3px] border-t border-b border-t-ink border-b-hair-strong" />

        <TextField
          label="Title"
          placeholder="e.g. Embergate"
          value={d.title || ""}
          onChange={(e) => lib.setDraft("title", e.target.value)}
          className="mb-[14px]"
        />
        <TextField
          label="Genre"
          placeholder="e.g. Maritime Intrigue"
          value={d.genre || ""}
          onChange={(e) => lib.setDraft("genre", e.target.value)}
          className="mb-[14px]"
        />
        <TextField
          label="Tagline"
          placeholder="One line for the switcher — what the world is, in a breath."
          value={d.tagline || ""}
          onChange={(e) => lib.setDraft("tagline", e.target.value)}
          className="mb-[14px]"
        />
        <TextArea
          label="Premise"
          placeholder="Write the world in full — its setting, mood, the powers in play, what it's about. Multiple paragraphs welcome."
          rows={7}
          value={d.premise || ""}
          onChange={(e) => lib.setDraft("premise", e.target.value)}
        />

        {lib.error ? (
          <p role="alert" className="mt-4 font-body text-[13px] text-accent">
            {lib.error}
          </p>
        ) : null}

        <div className="mt-[22px] flex items-center justify-end gap-[10px]">
          <Button variant="ghost" onClick={lib.closeModal}>
            Cancel
          </Button>
          <Button onClick={lib.submitStoryline} disabled={!lib.isStorylineValid || lib.pending}>
            {lib.pending ? "Creating…" : "Create World"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
