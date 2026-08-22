"use client";

import { useId } from "react";
import { FieldLabel } from "@/components/ui/FieldLabel";
import { useArtStyles } from "@/hooks/use-art-styles";
import { cn } from "@/lib/cn";
import type { ArtStyleId } from "@/lib/api";

/**
 * Which look to generate an image in — the one control shared by every image surface:
 * character portraits, setting scene art, scenario establishing art, and the in-play
 * **Create image** bar.
 *
 * Native radios inside a `fieldset`/`legend`, rather than the `ToggleChip` row this
 * resembles. The choice is one-of-three and mutually exclusive, and native radios are what
 * give that for free: arrow keys move between options, only the group takes a tab stop, and
 * a screen reader announces "Art style, Anime, 2 of 3" without a line of ARIA. A row of
 * `aria-pressed` buttons would need every one of those rebuilt by hand.
 *
 * Selection is carried by the border weight and fill as well as the accent colour, so it
 * never rests on colour alone. The visible `<span>` is the label's own content, which keeps
 * the whole pill a click target while the real radio stays focusable and screen-readable.
 *
 * The catalog comes from {@link useArtStyles}. While it is loading — or if the backend is
 * unreachable — this renders nothing rather than an empty box or a spinner: the render
 * button beside it still works, on the operator's stored default.
 */
export function ArtStylePicker({
  value,
  onChange,
  label = "Art style",
  compact = false,
  disabled = false,
  className,
}: {
  /** The selected style. Pass `null`/`undefined` to show the operator's default selected. */
  value?: ArtStyleId | null;
  onChange: (style: ArtStyleId) => void;
  label?: string;
  /** Drops the blurbs and tightens the row — for the in-play bar, where space is scarce. */
  compact?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  const { styles, defaultStyle } = useArtStyles();
  const name = useId();
  const selected = value ?? defaultStyle;

  if (styles.length === 0) return null;

  return (
    <fieldset className={cn("min-w-0", className)} disabled={disabled}>
      <legend className="contents">
        <FieldLabel>{label}</FieldLabel>
      </legend>
      <div className={cn("flex flex-wrap", compact ? "gap-[6px]" : "gap-[8px]")}>
        {styles.map((style) => {
          const isSelected = style.id === selected;
          return (
            <label
              key={style.id}
              className={cn(
                "press relative flex cursor-pointer items-center rounded-full border",
                "touch-target focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent",
                compact ? "px-[11px] py-[5px]" : "flex-col items-start px-[12px] py-[7px]",
                isSelected
                  ? "border-[1.5px] border-accent bg-card2 text-accent"
                  : "border-field-bd bg-field text-ink-soft hover:border-hair-strong hover:bg-hover hover:text-ink",
                disabled && "cursor-not-allowed opacity-45",
              )}
            >
              {/* Visually hidden but focusable and hit-testable — the pill is the target. */}
              <input
                type="radio"
                name={name}
                value={style.id}
                checked={isSelected}
                onChange={() => onChange(style.id)}
                disabled={disabled}
                className="absolute inset-0 cursor-[inherit] opacity-0"
              />
              <span
                className={cn(
                  "font-body text-[13px] leading-[1.3]",
                  isSelected && "font-semibold",
                )}
              >
                {style.label}
              </span>
              {compact ? null : (
                <span className="mt-[1px] font-body text-[11.5px] leading-[1.35] text-mute">
                  {style.blurb}
                </span>
              )}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
