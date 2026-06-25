"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { Monogram } from "@/components/ui/Monogram";
import { cn } from "@/lib/cn";

const LINK =
  "cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase enabled:hover:underline disabled:opacity-40";

/**
 * Portrait editor pop-up — the "own page" for a character's portrait, opened from
 * the compact preview's **Edit image** button in {@link CharacterModal}. It holds
 * everything image-related: the rendered WebP (or monogram placeholder) preview,
 * the editable watercolor positive/negative prompts, a **Generate prompts** action
 * (written from the character's current context), and a **Generate portrait** render.
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
}) {
  if (!open) return null;
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
            onClick={onGeneratePrompts}
            disabled={!hasDescription || generatingPrompts}
            className={cn(LINK, "mb-[6px]")}
          >
            {generatingPrompts ? "Writing…" : "❖ Generate prompts"}
          </button>
        </div>
        <p className="mt-[6px] mb-[14px] font-body text-[12.5px] text-ink-soft">
          A watercolor portrait via ComfyUI — accurate to their species/race, look,
          and personality. Generate the prompts from the character&apos;s context,
          tweak, then render.
        </p>

        <div className="md:flex md:gap-[18px]">
          <div className="md:min-w-0 md:flex-1">
            <TextArea
              label="Positive prompt"
              aria-label="Portrait positive prompt"
              rows={3}
              placeholder="Short comma-separated phrases — subject & species first, then features, attire, expression, then watercolor style."
              value={positive}
              onChange={(e) => onPositiveChange(e.target.value)}
            />
            <TextArea
              label="Negative prompt"
              aria-label="Portrait negative prompt"
              rows={2}
              placeholder="What to avoid — e.g. blurry, extra limbs, text, watermark."
              value={negative}
              onChange={(e) => onNegativeChange(e.target.value)}
              className="mt-[12px]"
            />
            <Button
              onClick={onGeneratePortrait}
              disabled={!canRenderPortrait || generatingPortrait}
              className="mt-[12px]"
            >
              {generatingPortrait ? "Rendering… (this can take a moment)" : "❖ Generate portrait"}
            </Button>
          </div>
          {/* Preview — the rendered WebP, or a monogram placeholder. */}
          <div className="mt-[14px] flex flex-none justify-center md:mt-0">
            <div
              className="flex h-[220px] w-[165px] items-center justify-center overflow-hidden rounded-[6px] border border-cardbd bg-field"
              style={{ borderColor: color }}
            >
              {portraitUrl ? (
                // eslint-disable-next-line @next/next/no-img-element -- generated portrait from our media mount
                <img
                  src={portraitUrl}
                  alt={`Portrait of ${name || "the character"}`}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex flex-col items-center gap-[8px] px-[10px] text-center">
                  <Monogram mono={mono} color={color} size={64} ring={3} fontSize={26} />
                  <span className="font-mono text-[9px] tracking-[0.1em] text-mute2 uppercase">
                    No portrait yet
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {error ? (
          <p role="alert" className="mt-4 font-body text-[13px] text-accent">
            {error}
          </p>
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
