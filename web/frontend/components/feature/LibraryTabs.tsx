"use client";

import { useRef, type ReactNode } from "react";
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
  action,
}: {
  tabs: TabItem[];
  active: string;
  onChange: (key: string) => void;
  idBase?: string;
  /**
   * One control at the end of the bar — in practice, "add one of these".
   *
   * It lives here below `lg` because the column header that used to carry it is hidden
   * there: the header said "SCENARIOS 3" directly under a tab that already says
   * "Scenarios 3", which is the duplication this slot exists to remove without also
   * removing the only way to create something on a phone. Outside the tablist's
   * `role="tablist"` children, so it is not announced as a tab.
   */
  action?: ReactNode;
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
    <div className="flex items-stretch border-b border-hair-strong">
    <div
      role="tablist"
      aria-label="Library sections"
      // `.scroll-fade` draws an edge gradient that clears at each end of the
      // track, so a clipped tab reads as "there is more this way" rather than
      // as the end of the list. It is driven by animation-timeline: scroll(),
      // so there is no scroll listener behind it.
      className="scroll-fade flex min-w-0 flex-1 items-center gap-1 overflow-x-auto px-lg sm:px-xl"
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
              "flex cursor-pointer items-center gap-2 px-lg pt-sm pb-md font-display text-body font-semibold whitespace-nowrap",
              selected
                ? "border-b-2 border-accent text-ink"
                : "border-b-2 border-transparent text-tab-ink",
            )}
          >
            {tab.label}
            <span className="font-mono text-eyebrow font-normal text-[#A38E63]">
              {tab.count}
            </span>
          </button>
        );
      })}
    </div>
      {action ? (
        <div className="flex flex-none items-center pr-lg pb-md sm:pr-xl">{action}</div>
      ) : null}
    </div>
  );
}
