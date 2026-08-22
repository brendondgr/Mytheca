"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { Monogram } from "@/components/ui/Monogram";
import { SmartImage } from "@/components/ui/SmartImage";
import { ArtStylePicker } from "@/components/feature/ArtStylePicker";
import { cn } from "@/lib/cn";
import type { ArtStyleId } from "@/lib/api";

const LINK =
  "cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase enabled:hover:underline disabled:opacity-40";

/** The `messageOf()` fallback in useLibraryState for a non-`Error` throw — too
 * vague to leave on screen, so a retry-able failure names the operation instead. */
const VAGUE_ERROR = "Something went wrong.";

/**
 * Portrait editor pop-up — the "own page" for a character's portrait, opened from
 * the compact preview's **Edit image** button in {@link CharacterModal}. It holds
 * everything image-related: the rendered WebP (or monogram placeholder) preview, the
 * art-style picker, the editable positive/negative prompts, a **Generate prompts** action
 * (written from the character's current context), and a **Generate portrait** render.
 *
 * The style sits above the prompts because it governs both actions below it: the prompts
 * are *written* for it and the render is *painted* in it.
 *
 * A nested {@link Modal} (raised z-index) over the editor — purely presentational;
 * all generation handlers live on the parent's `useLibraryState` and are passed in.
 */
export function PortraitModal({
  open,
  onClose,
  name,
  mono,
  color,
  portraitUrl,
  positive,
  negative,
  onPositiveChange,
  onNegativeChange,
  hasDescription,
  generatingPrompts,
  onGeneratePrompts,
  canRenderPortrait,
  generatingPortrait,
  onGeneratePortrait,
  error,
  activeField = null,
  artStyle = null,
  onArtStyleChange,
}: {
  open: boolean;
  onClose: () => void;
  name: string;
  mono: string;
  color: string;
  portraitUrl: string | null;
  positive: string;
  negative: string;
  onPositiveChange: (value: string) => void;
  onNegativeChange: (value: string) => void;
  hasDescription: boolean;
  generatingPrompts: boolean;
  onGeneratePrompts: () => void;
  canRenderPortrait: boolean;
  generatingPortrait: boolean;
  onGeneratePortrait: () => void;
  error: string | null;
  /** The prompt field being written right now (live highlight). */
  activeField?: string | null;
  /** The chosen look; `null` shows the operator's Options default selected. */
  artStyle?: ArtStyleId | null;
  onArtStyleChange?: (style: ArtStyleId) => void;
}) {
  // Tracks which generate action the Retry control should re-run — whichever
  // of the two was attempted most recently (defaults to the render, the
  // modal's primary action, until either has been tried).
  const [lastAction, setLastAction] = useState<"prompts" | "portrait" | null>(null);

  if (!open) return null;

  function retryFailed() {
    if (lastAction === "prompts") onGeneratePrompts();
    else onGeneratePortrait();
  }

  return (
    <Modal
      open
      onClose={onClose}
      labelledBy="portrait-modal-title"
      className="sm:w-[560px] md:w-[720px]"
      z={70}
    >
      <div className="p-[22px_26px_24px]">
        <div className="flex items-end justify-between gap-[10px]">
          <div
            id="portrait-modal-title"
            className="font-display text-[22px] font-bold text-ink"
          >
            Portrait
          </div>
          <button
            type="button"
            onClick={() => {
              setLastAction("prompts");
              onGeneratePrompts();
            }}
            disabled={!hasDescription || generatingPrompts}
            className={cn(LINK, "mb-[6px]")}
          >
            {generatingPrompts ? "Writing…" : "❖ Generate prompts"}
          </button>
        </div>
        <p className="mt-[6px] mb-[14px] font-body text-[12.5px] text-ink-soft">
          A portrait via ComfyUI — accurate to their species/race, look, and personality.
          Pick a style, generate the prompts from the character&apos;s context, tweak, then
          render.
        </p>

        {onArtStyleChange ? (
          <ArtStylePicker
            value={artStyle}
            onChange={onArtStyleChange}
            disabled={generatingPrompts || generatingPortrait}
            className="mb-[16px]"
          />
        ) : null}

        <div className="md:flex md:gap-[18px]">
          <div className="md:min-w-0 md:flex-1">
            <TextArea
              label="Positive prompt"
              aria-label="Portrait positive prompt"
              rows={3}
              placeholder="Short comma-separated phrases — subject & species first, then features, attire, expression, then style."
              value={positive}
              onChange={(e) => onPositiveChange(e.target.value)}
              className={activeField === "_portraitPositive" ? "mytheca-field-active" : undefined}
            />
            <TextArea
              label="Negative prompt"
              aria-label="Portrait negative prompt"
              rows={2}
              placeholder="What to avoid — e.g. blurry, extra limbs, text, watermark."
              value={negative}
              onChange={(e) => onNegativeChange(e.target.value)}
              className={cn(
                "mt-[12px]",
                activeField === "_portraitNegative" && "mytheca-field-active",
              )}
            />
            <Button
              onClick={() => {
                setLastAction("portrait");
                onGeneratePortrait();
              }}
              disabled={!canRenderPortrait || generatingPortrait}
              className="mt-[12px]"
            >
              {generatingPortrait ? "Rendering… (this can take a moment)" : "❖ Generate portrait"}
            </Button>
          </div>
          {/* Preview — the rendered WebP, or a monogram placeholder. */}
          <div className="mt-[14px] flex flex-none justify-center md:mt-0">
            <div
              className="flex aspect-[2/3] w-[200px] items-center justify-center overflow-hidden rounded-[6px] border border-cardbd bg-field"
              style={{ borderColor: color }}
            >
              <SmartImage
                src={portraitUrl}
                alt={`Portrait of ${name || "the character"}`}
                aspect="2 / 3"
                className="h-full w-full"
                placeholder={
                  <div className="flex flex-col items-center gap-[8px] px-[10px] text-center">
                    <Monogram mono={mono} color={color} size={64} ring={3} fontSize={26} />
                    <span className="font-mono text-[9px] tracking-[0.1em] text-mute2 uppercase">
                      No portrait yet
                    </span>
                  </div>
                }
              />
            </div>
          </div>
        </div>

        {error ? (
          <div className="mt-4 flex flex-wrap items-center gap-[10px]">
            <p role="alert" className="font-body text-[13px] text-accent">
              {error === VAGUE_ERROR
                ? lastAction === "prompts"
                  ? "Could not generate the portrait prompts."
                  : "Could not render the portrait."
                : error}
            </p>
            <Button variant="secondary" onClick={retryFailed}>
              Try again
            </Button>
          </div>
        ) : null}
        <div className="mt-[20px] flex justify-end">
          <Button variant="ghost" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </Modal>
  );
}
