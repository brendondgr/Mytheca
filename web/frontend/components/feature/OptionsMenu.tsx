"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import { useMediaQuery } from "@/hooks/use-media-query";
import { useTheme } from "@/hooks/use-theme";
import { THEMES } from "@/lib/theme";

/**
 * The "Options ▾" header dropdown (sits to the right of Create). Two entries:
 * a **Settings Menu** link to `/options`, and a quick **Appearance** theme
 * selector (persisted across sessions via the `mytheca-theme` machinery).
 * Closes on outside-click and Escape, mirroring `CreateMenu`.
 */
export function OptionsMenu() {
  const [open, setOpen] = useState(false);
  const { theme, setTheme } = useTheme();
  const ref = useRef<HTMLDivElement>(null);
  // `false` during SSR and wherever `matchMedia` is absent, so the server renders the
  // NARROW form — the plain link, which works everywhere and cannot strand anyone.
  const wide = useMediaQuery("(min-width: 640px)");

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

  // Below `sm` this is a LINK, not a dropdown.
  //
  // The dropdown holds two things: a link to `/options` and the theme swatches. On a phone
  // the first is the whole reason anyone opens it, and the second is on the page it leads
  // to (Appearance). A popover whose only real content is a link to a page is a tap that
  // buys a second tap.
  if (!wide) {
    return (
      <Link
        href="/options"
        aria-label="Options"
        title="Options — models, appearance, defaults"
        className="flex h-control w-control touch-target-overlay items-center justify-center rounded-xs border border-field-bd bg-field text-ink hover:border-accent hover:bg-hover hover:text-accent-ink"
      >
        <Icon name="sliders" size={16} />
      </Link>
    );
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="options-menu"
        className="flex h-control items-center gap-xs rounded-xs border border-field-bd bg-field px-lg font-mono text-eyebrow tracking-[0.1em] text-ink uppercase hover:border-accent hover:bg-hover hover:text-accent-ink aria-expanded:border-accent aria-expanded:text-accent-ink"
      >
        <Icon name="sliders" size={15} />
        Options
      </button>
      {open ? (
        <div
          id="options-menu"
          aria-label="Options"
          className="absolute top-3xl right-0 z-40 w-[244px] mytheca-menu p-xs"
        >
          <Link
            href="/options"
            onClick={() => setOpen(false)}
            className="flex w-full items-center gap-md rounded-xs px-md py-sm text-left hover:bg-hover"
          >
            <span className="flex w-4 justify-center text-gold-ink" aria-hidden>
              <Icon name="sliders" size={14} />
            </span>
            <span className="flex flex-col gap-3xs">
              <span className="font-display text-body-sm font-semibold text-ink">
                Settings Menu
              </span>
              <span className="font-mono text-tag tracking-[0.04em] text-mute">
                models · appearance · defaults
              </span>
            </span>
          </Link>

          <div className="mt-2xs border-t border-hair px-md pt-sm pb-2xs">
            <div className="mb-sm font-mono text-tag tracking-[0.18em] text-mute uppercase">
              Appearance
            </div>
            <div role="group" aria-label="Theme" className="flex items-center gap-sm">
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
                    className="flex items-center justify-center rounded-full border border-field-bd bg-field p-xs hover:border-accent hover:bg-hover"
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
