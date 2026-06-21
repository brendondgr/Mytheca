import { IconButton } from "@/components/ui/IconButton";
import type { Branch } from "@/lib/types";

/** A storyline branch row: ◆ approach + outcome, with the check + event tag. */
export function BranchRow({
  branch,
  showEventTag = true,
  onEdit,
  onDelete,
}: {
  branch: Branch;
  showEventTag?: boolean;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  const b = branch;
  return (
    <div className="velora-row flex items-start gap-[15px] rounded-[3px] border border-cardbd bg-card p-[14px_16px] hover:translate-x-[4px]">
      <span aria-hidden className="mt-1 flex-none text-[13px] text-accent">
        ◆
      </span>
      <div className="min-w-0 flex-1">
        <div className="font-display text-[16px] text-ink">{b.label}</div>
        <div className="mt-1 font-body text-[14px] text-ink-soft">{b.outcome}</div>
      </div>
      <div className="flex flex-none flex-col items-end gap-[5px] text-right">
        {/* check + tag keep their original case, so plain mono (not Eyebrow). */}
        <span className="font-mono text-[11px] text-accent">{b.check}</span>
        {showEventTag ? (
          <span className="font-mono text-[9px] tracking-[0.06em] text-[#9A8A68]">
            {b.tag}
          </span>
        ) : null}
      </div>
      {onEdit || onDelete ? (
        <div className="flex flex-none flex-col gap-[5px]">
          {onEdit ? (
            <IconButton label="Edit branch" size={22} onClick={onEdit}>
              ✎
            </IconButton>
          ) : null}
          {onDelete ? (
            <IconButton label="Delete branch" size={22} onClick={onDelete}>
              ×
            </IconButton>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
