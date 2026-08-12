"use client";

import type { useLibraryState } from "@/features/library/useLibraryState";
import type { LibraryTabKey } from "@/features/library/useLibraryState";
import { LibraryTabs, type TabItem } from "@/components/feature/LibraryTabs";
import { ScenarioColumn } from "@/components/feature/ScenarioColumn";
import { CharacterColumn } from "@/components/feature/CharacterColumn";
import { SettingColumn } from "@/components/feature/SettingColumn";
import { useDelayedFlag } from "@/hooks/use-delayed-flag";
import { cn } from "@/lib/cn";

/** Wrap a column so it shows as one of three open columns on desktop, and as
 *  the single active section (via the mobile tab switcher) on narrow screens. */
function Column({
  tabKey,
  active,
  children,
}: {
  tabKey: LibraryTabKey;
  active: LibraryTabKey;
  children: React.ReactNode;
}) {
  return (
    <section
      role="tabpanel"
      id={`lib-panel-${tabKey}`}
      aria-labelledby={`lib-tab-${tabKey}`}
      className={cn(
        "outline-none lg:block lg:h-full lg:min-h-0 lg:overflow-y-auto lg:border-l lg:border-hair-strong lg:pb-[28px] lg:first:border-l-0",
        active !== tabKey && "hidden",
      )}
    >
      {children}
    </section>
  );
}

/**
 * The Library's lower portion: three open columns (Scenarios · Characters ·
 * Settings) side-by-side on desktop. On mobile the columns collapse to a
 * single section chosen by the 3-tab switcher. Each column renders exactly once
 * (no duplicated content) — visibility is CSS-only.
 */
export function LibraryColumns({
  lib,
}: {
  lib: ReturnType<typeof useLibraryState>;
}) {
  const tabs: TabItem[] = [
    { key: "scenarios", label: "Scenarios", count: lib.counts.scenarios },
    { key: "characters", label: "Characters", count: lib.counts.characters },
    { key: "settings", label: "Settings", count: lib.counts.settings },
  ];
  const castIds = lib.featured?.castIds ?? [];
  const settingId = lib.featured?.settingId ?? "";

  // Gated at 300ms: a library that loads from a warm cache should not flash
  // three columns of placeholders on its way to the real thing. Without the
  // gate the skeleton IS the jank it exists to prevent.
  const showSkeletons = useDelayedFlag(lib.loading);

  // Clearing the search is the only useful action when a filter has emptied a
  // column, so the empty state offers it.
  const clearQuery = () => lib.setQuery("");

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* Mobile-only section switcher; desktop shows all three columns. */}
      <div className="lg:hidden">
        <LibraryTabs
          tabs={tabs}
          active={lib.tab}
          onChange={(key) => lib.setTab(key as LibraryTabKey)}
        />
      </div>

      {/* Mobile: the whole area scrolls (single active column). Desktop: the
          grid row is pinned to the viewport and each column scrolls on its own,
          so the page itself never scrolls past the screen. A solid bg-page
          (full width) sits behind the columns so the page's radial glow never
          shows through behind the scrolling cards. */}
      <div className="min-h-0 flex-1 overflow-y-auto bg-page px-[20px] pt-[18px] pb-[30px] sm:px-[28px] lg:grid lg:grid-cols-3 lg:grid-rows-[minmax(0,1fr)] lg:gap-0 lg:overflow-hidden lg:px-[28px] lg:pt-[18px] lg:pb-0">
        <Column tabKey="scenarios" active={lib.tab}>
          <ScenarioColumn
            scenarios={lib.filteredScenarios}
            featuredId={lib.featuredId}
            query={lib.query}
            onSelect={lib.setFeaturedId}
            onEdit={lib.editScenario}
            onProfile={lib.openProfile}
            onAdd={() => lib.openCreate("scenario")}
            onClearQuery={clearQuery}
            loading={showSkeletons}
            padX="lg:pr-[24px]"
          />
        </Column>

        <Column tabKey="characters" active={lib.tab}>
          <CharacterColumn
            characters={lib.filteredCharacters}
            castIds={castIds}
            query={lib.query}
            onPreview={lib.openProfile}
            onEdit={lib.editCharacter}
            onAdd={() => lib.openCreate("character")}
            onClearQuery={clearQuery}
            loading={showSkeletons}
            padX="lg:px-[24px]"
          />
        </Column>

        <Column tabKey="settings" active={lib.tab}>
          <SettingColumn
            settings={lib.filteredSettings}
            activeId={settingId}
            query={lib.query}
            onEdit={lib.editSetting}
            onAdd={() => lib.openCreate("setting")}
            onClearQuery={clearQuery}
            loading={showSkeletons}
            padX="lg:pl-[24px]"
          />
        </Column>
      </div>
    </div>
  );
}
