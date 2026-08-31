"use client";

import { useTheme } from "@/hooks/use-theme";
import { THEMES } from "@/lib/theme";

/** The three-dot theme picker (Parchment / Ember / Slate). */
export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="group"
      aria-label="Theme"
      className="flex items-center gap-xs rounded-full border border-field-bd bg-field px-sm py-2xs"
    >
      {THEMES.map((option) => {
        const active = theme === option.key;
        return (
          <button
            key={option.key}
            type="button"
            onClick={() => setTheme(option.key)}
            aria-label={option.label}
            aria-pressed={active}
            title={option.label}
            className="h-[18px] w-[18px] cursor-pointer rounded-full hover-grow"
            style={{
              background: option.swatch,
              boxShadow: active
                ? "0 0 0 2px var(--field-bg), 0 0 0 4px var(--accent)"
                : "0 0 0 1px rgba(120,90,40,.3)",
            }}
          />
        );
      })}
    </div>
  );
}
