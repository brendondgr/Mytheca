"use client";

import { useEffect, useRef, useState } from "react";

export type ExportFormat = "json" | "md";

const ITEMS: { format: ExportFormat; label: string; sub: string }[] = [
  { format: "md", label: "Conversation (Markdown)", sub: "readable transcript + diagnostics" },
  { format: "json", label: "Conversation (JSON)", sub: "structured record for debugging" },
];

/**
 * Header "Export" control: downloads the full conversation record (turn-by-turn flow,
 * character thoughts, and the knowledge-graph + RAG activity) as Markdown or JSON.
 * A menu button (popover closes on outside-click / Escape). Disabled until the scene has
 * a saved session — nothing to export before the first turn.
 */
export function ExportMenu({
  onExport,
  disabled = false,
}: {
  onExport: (format: ExportFormat) => void;
  disabled?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

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
        onClick={() => setOpen((o) => !o)}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="export-menu"
        title="Export the full conversation — flow, thoughts, graph + RAG activity"
        className="flex flex-none items-center gap-[6px] rounded-[2px] border border-field-bd px-[10px] py-[6px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent aria-expanded:border-accent aria-expanded:text-accent disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-field-bd disabled:hover:text-mute"
      >
        <span aria-hidden>⭳</span> Export
      </button>
      {open ? (
        <div
          id="export-menu"
          role="menu"
          aria-label="Export conversation"
          className="absolute top-[38px] right-0 z-40 w-[240px] velora-menu p-[7px]"
        >
          {ITEMS.map((item) => (
            <button
              key={item.format}
              type="button"
              role="menuitem"
              onClick={() => {
                onExport(item.format);
                setOpen(false);
              }}
              className="flex w-full flex-col gap-[2px] rounded-[3px] px-[11px] py-[9px] text-left hover:bg-hover"
            >
              <span className="font-display text-[13px] font-semibold text-ink">{item.label}</span>
              <span className="font-mono text-tag tracking-[0.04em] text-mute">{item.sub}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
