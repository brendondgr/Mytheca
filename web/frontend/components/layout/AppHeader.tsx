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
 * Top app bar: ❖ VELORA wordmark, the storyline switcher slot, library search,
 * and slots for the Create and Options controls. (Theme switching now lives in
 * the Options dropdown / the Options page Appearance tab.)
 */
export function AppHeader({
  query,
  onQuery,
  storylineSlot,
  createSlot,
  optionsSlot,
}: {
  query: string;
  onQuery: (value: string) => void;
  storylineSlot?: React.ReactNode;
  createSlot?: React.ReactNode;
  optionsSlot?: React.ReactNode;
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
        {storylineSlot ? (
          <>
            <span
              className="hidden h-5 w-px bg-hair-strong md:block"
              aria-hidden
            />
            <span className="hidden md:block">{storylineSlot}</span>
          </>
        ) : null}
      </div>
      <div className="flex items-center gap-3">
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
        {optionsSlot}
      </div>
    </header>
  );
}
