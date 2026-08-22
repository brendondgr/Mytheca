"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { SessionSummary } from "@/lib/events";

/** How a play-through labels itself: its name, else its first line, else a placeholder. */
export function playthroughLabel(session: SessionSummary): string {
  return session.name?.trim() || session.preview.trim() || "Untitled play-through";
}

/** "3 minutes ago" — coarse on purpose; a play-through's age is context, not data. */
export function relativeTime(iso: string, now: number = Date.now()): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const seconds = Math.max(0, Math.round((now - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days}d ago`;
}

type RowMode = "idle" | "renaming" | "confirming-delete";

/**
 * The scene header's play-through tray: every saved story for this scenario, and the
 * actions over them.
 *
 * This is the surface that ends "one play-through per scenario". The list endpoint always
 * returned every session; the story player read `sessions[0]` and discarded the rest, so
 * replaying a scenario differently meant destroying the first attempt. Later phases report
 * into this same list — a branch appears here, and so does the snapshot a rewind keeps.
 *
 * Rename and delete confirm **inside the row** rather than opening a modal, so the tray
 * stays one focus context: opening a dialog over a popover means two nested traps and an
 * Escape key that has to decide which one it means.
 */
export function PlaythroughTray({
  sessions,
  currentSessionId,
  onOpen,
  onCreate,
  onRename,
  onDelete,
  disabled = false,
}: {
  sessions: SessionSummary[];
  /** The play-through currently on screen (`null` before the first turn of a fresh scene). */
  currentSessionId: string | null;
  onOpen: (sessionId: string) => void;
  onCreate: () => void;
  onRename: (sessionId: string, name: string) => void;
  onDelete: (sessionId: string) => void;
  /** True while a turn is streaming — switching stories mid-sentence is not a thing. */
  disabled?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [rowMode, setRowMode] = useState<Record<string, RowMode>>({});
  const [draftName, setDraftName] = useState("");

  /**
   * Close the tray, abandoning any half-finished rename or delete confirmation so reopening
   * never presents a row mid-edit with a stale draft in it.
   *
   * The reset happens HERE, on the action, rather than in an effect watching `open`. Doing
   * it in an effect means a synchronous setState during commit, which cascades an extra
   * render pass for every close.
   */
  const closeTray = useCallback(() => {
    setOpen(false);
    setRowMode({});
    setDraftName("");
  }, []);

  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) closeTray();
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") closeTray();
    }
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, closeTray]);

  const modeOf = (id: string): RowMode => rowMode[id] ?? "idle";
  const setMode = (id: string, mode: RowMode) =>
    setRowMode((m) => ({ ...m, [id]: mode }));

  const count = sessions.length;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => (open ? closeTray() : setOpen(true))}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="playthrough-tray"
        title="Play-throughs — switch between saved stories, or start a new one"
        className="flex flex-none items-center gap-[6px] rounded-[2px] border border-field-bd px-[10px] py-[6px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent aria-expanded:border-accent aria-expanded:text-accent disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-field-bd disabled:hover:text-mute"
      >
        <span aria-hidden>❑</span>
        <span className="hidden sm:inline">Play-throughs</span>
        {count > 1 ? <span className="tabular-nums">{count}</span> : null}
      </button>

      {open ? (
        <div
          id="playthrough-tray"
          role="menu"
          aria-label="Play-throughs"
          className="absolute top-[38px] left-0 z-40 flex w-[300px] max-w-[calc(100vw-24px)] flex-col mytheca-menu p-[7px]"
        >
          {count === 0 ? (
            <p className="px-[11px] py-[10px] font-body text-[13px] text-mute">
              This scene has not been played yet. Your first message starts a play-through.
            </p>
          ) : (
            <ul className="flex max-h-[320px] flex-col overflow-auto">
              {sessions.map((session) => {
                const mode = modeOf(session.id);
                const isCurrent = session.id === currentSessionId;
                return (
                  <li key={session.id} className="border-b border-hair last:border-b-0">
                    {mode === "renaming" ? (
                      <form
                        className="flex items-center gap-[6px] px-[9px] py-[8px]"
                        onSubmit={(e) => {
                          e.preventDefault();
                          onRename(session.id, draftName);
                          setMode(session.id, "idle");
                        }}
                      >
                        <input
                          autoFocus
                          value={draftName}
                          onChange={(e) => setDraftName(e.target.value)}
                          aria-label={`Rename ${playthroughLabel(session)}`}
                          placeholder="Name this play-through"
                          className="min-w-0 flex-1 rounded-[3px] border border-field-bd bg-field px-[7px] py-[5px] font-body text-[13px] text-ink placeholder:text-mute2 focus:border-accent focus:outline-none"
                        />
                        <button
                          type="submit"
                          className="flex h-[26px] min-w-[26px] items-center justify-center rounded-[3px] px-[7px] font-mono text-[9px] tracking-[0.1em] text-accent uppercase hover:bg-hover"
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => setMode(session.id, "idle")}
                          className="flex h-[26px] min-w-[26px] items-center justify-center rounded-[3px] px-[7px] font-mono text-[9px] tracking-[0.1em] text-mute uppercase hover:bg-hover"
                        >
                          Cancel
                        </button>
                      </form>
                    ) : mode === "confirming-delete" ? (
                      <div className="flex items-center gap-[6px] px-[9px] py-[8px]">
                        <span className="min-w-0 flex-1 font-body text-[13px] text-ink">
                          Delete this play-through?
                        </span>
                        <button
                          type="button"
                          onClick={() => {
                            onDelete(session.id);
                            setMode(session.id, "idle");
                          }}
                          className="flex h-[26px] items-center rounded-[3px] bg-accent px-[9px] font-mono text-[9px] tracking-[0.1em] text-[#F6ECDA] uppercase hover:bg-accent-hover"
                        >
                          Delete
                        </button>
                        <button
                          type="button"
                          onClick={() => setMode(session.id, "idle")}
                          className="flex h-[26px] items-center rounded-[3px] px-[7px] font-mono text-[9px] tracking-[0.1em] text-mute uppercase hover:bg-hover"
                        >
                          Keep
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-[4px] px-[4px] py-[3px]">
                        <button
                          type="button"
                          role="menuitem"
                          onClick={() => {
                            if (!isCurrent) onOpen(session.id);
                            closeTray();
                          }}
                          aria-current={isCurrent ? "true" : undefined}
                          className="flex min-w-0 flex-1 flex-col gap-[2px] rounded-[3px] px-[7px] py-[7px] text-left hover:bg-hover"
                        >
                          <span className="flex items-center gap-[6px]">
                            {isCurrent ? (
                              <span
                                aria-hidden
                                className="h-[6px] w-[6px] flex-none rounded-full bg-accent"
                              />
                            ) : null}
                            <span className="truncate font-display text-[13px] font-semibold text-ink">
                              {playthroughLabel(session)}
                            </span>
                          </span>
                          <span className="font-mono text-tag tracking-[0.04em] text-mute">
                            {session.turnCount} {session.turnCount === 1 ? "turn" : "turns"} ·{" "}
                            {relativeTime(session.updatedAt)}
                            {isCurrent ? " · open" : ""}
                            {session.parentSessionId ? " · branched" : ""}
                          </span>
                        </button>
                        {/* 24x24 minimum target (WCAG 2.5.8). */}
                        <button
                          type="button"
                          onClick={() => {
                            setDraftName(session.name ?? "");
                            setMode(session.id, "renaming");
                          }}
                          aria-label={`Rename ${playthroughLabel(session)}`}
                          className="flex h-[24px] w-[24px] flex-none items-center justify-center rounded-[3px] text-[12px] text-mute hover:bg-hover hover:text-ink"
                        >
                          <span aria-hidden>✎</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setMode(session.id, "confirming-delete")}
                          aria-label={`Delete ${playthroughLabel(session)}`}
                          className="flex h-[24px] w-[24px] flex-none items-center justify-center rounded-[3px] text-[12px] text-mute hover:bg-hover hover:text-danger"
                        >
                          <span aria-hidden>×</span>
                        </button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onCreate();
              closeTray();
            }}
            className="mt-[4px] flex w-full items-center gap-[7px] rounded-[3px] border-t border-hair px-[11px] py-[9px] text-left hover:bg-hover"
          >
            <span aria-hidden className="font-mono text-[13px] text-accent">
              +
            </span>
            <span className="flex flex-col gap-[1px]">
              <span className="font-display text-[13px] font-semibold text-ink">
                New play-through
              </span>
              <span className="font-mono text-tag tracking-[0.04em] text-mute">
                start this scene again; the current one is kept
              </span>
            </span>
          </button>
        </div>
      ) : null}
    </div>
  );
}
