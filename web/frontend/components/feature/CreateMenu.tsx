"use client";

import { useEffect, useRef } from "react";
import type { EntityType } from "@/features/library/editor";

const ITEMS: { type: EntityType; icon: string; label: string; sub: string }[] = [
  { type: "character", icon: "❖", label: "Forge a Character", sub: "add to the cast" },
  { type: "setting", icon: "◆", label: "Add a Setting", sub: "a place to meet" },
  { type: "scenario", icon: "❖", label: "Assemble a Scenario", sub: "cast + setting + goal" },
];

/** The "+ Create" button + popover. Closes on outside-click and Escape. */
export function CreateMenu({
  open,
  onToggle,
  onClose,
  onCreate,
}: {
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  onCreate: (type: EntityType) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDocMouseDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onDocMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, onClose]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={onToggle}
        aria-haspopup="true"
        aria-expanded={open}
        aria-controls="create-menu"
        className="rounded-[2px] bg-accent px-[15px] py-[8px] font-mono text-[10.5px] uppercase tracking-[0.1em] text-[#F6ECDA] hover:brightness-110"
      >
        + Create ▾
      </button>
      {open ? (
        <div
          id="create-menu"
          aria-label="Create new"
          className="absolute top-[42px] right-0 z-40 w-[236px] rounded-[4px] border border-[#4A3826] bg-[#241B12] p-[7px] shadow-[0_16px_40px_rgba(20,12,4,.5)]"
        >
          <div className="px-[11px] pt-[5px] pb-[8px] font-mono text-[8.5px] uppercase tracking-[0.18em] text-[#7A6242]">
            New in Embergate
          </div>
          {ITEMS.map((item) => (
            <button
              key={item.type}
              type="button"
              onClick={() => onCreate(item.type)}
              className="flex w-full items-center gap-[11px] rounded-[3px] px-[11px] py-[9px] text-left hover:bg-[#34271A]"
            >
              <span className="w-4 text-center text-[14px] text-gold" aria-hidden>
                {item.icon}
              </span>
              <span className="flex flex-col gap-[2px]">
                <span className="font-display text-[14px] font-semibold text-[#F1E4CB]">
                  {item.label}
                </span>
                <span className="font-mono text-[8.5px] tracking-[0.04em] text-[#9A7E52]">
                  {item.sub}
                </span>
              </span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
