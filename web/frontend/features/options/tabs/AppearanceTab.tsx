"use client";

import { useTheme } from "@/hooks/use-theme";
import { useFontSize } from "@/hooks/use-font-size";
import { THEMES } from "@/lib/theme";
import { FONT_SIZES } from "@/lib/font-size";
import { cn } from "@/lib/cn";

/** Theme + font-size picker as a full panel. Both choices persist via `localStorage`. */
export function AppearanceTab() {
  const { theme, setTheme } = useTheme();
  const { fontSize, setFontSize } = useFontSize();

  return (
    <div className="flex flex-col gap-[28px]">
      <section aria-labelledby="appearance-heading">
        <h2 id="appearance-heading" className="font-display text-[19px] font-semibold text-ink">
          Appearance
        </h2>
        <p className="mt-[4px] mb-[18px] font-body text-[14px] text-ink-soft">
          Pick a manuscript theme. Your choice is saved to this browser and persists across sessions.
        </p>

        <div role="radiogroup" aria-label="Theme" className="flex flex-wrap gap-[14px]">
          {THEMES.map((option) => {
            const active = theme === option.key;
            return (
              <button
                key={option.key}
                type="button"
                role="radio"
                aria-checked={active}
                aria-label={option.label}
                title={option.label}
                onClick={() => setTheme(option.key)}
                className={cn(
                  "flex items-center justify-center rounded-[4px] border p-[16px]",
                  active ? "border-accent bg-card2" : "border-cardbd bg-card hover:border-hair-strong hover:bg-hover",
                )}
              >
                <span
                  className="h-[40px] w-[40px] flex-none rounded-full"
                  style={{
                    background: option.swatch,
                    boxShadow: active
                      ? "0 0 0 2px var(--card-bg), 0 0 0 4px var(--accent)"
                      : "0 0 0 1px rgba(120,90,40,.3)",
                  }}
                  aria-hidden
                />
              </button>
            );
          })}
        </div>
      </section>

      <hr className="border-hair" />

      <section aria-labelledby="fontsize-heading">
        <h2 id="fontsize-heading" className="font-display text-[19px] font-semibold text-ink">
          Text size
        </h2>
        <p className="mt-[4px] mb-[18px] font-body text-[14px] text-ink-soft">
          Choose how large labels, card text, and UI elements appear. Saved to this browser.
        </p>

        <div role="radiogroup" aria-label="Text size" className="flex flex-wrap gap-[10px]">
          {FONT_SIZES.map((option) => {
            const active = fontSize === option.key;
            return (
              <button
                key={option.key}
                type="button"
                role="radio"
                aria-checked={active}
                aria-label={option.label}
                onClick={() => setFontSize(option.key)}
                className={cn(
                  "flex min-w-[120px] flex-col rounded-[4px] border px-[14px] py-[12px] text-left",
                  active ? "border-accent bg-card2" : "border-cardbd bg-card hover:border-hair-strong hover:bg-hover",
                )}
              >
                <span className="font-display text-[15px] font-semibold text-ink">
                  {option.label}
                </span>
                <span className="mt-[2px] font-body text-[13px] text-ink-soft">
                  {option.description}
                </span>
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
