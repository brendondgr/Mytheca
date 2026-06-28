"use client";

import { useEffect, useRef } from "react";
import { SettingCard } from "@/components/feature/SettingCard";
import { ColumnEmpty, ColumnHeader } from "@/components/feature/ColumnChrome";
import type { Setting } from "@/lib/types";
import { cn } from "@/lib/cn";

/**
 * Settings column — one setting per row. The selected scenario's setting is
 * brought forward via the card's `active` state, and scrolled into view within
 * the column whenever the active setting changes (i.e. a new scenario is
 * selected) so a setting further down the list comes to the user.
 */
export function SettingColumn({
  settings,
  activeId,
  query,
  onEdit,
  onAdd,
  padX,
}: {
  settings: Setting[];
  activeId: string;
  query: string;
  onEdit: (id: string) => void;
  onAdd?: () => void;
  padX?: string;
}) {
  const activeRef = useRef<HTMLDivElement>(null);

  // When a new scenario is selected the active setting changes; reveal it inside
  // the column with a smooth scroll so it glides to the user rather than jumping.
  // Honors prefers-reduced-motion (falls back to instant). scroll-mt on the
  // active wrapper clears the sticky header.
  useEffect(() => {
    const el = activeRef.current;
    if (!el || !activeId) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView?.({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
  }, [activeId]);

  return (
    <div>
      <ColumnHeader title="Settings" count={settings.length} hint="The places of this world." onAdd={onAdd} addLabel="Add setting" className={padX} />
      <div className={cn(padX)}>
        {settings.length === 0 ? (
          <ColumnEmpty query={query} noun="settings" />
        ) : (
          <div className="flex flex-col gap-[14px]">
            {settings.map((s) => {
              const isActive = s.id === activeId;
              return (
                <div
                  key={s.id}
                  ref={isActive ? activeRef : undefined}
                  className={isActive ? "scroll-mt-[68px]" : undefined}
                >
                  <SettingCard
                    setting={s}
                    active={isActive}
                    onEdit={() => onEdit(s.id)}
                  />
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
