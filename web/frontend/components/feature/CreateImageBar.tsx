"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { ArtStylePicker } from "@/components/feature/ArtStylePicker";
import { cn } from "@/lib/cn";
import type { ArtStyleId } from "@/lib/api";

/** What the two stages of a moment render are called, in the player's language. */
const STAGE_LABEL: Record<"prompt" | "render", string> = {
  prompt: "Reading the scene…",
  render: "Painting the moment…",
};

/**
 * **Create image** — the control at the foot of the transcript, below the last beat.
 *
 * Rendered by `StoryPlayerView` only **between** turns — once a session exists and no
 * turn is streaming — so it never offers to paint a half-played beat.
 *
 * Idle it is one quiet row: what it does, the compact art-style picker, and **Go**. The
 * picker is idle-only — the look is a decision made *before* painting, and a control that
 * cannot take effect on the render in flight would only invite a click that does nothing.
 * Running, it becomes the
 * landscape frame the picture will occupy, washed by `.mytheca-wash` so the wait
 * reads as work under way, with the current stage named in a polite live region
 * (`prompt` → `render`). Reduced motion keeps the frame and drops the wash, per
 * the global rule in `styles/themes.css`.
 *
 * Presentational: the stream itself lives on `useScenePlay.createImage`.
 */
export function CreateImageBar({
  onCreate,
  running = false,
  stage = null,
  error = null,
  className,
}: {
  onCreate: (artStyle?: ArtStyleId) => void;
  running?: boolean;
  stage?: "prompt" | "render" | null;
  error?: string | null;
  className?: string;
}) {
  // Owned here rather than lifted: the choice lives exactly as long as this control does,
  // and nothing above it needs to read it. `null` means the operator's Options default,
  // which the picker shows selected and the backend resolves.
  const [artStyle, setArtStyle] = useState<ArtStyleId | null>(null);
  const status = running ? STAGE_LABEL[stage ?? "prompt"] : "";
  return (
    <section
      aria-label="Create an image of this moment"
      className={cn("mx-auto w-full max-w-[560px]", className)}
    >
      {running ? (
        <div
          className="mytheca-wash flex aspect-[3/2] w-full flex-col items-center justify-center gap-[8px] rounded-[6px] border border-cardbd"
          aria-busy="true"
        >
          <span aria-hidden className="text-[22px] text-mute2">
            ❖
          </span>
          <Eyebrow size={9} tracking="0.16em" color="var(--accent)">
            {status}
          </Eyebrow>
        </div>
      ) : (
        <div className="flex flex-wrap items-center justify-center gap-x-[14px] gap-y-[8px] rounded-[6px] border border-dashed border-hair-strong p-[12px_14px]">
          <div className="text-center sm:text-left">
            <Eyebrow size={9} tracking="0.16em" className="block">
              ❖ Create image
            </Eyebrow>
            <span className="mt-[2px] block font-body text-[12.5px] text-ink-soft">
              Picture the scene as it stands right now.
            </span>
          </div>
          <ArtStylePicker
            value={artStyle}
            onChange={setArtStyle}
            label="Style"
            compact
            className="w-full sm:w-auto"
          />
          <Button variant="secondary" onClick={() => onCreate(artStyle ?? undefined)}>
            Go
          </Button>
        </div>
      )}

      {/* One polite live region for both the stage changes and a failure. */}
      <p role="status" aria-live="polite" className="sr-only">
        {status}
      </p>
      {error ? (
        <p role="alert" className="mt-[8px] text-center font-mono text-[11px] tracking-[0.08em] text-danger">
          {error}
        </p>
      ) : null}
    </section>
  );
}
