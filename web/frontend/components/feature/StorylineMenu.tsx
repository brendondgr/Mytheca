"use client";

import { useEffect, useId, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { DEFAULT_SEAL_COLOR, DEFAULT_SEAL_SYMBOL } from "@/lib/seals";
import type { Storyline } from "@/lib/types";

function PencilIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  );
}

function DocsIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="M8 13h8" />
      <path d="M8 17h8" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M3 6h18" />
      <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    </svg>
  );
}

/**
 * Shows scenario / cast / setting totals — each count on its own line.
 *
 * Uses API count fields as the primary source so non-active storylines
 * display accurate numbers without loading their full child arrays.
 */
function StorylineCounts({ storyline: s }: { storyline: Storyline }) {
  const scenarios = s.scenarioCount ?? s.scenarios.length;
  const characters = s.characterCount ?? s.characters.length;
  const settings = s.settingCount ?? s.settings.length;
  return (
    // pl-[55px] = 11px outer padding + w-3 checkmark (12px) + gap-[10px] + w-3 symbol (12px) + gap-[10px]
    // aligns each count under the title text above
    <div className="flex flex-col pb-[10px] pl-[55px] font-mono text-[12px] leading-[1.7] tracking-[0.03em] text-mute">
      <span>{scenarios} scenario{scenarios === 1 ? "" : "s"}</span>
      <span>{characters} cast</span>
      <span>{settings} setting{settings === 1 ? "" : "s"}</span>
    </div>
  );
}

/**
 * The header storyline switcher: the active storyline's name is a dropdown that
 * lists every storyline (each owns its own cast/settings/scenarios), with
 * per-row Edit / Delete actions, and offers "+ New Storyline". Closes on
 * outside-click and Escape (mirrors CreateMenu).
 */
export function StorylineMenu({
  storylines,
  activeId,
  onSwitch,
  onCreate,
  onEdit,
  onConfigurePrompts,
  onDocuments,
  onDelete,
}: {
  storylines: Storyline[];
  activeId: string;
  onSwitch: (id: string) => void;
  onCreate: () => void;
  onEdit: (id: string) => void;
  onConfigurePrompts: (id: string) => void;
  onDocuments: (id: string) => void;
  onDelete: (id: string) => void;
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
        <span
          aria-hidden
          className="text-[13px] leading-none"
          style={{ color: active?.symbolColor || DEFAULT_SEAL_COLOR }}
        >
          {active?.symbol || DEFAULT_SEAL_SYMBOL}
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
          className="absolute top-[38px] left-0 z-40 w-[280px] rounded-[4px] border border-cardbd bg-card p-[7px] shadow-[0_16px_40px_rgba(20,12,4,.5)]"
        >
          <div className="px-[11px] pt-[5px] pb-[8px] font-mono text-[11px] uppercase tracking-[0.18em] text-mute2">
            Storylines
          </div>
          {storylines.map((s) => {
            const isActive = s.id === activeId;
            return (
              <div
                key={s.id}
                className={cn("rounded-[3px] hover:bg-card2", isActive && "bg-card2")}
              >
                {/* Title row: checkmark + symbol + title + edit/delete right-aligned */}
                <div className="flex items-center gap-[10px] px-[11px] pt-[9px] pb-[3px]">
                  <button
                    type="button"
                    onClick={() => {
                      onSwitch(s.id);
                      setOpen(false);
                    }}
                    aria-current={isActive ? "true" : undefined}
                    className="flex min-w-0 flex-1 items-center gap-[10px] text-left"
                  >
                    <span
                      aria-hidden
                      className={cn(
                        "w-3 flex-none text-center text-[11px]",
                        isActive ? "text-accent" : "text-transparent",
                      )}
                    >
                      ✓
                    </span>
                    <span
                      aria-hidden
                      className="w-3 flex-none text-center text-[13px] leading-none"
                      style={{ color: s.symbolColor || DEFAULT_SEAL_COLOR }}
                    >
                      {s.symbol || DEFAULT_SEAL_SYMBOL}
                    </span>
                    <span className="min-w-0 flex-1 truncate font-display text-[15px] font-semibold text-ink">
                      {s.title}
                    </span>
                  </button>
                  <div className="flex flex-none items-center gap-[1px]">
                    <button
                      type="button"
                      aria-label={`Writing prompts for ${s.title}`}
                      title="Writing prompts"
                      onClick={() => {
                        onConfigurePrompts(s.id);
                        setOpen(false);
                      }}
                      className="rounded-[3px] p-[6px] text-mute hover:bg-field hover:text-accent focus-visible:text-accent"
                    >
                      <GearIcon />
                    </button>
                    <button
                      type="button"
                      aria-label={`Documents for ${s.title}`}
                      title="Documents"
                      onClick={() => {
                        onDocuments(s.id);
                        setOpen(false);
                      }}
                      className="rounded-[3px] p-[6px] text-mute hover:bg-field hover:text-accent focus-visible:text-accent"
                    >
                      <DocsIcon />
                    </button>
                    <button
                      type="button"
                      aria-label={`Edit ${s.title}`}
                      title="Edit storyline"
                      onClick={() => {
                        onEdit(s.id);
                        setOpen(false);
                      }}
                      className="rounded-[3px] p-[6px] text-mute hover:bg-field hover:text-accent focus-visible:text-accent"
                    >
                      <PencilIcon />
                    </button>
                    <button
                      type="button"
                      aria-label={`Delete ${s.title}`}
                      title="Delete storyline"
                      onClick={() => {
                        onDelete(s.id);
                        setOpen(false);
                      }}
                      className="rounded-[3px] p-[6px] text-mute hover:bg-field hover:text-danger focus-visible:text-danger"
                    >
                      <TrashIcon />
                    </button>
                  </div>
                </div>
                {/* Counts: each on its own line, indented to align with the title */}
                <StorylineCounts storyline={s} />
              </div>
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
            <span className="font-display text-[15px] font-semibold text-ink">
              New Storyline
            </span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
