"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { mediaUrl } from "@/lib/api";
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
}: {
  image: SceneImage | null;
  onClose: () => void;
}) {
  const [showPrompt, setShowPrompt] = useState(false);
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
          className="block h-auto max-h-[70vh] w-full rounded-[4px] border border-cardbd object-contain"
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
                <Eyebrow size={8} tracking="0.14em" className="mb-[5px] block">
                  Image prompt
                </Eyebrow>
                <p className="font-body text-[12.5px] leading-[1.5] text-ink-soft">
                  {image.prompt}
                </p>
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
