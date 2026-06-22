"use client";

import type { useLibraryState } from "@/features/library/useLibraryState";
import type { LibraryTabKey } from "@/features/library/useLibraryState";
import { LibraryTabs, type TabItem } from "@/components/feature/LibraryTabs";
import { ScenarioColumn } from "@/components/feature/ScenarioColumn";
import { CharacterColumn } from "@/components/feature/CharacterColumn";
import { SettingColumn } from "@/components/feature/SettingColumn";
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
        "outline-none lg:block lg:border-l lg:border-hair lg:px-[24px] lg:first:border-l-0 lg:first:pl-0 lg:last:pr-0",
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

      <div className="min-h-0 flex-1 overflow-auto px-[20px] pt-[18px] pb-[30px] sm:px-[28px] lg:grid lg:grid-cols-3 lg:gap-0">
        <Column tabKey="scenarios" active={lib.tab}>
          <ScenarioColumn
            scenarios={lib.filteredScenarios}
            featuredId={lib.featuredId}
            query={lib.query}
            onSelect={lib.setFeaturedId}
            onEdit={lib.editScenario}
            onProfile={lib.openProfile}
          />
        </Column>

        <Column tabKey="characters" active={lib.tab}>
          <CharacterColumn
            characters={lib.filteredCharacters}
            castIds={castIds}
            expandedId={lib.expandedCharId}
            query={lib.query}
            onToggle={lib.toggleExpand}
            onEdit={lib.editCharacter}
          />
        </Column>

        <Column tabKey="settings" active={lib.tab}>
          <SettingColumn
            settings={lib.filteredSettings}
            activeId={settingId}
            query={lib.query}
            onEdit={lib.editSetting}
          />
        </Column>
      </div>
    </div>
  );
}
