import { SkeletonBlock, SkeletonLine } from "@/components/ui/Skeleton";

/**
 * Placeholders for the Library's three columns.
 *
 * These are **tracings**, not grey boxes: each mirrors the card it stands in
 * for — same grid, same gaps, same radii, same heights (a scenario card is
 * `min-h-[176px]`, a setting card `min-h-[118px]`, a character tile `2/3`).
 * A skeleton whose shape disagrees with the real content breaks the user's
 * model of the page the instant the content lands, which costs more trust than
 * the placeholder ever bought.
 *
 * The counts are deliberately modest (3 / 6 / 3). A placeholder is a promise
 * about layout, not about quantity, and over-promising rows is the same
 * mistake in the other direction.
 */

/* Note these placeholders do NOT carry `.reveal`. A scroll-driven entrance on
 * a shimmer would animate a thing that is already animating, and the columns
 * are short enough that most placeholders are on screen at once anyway. */

/** One scenario row — image band, title, eyebrow, goal line, cast footer. */
function ScenarioCardSkeleton() {
  return (
    <div className="min-h-[176px] rounded-[4px] border border-cardbd bg-card p-[14px]">
      <SkeletonLine width="38%" height="9px" />
      <SkeletonLine width="70%" height="18px" className="mt-[10px]" />
      <SkeletonLine width="92%" height="12px" className="mt-[12px]" />
      <SkeletonLine width="64%" height="12px" className="mt-[6px]" />
      <SkeletonLine width="46%" height="10px" className="mt-[26px]" />
    </div>
  );
}

/** One 2:3 character tile — the portrait frame with its name/role footer. */
function CharacterTileSkeleton() {
  return (
    <div className="relative aspect-[2/3] overflow-hidden rounded-[4px] border border-cardbd bg-card">
      <SkeletonBlock className="absolute inset-0 h-full w-full rounded-none" />
      <div className="absolute inset-x-[10px] bottom-[10px]">
        <SkeletonLine width="72%" height="13px" />
        <SkeletonLine width="48%" height="9px" className="mt-[6px]" />
      </div>
    </div>
  );
}

/** One setting row — plate band, name, type eyebrow, description. */
function SettingCardSkeleton() {
  return (
    <div className="min-h-[118px] rounded-[4px] border border-cardbd bg-card p-[14px]">
      <SkeletonLine width="30%" height="9px" />
      <SkeletonLine width="62%" height="16px" className="mt-[10px]" />
      <SkeletonLine width="88%" height="12px" className="mt-[12px]" />
      <SkeletonLine width="55%" height="12px" className="mt-[6px]" />
    </div>
  );
}

export function ScenarioColumnSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-[14px]">
      {Array.from({ length: rows }, (_, i) => (
        <ScenarioCardSkeleton key={i} />
      ))}
    </div>
  );
}

export function CharacterColumnSkeleton({ tiles = 6 }: { tiles?: number }) {
  // The same container-driven 2-up / 3-up grid the real column uses. If this
  // used the viewport while the real grid asks its container, the tiles would
  // visibly re-flow the instant the real cast landed — which is precisely the
  // broken-trust moment a skeleton exists to avoid.
  return (
    <div className="grid grid-cols-2 gap-[12px] @[420px]:grid-cols-3">
      {Array.from({ length: tiles }, (_, i) => (
        <CharacterTileSkeleton key={i} />
      ))}
    </div>
  );
}

export function SettingColumnSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-[14px]">
      {Array.from({ length: rows }, (_, i) => (
        <SettingCardSkeleton key={i} />
      ))}
    </div>
  );
}
