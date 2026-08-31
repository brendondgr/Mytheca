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
    <div className="flex flex-col pb-sm pl-3xl font-mono text-eyebrow leading-[1.7] tracking-[0.03em] text-mute">
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
        // The visible label is hidden below `md` (the seal and caret carry it there), so the
        // name has to be spelled out — otherwise the trigger reads as "Switch storyline" with
        // no indication of which world is open. Responsive in CSS rather than JS: a second
        // DOM copy would duplicate the accessible name, and a `useMediaQuery` swap would
        // repaint the Library's LCP element on hydration.
        aria-label={active?.title ? `Switch storyline — ${active.title}` : "Switch storyline"}
        title="Switch storyline"
        className="group flex items-center gap-sm rounded-xs border border-cardbd bg-card px-md py-2xs hover:border-accent hover:bg-hover focus-visible:border-accent"
      >
        <span
          aria-hidden
          className="text-label text-entity leading-none"
          style={{ ["--entity" as string]: active?.symbolColor || DEFAULT_SEAL_COLOR }}
        >
          {active?.symbol || DEFAULT_SEAL_SYMBOL}
        </span>
        <span className="hidden font-display text-step-1 font-bold uppercase leading-none tracking-[0.12em] text-ink md:inline">
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
            "-mr-3xs text-mute transition-transform group-hover:text-accent-ink",
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
          // Below `md` the panel is pinned to the VIEWPORT, not to the trigger. Capping its
          // width is not enough and was measured not to be: at 320 the trigger sits 203px
          // from the left (wordmark + brandmark precede it), so an `absolute left-0` panel
          // starts at 203 and runs to 483 whatever width it is given. `min(280px, 100vw-24px)`
          // evaluates to 280 there and changes nothing. Anchoring to the viewport is the only
          // form that cannot overhang, at any width, for any trigger position.
          // The height cap is not decoration either: measured at 320 with a real library
          // this panel is 4912px tall, and `fixed` means the page cannot scroll it into
          // view — so without an inner scroller every world past the first few would be
          // unreachable. Capped at every width, because an unbounded popover is no better
          // on a desktop, only less obviously broken.
          className="fixed inset-x-[12px] top-3xl z-40 flex max-h-[calc(100dvh-70px)] w-auto flex-col overflow-y-auto mytheca-menu p-xs md:absolute md:inset-x-auto md:top-2xl md:left-0 md:max-h-[calc(100dvh-60px)] md:w-[280px]"
        >
          <div className="px-md pt-2xs pb-sm font-mono text-eyebrow uppercase tracking-[0.18em] text-mute2">
            Storylines
          </div>
          {storylines.map((s) => {
            const isActive = s.id === activeId;
            return (
              <div
                key={s.id}
                className={cn("rounded-xs hover:bg-hover", isActive && "bg-hover")}
              >
                {/* Title row: checkmark + symbol + title + edit/delete right-aligned */}
                <div className="flex items-center gap-sm px-md pt-sm pb-3xs">
                  <button
                    type="button"
                    onClick={() => {
                      onSwitch(s.id);
                      setOpen(false);
                    }}
                    aria-current={isActive ? "true" : undefined}
                    className="flex min-w-0 flex-1 items-center gap-sm text-left"
                  >
                    <span
                      aria-hidden
                      className={cn(
                        "w-3 flex-none text-center text-eyebrow",
                        isActive ? "text-accent-ink" : "text-transparent",
                      )}
                    >
                      ✓
                    </span>
                    <span
                      aria-hidden
                      className="w-3 flex-none text-center text-label leading-none"
                      style={{ color: s.symbolColor || DEFAULT_SEAL_COLOR }}
                    >
                      {s.symbol || DEFAULT_SEAL_SYMBOL}
                    </span>
                    <span className="min-w-0 flex-1 truncate font-display text-body-sm font-semibold text-ink">
                      {s.title}
                    </span>
                  </button>
                  <div className="flex flex-none items-center gap-3xs">
                    <button
                      type="button"
                      aria-label={`Writing prompts for ${s.title}`}
                      title="Writing prompts"
                      onClick={() => {
                        onConfigurePrompts(s.id);
                        setOpen(false);
                      }}
                      className="rounded-xs p-xs text-mute hover:bg-hover hover:text-accent-ink focus-visible:text-accent-ink"
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
                      className="rounded-xs p-xs text-mute hover:bg-hover hover:text-accent-ink focus-visible:text-accent-ink"
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
                      className="rounded-xs p-xs text-mute hover:bg-hover hover:text-accent-ink focus-visible:text-accent-ink"
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
                      className="rounded-xs p-xs text-mute hover:bg-hover hover:text-danger-ink focus-visible:text-danger-ink"
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
          <div className="my-xs border-t border-hair" />
          <button
            type="button"
            onClick={() => {
              onCreate();
              setOpen(false);
            }}
            className="flex w-full items-center gap-sm rounded-xs px-md py-sm text-left hover:bg-hover"
          >
            <span aria-hidden className="w-3 flex-none text-center text-body-sm text-gold-ink">
              ＋
            </span>
            <span className="font-display text-body-sm font-semibold text-ink">
              New Storyline
            </span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
