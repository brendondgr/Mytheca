"use client";

import { useRef } from "react";
import { cn } from "@/lib/cn";

export interface TabItem {
  key: string;
  label: string;
  count: number;
}

/** ARIA tablist with roving tabindex + arrow/Home/End keyboard navigation. */
export function LibraryTabs({
  tabs,
  active,
  onChange,
  idBase = "lib",
}: {
  tabs: TabItem[];
  active: string;
  onChange: (key: string) => void;
  idBase?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(event: React.KeyboardEvent, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft")
      next = (index - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    onChange(tabs[next].key);
    refs.current[next]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label="Library sections"
      className="flex items-center gap-1 overflow-x-auto border-b border-hair-strong px-[28px]"
    >
      {tabs.map((tab, index) => {
        const selected = tab.key === active;
        return (
          <button
            key={tab.key}
            ref={(el) => {
              refs.current[index] = el;
            }}
            role="tab"
            id={`${idBase}-tab-${tab.key}`}
            aria-selected={selected}
            aria-controls={`${idBase}-panel-${tab.key}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.key)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={cn(
              "flex cursor-pointer items-center gap-2 px-[18px] pt-[10px] pb-[13px] font-display text-[16px] font-semibold whitespace-nowrap",
              selected
                ? "border-b-2 border-accent text-ink"
                : "border-b-2 border-transparent text-tab-ink",
            )}
          >
            {tab.label}
            <span className="font-mono text-[11px] font-normal text-[#A38E63]">
              {tab.count}
            </span>
          </button>
        );
      })}
    </div>
  );
}
