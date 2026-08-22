"use client";

import { useTheme } from "@/hooks/use-theme";
import { useFontSize } from "@/hooks/use-font-size";
import { useShortcutsEnabled } from "@/hooks/use-shortcuts-enabled";
import { writeShortcutsEnabled } from "@/lib/shortcuts";
import { THEMES } from "@/lib/theme";
import { FONT_SIZES } from "@/lib/font-size";
import { cn } from "@/lib/cn";

/** Theme + font-size picker as a full panel. Both choices persist via `localStorage`. */
export function AppearanceTab() {
  const { theme, setTheme } = useTheme();
  const { fontSize, setFontSize } = useFontSize();
  const shortcutsEnabled = useShortcutsEnabled();

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

      {/* WCAG 2.1.4 (Character Key Shortcuts, Level A). `/` and `?` are single-character
          bindings on `document`; the criterion requires a way to turn them off, a way to
          remap them, or that they are active only on focus. The scene's hook already stands
          down inside text fields, which is necessary and is none of the three — a
          screen-reader user browsing the transcript is not in a text field, and their
          assistive technology sends single characters to navigate. This is the way off. */}
      <section aria-labelledby="shortcuts-heading">
        <h2 id="shortcuts-heading" className="font-display text-[19px] font-semibold text-ink">
          Keyboard shortcuts
        </h2>
        <p className="mt-[4px] mb-[18px] font-body text-[14px] text-ink-soft">
          In a scene, <kbd className="font-mono text-[13px]">/</kbd> jumps to the message box
          and <kbd className="font-mono text-[13px]">?</kbd> opens the shortcut sheet. Turn
          them off if they collide with your screen reader&rsquo;s own single-key navigation.
          <kbd className="ml-[4px] font-mono text-[13px]">Esc</kbd> and the arrow keys are
          unaffected either way.
        </p>

        <button
          type="button"
          role="switch"
          aria-checked={shortcutsEnabled}
          onClick={() => writeShortcutsEnabled(!shortcutsEnabled)}
          className={cn(
            "flex min-w-[220px] items-center justify-between gap-[14px] rounded-[4px] border px-[14px] py-[12px] text-left",
            shortcutsEnabled
              ? "border-accent bg-card2"
              : "border-cardbd bg-card hover:border-hair-strong hover:bg-hover",
          )}
        >
          <span className="flex flex-col">
            <span className="font-display text-[15px] font-semibold text-ink">
              Single-key shortcuts
            </span>
            <span className="mt-[2px] font-body text-[13px] text-ink-soft">
              {shortcutsEnabled ? "On — / and ? are active in a scene" : "Off — / and ? do nothing"}
            </span>
          </span>
          <span aria-hidden className="font-mono text-[11px] tracking-[0.12em] text-accent uppercase">
            {shortcutsEnabled ? "On" : "Off"}
          </span>
        </button>
      </section>
    </div>
  );
}
