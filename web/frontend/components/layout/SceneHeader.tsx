import Link from "next/link";
import { ThemeSwitcher } from "@/components/layout/ThemeSwitcher";

/** Story-player header: back to the Library, scene title/setting, theme, status. */
export function SceneHeader({
  title,
  settingName,
  backHref = "/",
}: {
  title: string;
  settingName: string;
  backHref?: string;
}) {
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
            ◆ {settingName} · live scene
          </div>
        </div>
      </div>
      <div className="flex flex-none items-center gap-[14px]">
        <ThemeSwitcher />
        <div className="hidden items-center gap-2 font-mono text-[9px] tracking-[0.12em] text-mute uppercase sm:flex">
          <span className="h-[7px] w-[7px] rounded-full bg-success" aria-hidden /> Narrator
          active
        </div>
      </div>
    </header>
  );
}
