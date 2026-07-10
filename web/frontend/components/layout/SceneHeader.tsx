import Link from "next/link";
import { ThemeSwitcher } from "@/components/layout/ThemeSwitcher";
import { ExportMenu, type ExportFormat } from "@/components/feature/ExportMenu";

/** Story-player header: back to the Library, scene title/setting, export, theme, status.
 * Scene Config now lives in the composer's bottom controls row (not the header). */
export function SceneHeader({
  title,
  settingName,
  genre,
  tone,
  backHref = "/",
  onExport,
  canExport = false,
  onToggleInspector,
  inspectorOpen = false,
}: {
  title: string;
  settingName: string;
  genre?: string;
  tone?: string;
  backHref?: string;
  /** Download the full conversation record (omit to hide the Export control). */
  onExport?: (format: ExportFormat) => void;
  /** Whether there is a saved session to export yet (disables the control until then). */
  canExport?: boolean;
  /** Toggle the Turn Inspector drawer (omit to hide the control). */
  onToggleInspector?: () => void;
  inspectorOpen?: boolean;
}) {
  const meta = [`◆ ${settingName}`, genre, tone].filter(Boolean).join(" · ");
  return (
    <header className="velora-header flex h-[50px] flex-none items-center justify-between gap-3 border-b border-hair-strong px-[24px]">
      <div className="flex min-w-0 items-center gap-[14px]">
        <Link
          href={backHref}
          className="flex flex-none items-center gap-[7px] rounded-[2px] border border-field-bd px-[11px] py-[6px] font-mono text-[10px] tracking-[0.1em] text-accent uppercase hover:bg-accent hover:text-[#F6ECDA]"
        >
          ‹ Library
        </Link>
        <span className="h-[22px] w-px flex-none bg-hair-strong" aria-hidden />
        <div className="min-w-0">
          <div className="truncate font-display text-[16px] font-bold leading-none text-ink">
            {title}
          </div>
          <div className="mt-1 truncate font-mono text-tag tracking-[0.14em] text-mute uppercase">
            {meta} · live scene
          </div>
        </div>
      </div>
      <div className="flex flex-none items-center gap-[14px]">
        {onExport ? <ExportMenu onExport={onExport} disabled={!canExport} /> : null}
        <ThemeSwitcher />
        <div className="hidden items-center gap-2 font-mono text-[9px] tracking-[0.12em] text-mute uppercase sm:flex">
          <span className="h-[7px] w-[7px] rounded-full bg-success" aria-hidden /> Narrator
          active
        </div>
        {onToggleInspector ? (
          <button
            type="button"
            onClick={onToggleInspector}
            aria-pressed={inspectorOpen}
            title="Turn Inspector — see how the scene responds to each message"
            className="flex flex-none items-center gap-[6px] rounded-[2px] border border-field-bd px-[10px] py-[6px] font-mono text-[9px] tracking-[0.12em] text-mute uppercase hover:border-accent hover:text-accent aria-pressed:border-accent aria-pressed:text-accent"
          >
            <span aria-hidden>⚙</span> Inspector
          </button>
        ) : null}
      </div>
    </header>
  );
}
