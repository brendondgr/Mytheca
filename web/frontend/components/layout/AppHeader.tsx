import { HeaderBar, HeaderLead, HeaderTrail } from "@/components/layout/HeaderBar";
import { Icon } from "@/components/ui/Icon";

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
        {/* The wordmark folds below `sm`, the brandmark does not.
         *
         * At 390px it rendered 51->176px inside a 116px-wide lead: it overflowed
         * its OWN container by 44px and sat under the Create button. Nothing
         * extended past the viewport edge, so no overflow check saw it — an
         * overlap is invisible to a `scrollWidth` gate and obvious to a person.
         *
         * Truncating it was the other option and reads worse than hiding it:
         * "MYTH…" is not a brand. The name is not lost — the brandmark carries
         * it, `sr-only` keeps it in the accessibility tree, and the document
         * title says it too. */}
        <span className="sr-only">Mytheca</span>
        <span
          aria-hidden
          className="hidden truncate font-display text-step-1 leading-none font-bold tracking-[0.2em] text-ink sm:block"
        >
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
          <Icon
            name="search"
            size={13}
            className="pointer-events-none absolute top-1/2 left-md -translate-y-1/2 text-gold-soft-ink"
          />
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
