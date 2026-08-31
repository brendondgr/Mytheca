"use client";

import { useEffect, useRef } from "react";
import type { EntityType } from "@/features/library/editor";
import { Icon } from "@/components/ui/Icon";

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
        aria-label="Create"
        // A plus, and nothing else, below `sm`. The popover it opens already asks what
        // to create — "+ Create ▾" spends 96px of a 390px bar saying what the plus and
        // the panel say between them.
        className="flex h-control w-control touch-target-overlay items-center justify-center gap-2xs rounded-xs bg-accent font-mono text-eyebrow uppercase tracking-[0.1em] text-on-accent hover-lift press hover:bg-accent-hover hover:shadow-[0_5px_14px_rgba(10,6,3,.3)] active:translate-y-0 sm:w-auto sm:px-lg"
      >
        <Icon name="plus" size={15} strokeWidth={2.2} />
        <span className="hidden sm:inline">Create</span>
      </button>
      {open ? (
        <div
          id="create-menu"
          aria-label="Create new"
          className="absolute top-3xl right-0 z-40 w-[236px] mytheca-menu p-xs"
        >
          <div className="px-md pt-2xs pb-sm font-mono text-tag uppercase tracking-[0.18em] text-mute">
            New in Embergate
          </div>
          {ITEMS.map((item) => (
            <button
              key={item.type}
              type="button"
              onClick={() => onCreate(item.type)}
              className="flex w-full items-center gap-md rounded-xs px-md py-sm text-left hover:bg-hover"
            >
              <span className="w-4 text-center text-body-sm text-gold-ink" aria-hidden>
                {item.icon}
              </span>
              <span className="flex flex-col gap-3xs">
                <span className="font-display text-body-sm font-semibold text-ink">
                  {item.label}
                </span>
                <span className="font-mono text-tag tracking-[0.04em] text-mute">
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
