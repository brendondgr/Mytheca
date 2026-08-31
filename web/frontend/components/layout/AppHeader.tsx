import { HeaderBar, HeaderLead, HeaderTrail } from "@/components/layout/HeaderBar";

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
      className="pointer-events-none absolute top-1/2 left-md -translate-y-1/2 text-gold-soft"
    >
      <circle cx="11" cy="11" r="7" />
      <line x1="21" y1="21" x2="16.5" y2="16.5" />
    </svg>
  );
}

/**
 * Top app bar: the Mytheca emblem + wordmark, the storyline switcher slot, library search,
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
    <HeaderBar elevated>
      <HeaderLead className="gap-md">
        <span
          aria-hidden
          className="mytheca-brandmark h-[30px] w-[27px] flex-none"
        />
        <span className="font-display text-step-1 leading-none font-bold tracking-[0.2em] text-ink">
          MYTHECA
        </span>
        {storylineSlot ? (
          <>
            {/* The divider is decoration and stays `md`-gated; the switcher itself does not.
                Hiding it below `md` made a phone a single-world device — deep links already
                worked, the control simply did not exist. */}
            <span
              className="hidden h-5 w-px bg-hair-strong md:block"
              aria-hidden
            />
            {storylineSlot}
          </>
        ) : null}
      </HeaderLead>
      <HeaderTrail>
        <div className="relative hidden items-center sm:flex">
          <SearchIcon />
          <input
            type="search"
            aria-label="Search the library"
            value={query}
            onChange={(event) => onQuery(event.target.value)}
            placeholder="Search the library…"
            className="w-[210px] rounded-xs border border-field-bd bg-field py-xs pr-md pl-2xl font-body text-field text-ink focus:border-accent focus:outline-none"
          />
        </div>
        {createSlot}
        {optionsSlot}
      </HeaderTrail>
    </HeaderBar>
  );
}
