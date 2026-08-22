"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { TextArea } from "@/components/ui/TextArea";
import { ArtStylePicker } from "@/components/feature/ArtStylePicker";
import { mediaUrl, type ArtStyleId } from "@/lib/api";
import type { SceneImage } from "@/features/story-player/scene-data";

/**
 * The enlarged view of a transcript scene image — opened by clicking the beat.
 *
 * A lightbox rather than an editor: the picture at full width, its caption, and
 * the ComfyUI prompt behind a disclosure for the curious (the prompt is what the
 * image model was actually given, so it explains *why* the picture looks as it
 * does). Focus trap, Escape and backdrop dismissal come from {@link Modal}, which
 * also renders the external × so nothing overlays the art.
 */
export function SceneImageModal({
  image,
  onClose,
  onRepaint,
  busy = false,
}: {
  image: SceneImage | null;
  onClose: () => void;
  /**
   * Paint the moment again from the player's own wording, as a **new** beat. Omit to keep
   * the prompt read-only. Removing or replacing a picture is a different feature and a
   * different (destructive) code path; nothing here deletes anything.
   */
  onRepaint?: (prompt: string, artStyle?: ArtStyleId) => void;
  /** A moment stream is already in flight — a second would race it. */
  busy?: boolean;
}) {
  const [showPrompt, setShowPrompt] = useState(false);
  // Seeded from the beat, so painting again keeps THIS picture's look rather than reverting
  // to the global default. Reset alongside the prompt when a different image opens.
  const [style, setStyle] = useState<ArtStyleId | null>(image?.style ?? null);
  // Seeded from the image and keyed on it, so opening a different picture does not show the
  // previous one's prompt.
  const [draft, setDraft] = useState(image?.prompt ?? "");
  const [seenPrompt, setSeenPrompt] = useState(image?.prompt ?? "");
  if (image && image.prompt !== seenPrompt) {
    setSeenPrompt(image.prompt);
    setDraft(image.prompt);
    setStyle(image.style ?? null);
  }
  if (!image) return null;
  const caption = image.caption || "A picture of this moment in the scene.";
  return (
    <Modal
      open
      onClose={onClose}
      labelledBy="scene-image-modal-title"
      className="sm:w-[720px] md:w-[900px]"
      z={80}
      externalClose
    >
      <div className="p-[18px_18px_20px]">
        <div id="scene-image-modal-title" className="sr-only">
          Scene image — {caption}
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element -- generated art from our media mount */}
        <img
          src={mediaUrl(image.url)}
          alt={caption}
          // dvh: on mobile, `vh` measures the viewport as if the browser chrome
          // were hidden, so a 70vh image can exceed the space actually visible.
          className="block h-auto max-h-[70dvh] w-full rounded-[4px] border border-cardbd object-contain"
        />
        <p className="mt-[12px] font-body text-[13.5px] leading-[1.5] text-ink">{caption}</p>

        {image.prompt ? (
          <div className="mt-[12px]">
            <button
              type="button"
              onClick={() => setShowPrompt((open) => !open)}
              aria-expanded={showPrompt}
              className="cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase hover:underline"
            >
              {showPrompt ? "▾ Hide the prompt" : "▸ Show the prompt"}
            </button>
            {showPrompt ? (
              <div className="mt-[8px] rounded-[4px] border border-cardbd bg-field p-[10px_12px]">
                {onRepaint ? null : (
                  <Eyebrow size={8} tracking="0.14em" className="mb-[5px] block">
                    Image prompt
                  </Eyebrow>
                )}
                {onRepaint ? (
                  <>
                    {/* Editable, not read-only: the prompt already explained *why* the
                        picture looks as it does — making it writable turns that into how to
                        get the picture you wanted. Purely additive: painting again produces
                        a NEW beat and removes nothing. */}
                    <TextArea
                      label="Image prompt"
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      rows={4}
                      disabled={busy}
                    />
                    <ArtStylePicker
                      value={style}
                      onChange={setStyle}
                      label="Style"
                      compact
                      disabled={busy}
                      className="mt-[10px]"
                    />
                    <div className="mt-[10px] flex flex-wrap items-center justify-between gap-[8px]">
                      <span
                        role="status"
                        className="font-mono text-[9px] tracking-[0.08em] text-mute2 uppercase"
                      >
                        {busy ? "Painting the moment…" : ""}
                      </span>
                      <Button
                        variant="secondary"
                        onClick={() => onRepaint(draft, style ?? undefined)}
                        disabled={busy || !draft.trim()}
                      >
                        Paint again with this prompt
                      </Button>
                    </div>
                  </>
                ) : (
                  <p className="font-body text-[12.5px] leading-[1.5] text-ink-soft">
                    {image.prompt}
                  </p>
                )}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="mt-[16px] flex justify-end">
          <Button variant="ghost" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </Modal>
  );
}
