"use client";

import { cn } from "@/lib/cn";

/**
 * One button in the rail bar: what it says, how many things are behind it, and whether the
 * surface it owns is open right now.
 */
export interface RailTrigger {
  key: string;
  label: string;
  /**
   * A number worth advertising — the present-cast count, the outcomes a direction still owes.
   * `null` or `0` shows nothing. It is folded into the button's accessible name rather than
   * left as a bare numeral, because "Scene 2" tells a screen-reader user nothing.
   */
  count?: number | null;
  /** How the count reads aloud, e.g. `"2 still owed"`. Required whenever `count` is shown. */
  countLabel?: (n: number) => string;
  /** Draw attention: an amber dot on the count. For things the scene owes, not for totals. */
  urgent?: boolean;
  open: boolean;
  onSelect: () => void;
  /**
   * Whether this opens a modal dialog. `false` for a control that discloses a panel in the
   * layout (the scene-knowledge rail) — `aria-haspopup="dialog"` there would promise a modal
   * that never arrives, and `aria-expanded` alone is the right contract for a disclosure.
   */
  dialog?: boolean;
}

/**
 * The `lg:hidden` row of rail triggers, sitting directly above the composer.
 *
 * Above the composer rather than in the header on purpose: it is one thumb-reachable tap at
 * the bottom of the screen, and it leaves the header free for the overflow menu. Everything
 * these open is a rail that simply does not exist below `lg` today — the cast list with its
 * presence controls and stat values, the scene pulse, the scene state, the direction
 * checklist — so this row is the only way those reach a phone at all.
 */
export function SceneRailBar({
  triggers,
  className,
}: {
  triggers: RailTrigger[];
  className?: string;
}) {
  if (triggers.length === 0) return null;
  return (
    <div
      className={cn(
        "flex flex-none items-stretch gap-[6px] border-t border-hair-strong bg-page px-[12px] pt-[7px] lg:hidden",
        className,
      )}
    >
      {triggers.map((t) => {
        const n = t.count ?? 0;
        const showCount = n > 0;
        return (
          <button
            key={t.key}
            type="button"
            aria-haspopup={t.dialog === false ? undefined : "dialog"}
            aria-expanded={t.open}
            // The count belongs in the name, not beside it: a trailing numeral read on its own
            // is noise, and the badge is the only place this information exists on a phone.
            aria-label={
              showCount && t.countLabel ? `${t.label}, ${t.countLabel(n)}` : t.label
            }
            onClick={t.onSelect}
            className={cn(
              "touch-target press flex min-h-[36px] flex-1 items-center justify-center gap-[6px] rounded-[5px] border font-mono text-[10px] tracking-[0.12em] uppercase transition-colors duration-fast",
              t.open
                ? "border-accent bg-card2 text-ink"
                : "border-field-bd bg-card text-mute hover:bg-hover hover:text-ink",
            )}
          >
            <span>{t.label}</span>
            {showCount ? (
              <span
                aria-hidden
                className={cn(
                  "flex min-w-[17px] items-center justify-center rounded-[9px] px-[5px] py-[1px] text-[9px] leading-[1.4]",
                  // Filled accent with the light ink the design system pairs with it
                  // (`accent-ink / accent`, already in the contrast gate) — accent *as text*
                  // at 9px on a card ground would not clear AA.
                  t.urgent
                    ? "bg-accent text-[#F6ECDA]"
                    : "border border-cardbd bg-card2 text-ink-soft",
                )}
              >
                {n}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
