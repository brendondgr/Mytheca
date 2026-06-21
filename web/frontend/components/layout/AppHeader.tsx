import { ThemeSwitcher } from "@/components/layout/ThemeSwitcher";

function SearchIcon() {
  return (
    <svg
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden
      className="pointer-events-none absolute left-[10px] top-1/2 -translate-y-1/2 text-[#A8762A]"
    >
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.5" y2="16.5" />
    </svg>
  );
}

/**
 * Top app bar: ❖ VELORA wordmark, the (static) storyline affordance, the theme
 * switcher, library search, and a slot for the Create control (filled in Phase 5).
 */
export function AppHeader({
  query,
  onQuery,
  storylineName = "Embergate",
  createSlot,
}: {
  query: string;
  onQuery: (value: string) => void;
  storylineName?: string;
  createSlot?: React.ReactNode;
}) {
  return (
    <header className="velora-header flex h-[52px] flex-none items-center justify-between gap-3 border-b border-hair-strong px-[16px] sm:px-[26px]">
      <div className="flex items-center gap-[13px]">
        <span aria-hidden className="text-[16px] text-accent">
          ❖
        </span>
        <span className="font-display text-[20px] font-bold leading-none tracking-[0.2em] text-ink">
          VELORA
        </span>
        <span className="hidden h-5 w-px bg-hair-strong md:block" aria-hidden />
        <span className="hidden items-center gap-[6px] font-mono text-[10px] uppercase tracking-[0.14em] text-mute md:flex">
          <span className="text-[#A8762A]">◆</span> {storylineName}{" "}
          <span className="text-[8px]">▾</span>
        </span>
      </div>
      <div className="flex items-center gap-3">
        <ThemeSwitcher />
        <div className="relative hidden items-center sm:flex">
          <SearchIcon />
          <input
            type="search"
            aria-label="Search the library"
            value={query}
            onChange={(event) => onQuery(event.target.value)}
            placeholder="Search the library…"
            className="w-[210px] rounded-[2px] border border-field-bd bg-field py-[6px] pr-[11px] pl-[28px] font-body text-[13.5px] text-ink focus:border-accent focus:outline-none"
          />
        </div>
        {createSlot}
      </div>
    </header>
  );
}
