"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { cn } from "@/lib/cn";

const LINK =
  "cursor-pointer font-mono text-[10px] tracking-[0.08em] text-accent uppercase enabled:hover:underline disabled:opacity-40";

/**
 * Scene-art editor pop-up — the "own page" for a setting's establishing image,
 * opened from the compact preview's **Edit image** button in {@link SettingModal}.
 * It holds everything image-related: the rendered WebP (or placeholder) preview,
 * the editable watercolor positive/negative prompts, a **Generate prompts** action
 * (written from the place's current context), and a **Generate scene art** render.
 *
 * The setting counterpart to {@link PortraitModal}: a landscape (16:9) frame for a
 * place rather than a square head-and-shoulders portrait. Purely presentational;
 * all generation handlers live on the parent's `useLibraryState` and are passed in.
 */
export function SceneArtModal({
  open,
  onClose,
  name,
  imageUrl,
  positive,
  negative,
  onPositiveChange,
  onNegativeChange,
  hasDescription,
  generatingPrompts,
  onGeneratePrompts,
  canRender,
  generatingImage,
  onGenerate,
  error,
  activeField = null,
}: {
  open: boolean;
  onClose: () => void;
  name: string;
  imageUrl: string | null;
  positive: string;
  negative: string;
  onPositiveChange: (value: string) => void;
  onNegativeChange: (value: string) => void;
  hasDescription: boolean;
  generatingPrompts: boolean;
  onGeneratePrompts: () => void;
  canRender: boolean;
  generatingImage: boolean;
  onGenerate: () => void;
  error: string | null;
  /** The prompt field being written right now (live highlight). */
  activeField?: string | null;
}) {
  if (!open) return null;
  return (
    <Modal
      open
      onClose={onClose}
      labelledBy="scene-art-modal-title"
      className="sm:w-[560px] md:w-[760px]"
      z={70}
    >
      <div className="p-[22px_26px_24px]">
        <div className="flex items-end justify-between gap-[10px]">
          <div
            id="scene-art-modal-title"
            className="font-display text-[22px] font-bold text-ink"
          >
            Scene art
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
          A watercolor establishing shot of the place via ComfyUI — the location
          itself, no people. Generate the prompts from the setting&apos;s context,
          tweak, then render.
        </p>

        <div>
          <TextArea
            label="Positive prompt"
            aria-label="Scene-art positive prompt"
            rows={3}
            placeholder="Short comma-separated phrases — the place & its kind first, then features, materials, light, weather, mood, then watercolor style."
            value={positive}
            onChange={(e) => onPositiveChange(e.target.value)}
            className={activeField === "_sceneArtPositive" ? "mytheca-field-active" : undefined}
          />
          <TextArea
            label="Negative prompt"
            aria-label="Scene-art negative prompt"
            rows={2}
            placeholder="What to avoid — e.g. people, figures, text, watermark, blurry."
            value={negative}
            onChange={(e) => onNegativeChange(e.target.value)}
            className={cn(
              "mt-[12px]",
              activeField === "_sceneArtNegative" && "mytheca-field-active",
            )}
          />
          <Button
            onClick={onGenerate}
            disabled={!canRender || generatingImage}
            className="mt-[12px]"
          >
            {generatingImage ? "Rendering… (this can take a moment)" : "❖ Generate scene art"}
          </Button>
        </div>

        {/* Preview — the rendered WebP, or a placeholder, in a 16:9 frame. */}
        <div className="mt-[16px]">
          <div className="aspect-[16/9] w-full overflow-hidden rounded-[6px] border border-cardbd bg-field">
            {imageUrl ? (
              // eslint-disable-next-line @next/next/no-img-element -- generated scene art from our media mount
              <img
                src={imageUrl}
                alt={`Establishing image of ${name || "the place"}`}
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full flex-col items-center justify-center gap-[6px] text-center">
                <span aria-hidden className="text-[22px] text-mute2">
                  ◇
                </span>
                <span className="font-mono text-[9px] tracking-[0.1em] text-mute2 uppercase">
                  No scene art yet
                </span>
              </div>
            )}
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
