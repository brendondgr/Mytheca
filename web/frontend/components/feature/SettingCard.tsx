import { Eyebrow } from "@/components/ui/Eyebrow";
import { IconButton } from "@/components/ui/IconButton";
import { mediaUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Setting } from "@/lib/types";

const PLATE_STRIPES =
  "repeating-linear-gradient(45deg,var(--hair),var(--hair) 7px,var(--card-bd) 7px,var(--card-bd) 14px)";

/** Setting card: a "setting plate" header over name / type / description. */
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
  return (
    <div
      aria-current={active ? "true" : undefined}
      className={cn(
        "velora-card relative overflow-hidden rounded-[3px] border hover:-translate-y-[2px] hover:shadow-[0_7px_18px_rgba(20,14,6,.18)]",
        active
          ? "-translate-y-[2px] border-2 border-accent bg-card2 shadow-[0_6px_18px_rgba(142,43,28,.18)]"
          : "border-cardbd bg-card",
      )}
    >
      {onEdit ? (
        <IconButton
          label={`Edit ${s.name}`}
          onClick={onEdit}
          className="absolute right-[10px] top-[10px] z-[2]"
        >
          ✎
        </IconButton>
      ) : null}
      {s.image ? (
        // eslint-disable-next-line @next/next/no-img-element -- generated scene art from our media mount
        <img
          src={mediaUrl(s.image)}
          alt={`Establishing image of ${s.name}`}
          className="h-[96px] w-full object-cover"
        />
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
      <div className="p-[13px_15px]">
        <div className="flex items-baseline justify-between gap-[8px]">
          <div className="font-display text-[16px] font-semibold text-ink">
            {s.name}
          </div>
          {active ? (
            <span className="flex-none font-mono text-eyebrow uppercase tracking-[0.12em] text-accent">
              ◆ In this scene
            </span>
          ) : null}
        </div>
        <Eyebrow tracking="0.12em" color="#A8762A" className="mt-1 block">
          {s.type}
        </Eyebrow>
        <p className="mt-[7px] font-body text-body-sm leading-[1.4] text-ink-soft">
          {s.desc}
        </p>
      </div>
    </div>
  );
}
