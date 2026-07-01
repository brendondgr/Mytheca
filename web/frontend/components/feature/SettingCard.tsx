import type { CSSProperties } from "react";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { IconButton } from "@/components/ui/IconButton";
import { mediaUrl } from "@/lib/api";
import { CARD_SCRIM, OVER_ART } from "@/lib/cardArt";
import { cn } from "@/lib/cn";
import type { Setting } from "@/lib/types";

const PLATE_STRIPES =
  "repeating-linear-gradient(45deg,var(--hair),var(--hair) 7px,var(--card-bd) 7px,var(--card-bd) 14px)";

/**
 * Setting card. When the setting has an establishing image it fills the whole
 * card behind a left-dark→right-bright gradient "filter" (name / type /
 * description on the dark left, art reading on the right); otherwise it falls
 * back to the striped "setting plate" over a solid, theme-aware body. The
 * selected scenario's setting is brought forward with an animated glow in the
 * theme accent color (its existing outline color).
 */
export function SettingCard({
  setting,
  onEdit,
  active = false,
}: {
  setting: Setting;
  onEdit?: () => void;
  /** Brought forward when this is the selected scenario's setting. */
  active?: boolean;
}) {
  const s = setting;
  const hasImage = !!s.image;
  return (
    <div
      aria-current={active ? "true" : undefined}
      className={cn(
        "velora-card relative overflow-hidden rounded-[3px] border hover:-translate-y-[2px] hover:shadow-[0_7px_18px_rgba(20,14,6,.18)]",
        hasImage && "min-h-[118px]",
        active ? "-translate-y-[2px] border-2 border-accent velora-glow" : "border-cardbd",
        !hasImage && (active ? "bg-card2" : "bg-card"),
      )}
      style={active ? ({ "--glow-color": "var(--accent)" } as CSSProperties) : undefined}
    >
      {hasImage ? (
        <>
          {/* eslint-disable-next-line @next/next/no-img-element -- generated scene art from our media mount */}
          <img
            src={mediaUrl(s.image!)}
            alt={`Establishing image of ${s.name}`}
            className="pointer-events-none absolute inset-0 h-full w-full object-cover"
          />
          <div
            className="pointer-events-none absolute inset-0"
            style={{ background: CARD_SCRIM }}
          />
        </>
      ) : (
        <div
          className="flex h-[72px] items-center justify-center"
          style={{ backgroundImage: PLATE_STRIPES }}
          aria-hidden
        >
          <span className="rounded-[2px] bg-card px-[9px] py-[3px] font-mono text-tag tracking-[0.1em] text-mute">
            setting plate
          </span>
        </div>
      )}

      {onEdit ? (
        <IconButton
          label={`Edit ${s.name}`}
          onClick={onEdit}
          className="absolute right-[10px] top-[10px] z-[2]"
        >
          ✎
        </IconButton>
      ) : null}

      <div className={cn("relative z-[1]", hasImage ? "p-[14px_16px]" : "p-[13px_15px]")}>
        <div
          className={cn("pr-[28px] font-display text-[16px] font-semibold", !hasImage && "text-ink")}
          style={hasImage ? { color: OVER_ART.title } : undefined}
        >
          {s.name}
        </div>
        <Eyebrow tracking="0.12em" color={hasImage ? OVER_ART.eyebrow : "#A8762A"} className="mt-1 block">
          {s.type}
        </Eyebrow>
        {/* Active state isn't conveyed by the accent border alone — a labelled
            "in this scene" marker rides on the dark-left of the scrim. */}
        {active ? (
          <span
            className={cn(
              "mt-[4px] block font-mono text-[8.5px] uppercase tracking-[0.12em]",
              !hasImage && "text-accent",
            )}
            style={hasImage ? { color: OVER_ART.accent } : undefined}
          >
            ◆ In this scene
          </span>
        ) : null}
        <p
          className={cn(
            "mt-[7px] font-body text-body-sm leading-[1.4]",
            hasImage ? "max-w-[58%] line-clamp-2" : "text-ink-soft",
          )}
          style={hasImage ? { color: OVER_ART.body } : undefined}
        >
          {s.desc}
        </p>
      </div>
    </div>
  );
}
