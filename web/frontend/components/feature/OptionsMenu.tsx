"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useTheme } from "@/hooks/use-theme";
import { THEMES } from "@/lib/theme";

/**
 * The "Options ▾" header dropdown (sits to the right of Create). Two entries:
 * a **Settings Menu** link to `/options`, and a quick **Appearance** theme
 * selector (persisted across sessions via the `velora-theme` machinery).
 * Closes on outside-click and Escape, mirroring `CreateMenu`.
 */
export function OptionsMenu() {
  const [open, setOpen] = useState(false);
  const { theme, setTheme } = useTheme();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="options-menu"
        className="rounded-[2px] border border-field-bd bg-field px-[15px] py-[8px] font-mono text-[10.5px] tracking-[0.1em] text-ink uppercase hover:border-accent hover:bg-hover hover:text-accent aria-expanded:border-accent aria-expanded:text-accent"
      >
        Options ▾
      </button>
      {open ? (
        <div
          id="options-menu"
          aria-label="Options"
          className="absolute top-[42px] right-0 z-40 w-[244px] velora-menu p-[7px]"
        >
          <Link
            href="/options"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-[11px] rounded-[3px] px-[11px] py-[9px] text-left hover:bg-hover"
          >
            <span className="w-4 text-center text-[14px] text-gold" aria-hidden>
              ❖
            </span>
            <span className="flex flex-col gap-[2px]">
              <span className="font-display text-[14px] font-semibold text-ink">
                Settings Menu
              </span>
              <span className="font-mono text-tag tracking-[0.04em] text-mute">
                models · appearance · defaults
              </span>
            </span>
          </Link>

          <div className="mt-[5px] border-t border-hair px-[11px] pt-[9px] pb-[4px]">
            <div className="mb-[8px] font-mono text-tag tracking-[0.18em] text-mute uppercase">
              Appearance
            </div>
            <div role="group" aria-label="Theme" className="flex items-center gap-[10px]">
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
                    className="flex items-center justify-center rounded-full border border-field-bd bg-field p-[6px] hover:border-accent"
                  >
                    <span
                      className="h-[18px] w-[18px] rounded-full"
                      style={{
                        background: option.swatch,
                        boxShadow: active
                          ? "0 0 0 2px var(--field-bg), 0 0 0 4px var(--accent)"
                          : "0 0 0 1px rgba(120,90,40,.3)",
                      }}
                    />
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
