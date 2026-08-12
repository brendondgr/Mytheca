"use client";

import { Eyebrow } from "@/components/ui/Eyebrow";
import { mediaUrl } from "@/lib/api";
import type { SceneImage } from "@/features/story-player/scene-data";

/**
 * `scene_image` — a picture of the moment, centered in the transcript.
 *
 * Deliberately the same object language as the scene-art preview in
 * {@link SceneArtModal}: a landscape frame, `rounded-[6px]`, hairline card border.
 * The whole frame is a button, so the picture enlarges on click *and* on Enter /
 * Space from the keyboard; the caption is the accessible name and the image's alt
 * text, so a screen-reader user gets the same description a sighted one does.
 */
export function SceneImageBeat({
  image,
  onOpen,
}: {
  image: SceneImage;
  onOpen?: (image: SceneImage) => void;
}) {
  const caption = image.caption || "A picture of this moment in the scene.";
  return (
    <figure className="my-[2px] flex flex-col items-center">
      <button
        type="button"
        onClick={onOpen ? () => onOpen(image) : undefined}
        disabled={!onOpen}
        aria-label={`Enlarge scene image — ${caption}`}
        className="group block w-full max-w-[560px] cursor-pointer overflow-hidden rounded-[6px] border border-cardbd bg-field shadow-[0_1px_2px_rgba(20,14,6,.06)] transition hover:border-accent hover:shadow-[0_6px_18px_rgba(10,6,3,.28)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-default disabled:hover:border-cardbd disabled:hover:shadow-[0_1px_2px_rgba(20,14,6,.06)]"
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- generated art from our media mount */}
        <img
          src={mediaUrl(image.url)}
          alt={caption}
          className="block h-auto w-full object-cover"
        />
      </button>
      <figcaption className="mt-[7px] max-w-[560px] text-center">
        <Eyebrow size={8} tracking="0.16em" className="block">
          A moment in the scene
        </Eyebrow>
        <span className="mt-[3px] block font-body text-[12.5px] leading-[1.45] text-ink-soft italic">
          {caption}
        </span>
      </figcaption>
    </figure>
  );
}
