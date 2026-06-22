"use client";

import { useTheme } from "@/hooks/use-theme";
import { THEMES } from "@/lib/theme";
import { cn } from "@/lib/cn";

/** Theme picker as a full panel. The choice persists via `localStorage`. */
export function AppearanceTab() {
  const { theme, setTheme } = useTheme();

  return (
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
                active ? "border-accent bg-card2" : "border-cardbd bg-card hover:bg-card2",
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
  );
}
