"use client";

import { useEffect, useId, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import type { Storyline } from "@/lib/types";

/**
 * The header storyline switcher: the active storyline's name is a dropdown that
 * lists every storyline (each owns its own cast/settings/scenarios) and offers
 * "+ New Storyline". Closes on outside-click and Escape (mirrors CreateMenu).
 */
export function StorylineMenu({
  storylines,
  activeId,
  onSwitch,
  onCreate,
}: {
  storylines: Storyline[];
  activeId: string;
  onSwitch: (id: string) => void;
  onCreate: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const active = storylines.find((s) => s.id === activeId) ?? storylines[0];

  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node))
        setOpen(false);
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
        aria-controls={menuId}
        title="Switch storyline"
        className="group flex items-center gap-[9px] rounded-[3px] border border-cardbd bg-card px-[12px] py-[5px] hover:border-accent hover:bg-card2 focus-visible:border-accent"
      >
        <span aria-hidden className="text-[13px] text-gold">
          ◆
        </span>
        <span className="font-display text-[18px] font-bold uppercase leading-none tracking-[0.12em] text-ink">
          {active?.title ?? "Storyline"}
        </span>
        <svg
          aria-hidden
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={cn(
            "-mr-[2px] text-mute transition-transform group-hover:text-accent",
            open && "rotate-180",
          )}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open ? (
        <div
          id={menuId}
          aria-label="Switch storyline"
          className="absolute top-[38px] left-0 z-40 w-[268px] rounded-[4px] border border-cardbd bg-card p-[7px] shadow-[0_16px_40px_rgba(20,12,4,.5)]"
        >
          <div className="px-[11px] pt-[5px] pb-[8px] font-mono text-[8.5px] uppercase tracking-[0.18em] text-mute2">
            Storylines
          </div>
          {storylines.map((s) => {
            const isActive = s.id === activeId;
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => {
                  onSwitch(s.id);
                  setOpen(false);
                }}
                aria-current={isActive ? "true" : undefined}
                className={cn(
                  "flex w-full items-start gap-[10px] rounded-[3px] px-[11px] py-[9px] text-left hover:bg-card2",
                  isActive && "bg-card2",
                )}
              >
                <span
                  aria-hidden
                  className={cn(
                    "mt-[2px] w-3 flex-none text-center text-[11px]",
                    isActive ? "text-accent" : "text-transparent",
                  )}
                >
                  ✓
                </span>
                <span className="flex min-w-0 flex-col gap-[2px]">
                  <span className="font-display text-[14px] font-semibold text-ink">
                    {s.title}
                  </span>
                  <span className="font-mono text-[8.5px] tracking-[0.04em] text-mute">
                    {s.scenarios.length} scenario
                    {s.scenarios.length === 1 ? "" : "s"} · {s.characters.length}{" "}
                    cast · {s.settings.length} setting
                    {s.settings.length === 1 ? "" : "s"}
                  </span>
                </span>
              </button>
            );
          })}
          <div className="my-[6px] border-t border-hair" />
          <button
            type="button"
            onClick={() => {
              onCreate();
              setOpen(false);
            }}
            className="flex w-full items-center gap-[10px] rounded-[3px] px-[11px] py-[9px] text-left hover:bg-card2"
          >
            <span aria-hidden className="w-3 flex-none text-center text-[14px] text-gold">
              ＋
            </span>
            <span className="font-display text-[14px] font-semibold text-ink">
              New Storyline
            </span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
