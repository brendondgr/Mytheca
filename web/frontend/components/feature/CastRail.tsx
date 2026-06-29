import { Monogram } from "@/components/ui/Monogram";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { mediaUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { Character } from "@/lib/types";

export function TurnOrder({
  order,
  charById,
}: {
  order: string[];
  charById: (id: string) => Character | undefined;
}) {
  return (
    <div className="mt-[22px]">
      <Eyebrow tracking="0.16em" className="mb-[10px] block">
        Turn order
      </Eyebrow>
      <div className="flex flex-wrap gap-[5px]">
        {order.map((x, i) => {
          const isYou = x === "You";
          const c = isYou ? undefined : charById(x);
          const mono = isYou ? "YOU" : (c?.mono ?? "?");
          const color = isYou ? "#C8543E" : (c?.color ?? "#5A534A");
          const active = i === 0;
          return (
            <span
              key={`${x}-${i}`}
              className="rounded-[12px] border px-[9px] py-1 font-mono text-[9px] font-medium tracking-[0.04em]"
              style={{
                borderColor: color,
                color: active ? "#F6ECDA" : color,
                background: active ? color : "var(--card-bg)",
              }}
            >
              {mono}
            </span>
          );
        })}
      </div>
    </div>
  );
}

/** Left rail: cast "at the table" (with a speaking marker) + turn order. */
export function CastRail({
  cast,
  speakingId,
  turnOrder,
  charById,
  onProfile,
}: {
  cast: Character[];
  speakingId: string | null;
  turnOrder: string[];
  charById: (id: string) => Character | undefined;
  onProfile: (id: string) => void;
}) {
  return (
    <aside className="velora-rail hidden w-[236px] flex-none overflow-auto border-r border-hair-strong p-[18px_16px] lg:block">
      <Eyebrow tracking="0.16em" className="mb-3 block">
        In the Scene
      </Eyebrow>
      <div className="flex flex-col gap-[7px]">
        {cast.map((c) => {
          const speaking = c.id === speakingId;
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => onProfile(c.id)}
              title="View profile"
              className={cn(
                "velora-row flex items-center gap-[10px] rounded-[3px] border p-[8px_10px] text-left hover:translate-x-[2px]",
                speaking ? "border-accent bg-card2" : "border-cardbd bg-card",
              )}
            >
              <Monogram mono={c.mono} color={c.color} src={c.portrait ? mediaUrl(c.portrait) : undefined} size={34} fontSize={13} />
              <span className="min-w-0 flex-1">
                <span className="block font-display text-[14px] font-semibold leading-[1.05] text-ink">
                  {c.name}
                </span>
                <Eyebrow size={8} tracking="0.08em" color={c.color} className="mt-[3px] block">
                  {c.role}
                </Eyebrow>
              </span>
              {speaking ? (
                <span className="flex-none font-mono text-[7.5px] tracking-[0.1em] text-success uppercase">
                  • now
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      <TurnOrder order={turnOrder} charById={charById} />
    </aside>
  );
}
