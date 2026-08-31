"use client";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { cn } from "@/lib/cn";
import {
  DEFAULT_SEAL_COLOR,
  DEFAULT_SEAL_SYMBOL,
  SEAL_COLORS,
  SEAL_SYMBOLS,
} from "@/lib/seals";

/**
 * Seal editor pop-up — the "own page" for a storyline's seal, opened from the
 * compact Seal row's **Edit** button on the New Storyline page (`StorylineCreatorView`;
 * mirrors the Character creator's PortraitModal). It holds everything seal-related: a large
 * live preview, the expanded shape grid, a curated color palette, and a free
 * **color wheel** for any custom hex. Purely presentational — the chosen
 * `symbol`/`symbolColor` flow back through the parent's draft setters.
 */
export function SealModal({
  open,
  onClose,
  symbol,
  color,
  onSymbolChange,
  onColorChange,
}: {
  open: boolean;
  onClose: () => void;
  symbol: string;
  color: string;
  onSymbolChange: (symbol: string) => void;
  onColorChange: (color: string) => void;
}) {
  if (!open) return null;
  const seal = symbol || DEFAULT_SEAL_SYMBOL;
  const sealColor = color || DEFAULT_SEAL_COLOR;
  // Surface a custom (off-palette) color as an extra selected swatch.
  const isCustom = !SEAL_COLORS.includes(sealColor);

  return (
    <Modal
      open
      onClose={onClose}
      labelledBy="seal-modal-title"
      className="sm:w-[520px] md:w-[600px]"
      z={70}
    >
      <div className="p-[22px_26px_24px]">
        <div
          id="seal-modal-title"
          className="font-display text-step-2 font-bold text-ink"
        >
          Seal
        </div>
        <p className="mt-xs mb-lg font-body text-eyebrow text-ink-soft">
          The mark shown beside this world&apos;s name. Pick a shape and color — or
          dial in any custom color with the wheel.
        </p>

        <div className="flex items-start gap-lg">
          {/* Large live preview */}
          <div
            aria-hidden
            className="flex h-[96px] w-[96px] flex-none items-center justify-center rounded-md border border-cardbd bg-field text-step-3 text-entity-strong leading-none"
            style={{ ["--entity" as string]: sealColor }}
          >
            {seal}
          </div>

          <div className="min-w-0 flex-1">
            <FieldLabel>Shape</FieldLabel>
            <div
              role="group"
              aria-label="Seal symbol"
              className="flex flex-wrap gap-xs"
            >
              {SEAL_SYMBOLS.map((sym) => (
                <button
                  key={sym}
                  type="button"
                  aria-label={`Symbol ${sym}`}
                  aria-pressed={seal === sym}
                  onClick={() => onSymbolChange(sym)}
                  className={cn(
                    "flex h-[34px] w-[34px] items-center justify-center rounded-sm border text-step-1 leading-none focus-visible:border-accent",
                    seal === sym
                      ? "border-accent bg-card2 text-ink"
                      : "border-cardbd bg-field text-ink-soft hover:border-accent hover:bg-hover hover:text-ink",
                  )}
                >
                  {sym}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Colors + custom wheel */}
        <div className="mt-lg">
          <FieldLabel>Color</FieldLabel>
          <div className="flex flex-wrap items-center gap-sm">
            <div role="group" aria-label="Seal color" className="flex flex-wrap gap-sm">
              {SEAL_COLORS.map((col) => (
                <button
                  key={col}
                  type="button"
                  aria-label={`Color ${col}`}
                  aria-pressed={sealColor === col}
                  onClick={() => onColorChange(col)}
                  className="h-[26px] w-[26px] rounded-full focus-visible:outline-none"
                  style={{
                    background: col,
                    boxShadow:
                      sealColor === col
                        ? `0 0 0 2px var(--modal-bg), 0 0 0 4px ${col}`
                        : "0 0 0 1px rgba(0,0,0,.15)",
                  }}
                />
              ))}
            </div>

            {/* Custom color wheel — native picker, unlimited hex. */}
            <label
              className="flex cursor-pointer items-center gap-xs rounded-full border border-cardbd bg-field px-sm py-2xs"
              title="Custom color"
            >
              <span
                aria-hidden
                className="h-[20px] w-[20px] rounded-full"
                style={{
                  background: isCustom
                    ? sealColor
                    : "conic-gradient(red, orange, yellow, lime, cyan, blue, magenta, red)",
                  boxShadow: isCustom ? `0 0 0 2px ${sealColor}` : "0 0 0 1px rgba(0,0,0,.15)",
                }}
              />
              <span className="font-mono text-eyebrow tracking-[0.06em] text-ink-soft uppercase">
                Custom
              </span>
              <input
                type="color"
                aria-label="Custom seal color"
                value={sealColor}
                onChange={(e) => onColorChange(e.target.value)}
                className="sr-only"
              />
            </label>
          </div>
        </div>

        <div className="mt-xl flex justify-end">
          <Button variant="ghost" onClick={onClose}>
            Done
          </Button>
        </div>
      </div>
    </Modal>
  );
}
