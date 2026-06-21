import { Eyebrow } from "@/components/ui/Eyebrow";
import { IconButton } from "@/components/ui/IconButton";
import type { Setting } from "@/lib/types";

const PLATE_STRIPES =
  "repeating-linear-gradient(45deg,#DACBA6,#DACBA6 7px,#D0C09B 7px,#D0C09B 14px)";

/** Setting card: a "setting plate" header over name / type / description. */
export function SettingCard({
  setting,
  onEdit,
}: {
  setting: Setting;
  onEdit?: () => void;
}) {
  const s = setting;
  return (
    <div className="velora-card relative overflow-hidden rounded-[3px] border border-cardbd bg-card hover:-translate-y-[2px] hover:shadow-[0_7px_18px_rgba(20,14,6,.18)]">
      {onEdit ? (
        <IconButton
          label={`Edit ${s.name}`}
          onClick={onEdit}
          className="absolute right-[10px] top-[10px] z-[2]"
        >
          ✎
        </IconButton>
      ) : null}
      <div
        className="flex h-[72px] items-center justify-center"
        style={{ backgroundImage: PLATE_STRIPES }}
        aria-hidden
      >
        <span className="rounded-[2px] bg-[#F4ECDA] px-[9px] py-[3px] font-mono text-[9.5px] tracking-[0.1em] text-[#7A6A4A]">
          setting plate
        </span>
      </div>
      <div className="p-[13px_15px]">
        <div className="font-display text-[16px] font-semibold text-ink">{s.name}</div>
        <Eyebrow size={9} tracking="0.12em" color="#A8762A" className="mt-1 block">
          {s.type}
        </Eyebrow>
        <p className="mt-[7px] font-body text-[14px] leading-[1.4] text-ink-soft">
          {s.desc}
        </p>
      </div>
    </div>
  );
}
