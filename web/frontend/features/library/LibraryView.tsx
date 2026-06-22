"use client";

import {
  useLibraryState,
  type LibraryTabKey,
} from "@/features/library/useLibraryState";
import { AppHeader } from "@/components/layout/AppHeader";
import { LibraryTabs, type TabItem } from "@/components/feature/LibraryTabs";
import { ScenarioCarousel } from "@/components/feature/ScenarioCarousel";
import { CharacterCard } from "@/components/feature/CharacterCard";
import { SettingCard } from "@/components/feature/SettingCard";
import { ScenarioCard } from "@/components/feature/ScenarioCard";
import { BranchRow } from "@/components/feature/BranchRow";
import { CreateMenu } from "@/components/feature/CreateMenu";
import { StorylineMenu } from "@/components/feature/StorylineMenu";
import { EntityModal } from "@/components/feature/EntityModal";
import { CharacterProfileModal } from "@/components/feature/CharacterProfileModal";
import { BeginSceneModal } from "@/components/feature/BeginSceneModal";
import { Eyebrow } from "@/components/ui/Eyebrow";

function TabPanel({
  tabKey,
  children,
}: {
  tabKey: string;
  children: React.ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      id={`lib-panel-${tabKey}`}
      aria-labelledby={`lib-tab-${tabKey}`}
      tabIndex={0}
      className="outline-none"
    >
      {children}
    </div>
  );
}

function EmptyNote({ query, noun }: { query: string; noun: string }) {
  return (
    <p className="py-[30px] text-center font-body text-mute2 italic">
      {query ? `No ${noun} match “${query}”.` : `No ${noun} yet.`}
    </p>
  );
}

/** The Library surface: header → recent-scenario carousel → tabs → content + editors. */
export function LibraryView() {
  const lib = useLibraryState();

  const tabs: TabItem[] = [
    { key: "scenarios", label: "Scenarios", count: lib.counts.scenarios },
    { key: "characters", label: "Characters", count: lib.counts.characters },
    { key: "settings", label: "Settings", count: lib.counts.settings },
    { key: "storylines", label: "Storylines", count: lib.counts.branches },
  ];

  const beginScenario = lib.modal?.type === "begin" ? lib.featured : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">Velora — Library</h1>
      <AppHeader
        query={lib.query}
        onQuery={lib.setQuery}
        storylineSlot={
          <StorylineMenu
            storylines={lib.storylines}
            activeId={lib.activeStorylineId}
            onSwitch={lib.switchStoryline}
            onCreate={lib.createStoryline}
          />
        }
        createSlot={
          <CreateMenu
            open={lib.menuOpen}
            onToggle={() => lib.setMenuOpen(!lib.menuOpen)}
            onClose={() => lib.setMenuOpen(false)}
            onCreate={lib.openCreate}
          />
        }
      />

      <ScenarioCarousel
        slides={lib.resolvedScenarios}
        index={lib.featuredIndex}
        counterText={`${lib.featuredIndex + 1} / ${lib.scenarios.length}`}
        onPrev={() => lib.cycleFeatured(-1)}
        onNext={() => lib.cycleFeatured(1)}
        onSelect={lib.setFeaturedId}
        onBegin={lib.openBegin}
        onProfile={lib.openProfile}
      />

      <div className="mt-[16px]">
        <LibraryTabs
          tabs={tabs}
          active={lib.tab}
          onChange={(key) => lib.setTab(key as LibraryTabKey)}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-[28px] pt-[20px] pb-[30px]">
        {lib.tab === "scenarios" ? (
          <TabPanel tabKey="scenarios">
            <p className="mb-[14px] font-mono text-[10px] tracking-[0.06em] text-mute">
              Select a scenario to feature it · its cast &amp; setting carry into
              the scene.
            </p>
            {lib.filteredScenarios.length === 0 ? (
              <EmptyNote query={lib.query} noun="scenarios" />
            ) : (
              <div className="grid grid-cols-1 gap-[16px] sm:grid-cols-2 xl:grid-cols-3">
                {lib.filteredScenarios.map((s) => (
                  <ScenarioCard
                    key={s.id}
                    scenario={s}
                    featured={s.id === lib.featuredId}
                    onSelect={() => lib.setFeaturedId(s.id)}
                    onEdit={() => lib.editScenario(s.id)}
                    onProfile={lib.openProfile}
                  />
                ))}
              </div>
            )}
          </TabPanel>
        ) : null}

        {lib.tab === "characters" ? (
          <TabPanel tabKey="characters">
            {lib.filteredCharacters.length === 0 ? (
              <EmptyNote query={lib.query} noun="characters" />
            ) : (
              <div className="grid grid-cols-1 gap-[14px] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {lib.filteredCharacters.map((c) => (
                  <CharacterCard
                    key={c.id}
                    character={c}
                    expanded={lib.expandedCharId === c.id}
                    onToggle={() => lib.toggleExpand(c.id)}
                    onEdit={() => lib.editCharacter(c.id)}
                  />
                ))}
              </div>
            )}
          </TabPanel>
        ) : null}

        {lib.tab === "settings" ? (
          <TabPanel tabKey="settings">
            {lib.filteredSettings.length === 0 ? (
              <EmptyNote query={lib.query} noun="settings" />
            ) : (
              <div className="grid grid-cols-1 gap-[14px] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {lib.filteredSettings.map((s) => (
                  <SettingCard
                    key={s.id}
                    setting={s}
                    onEdit={() => lib.editSetting(s.id)}
                  />
                ))}
              </div>
            )}
          </TabPanel>
        ) : null}

        {lib.tab === "storylines" ? (
          <TabPanel tabKey="storylines">
            <div className="max-w-[880px]">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-baseline gap-3">
                  <h2 className="font-display text-[22px] font-semibold text-ink">
                    Storylines
                  </h2>
                  <Eyebrow size={10} tracking="0.08em" color="var(--accent)">
                    {lib.featured?.title}
                  </Eyebrow>
                </div>
                <button
                  type="button"
                  onClick={() => lib.openCreate("branch")}
                  className="rounded-[2px] border border-accent bg-card px-[14px] py-[8px] font-mono text-[10px] tracking-[0.08em] text-accent uppercase hover:bg-accent hover:text-[#F6ECDA]"
                >
                  + New Branch
                </button>
              </div>
              <p className="mt-[6px] mb-[18px] font-body text-[14px] text-ink-soft italic">
                {lib.featured?.goal}
              </p>
              {(lib.featured?.branches.length ?? 0) === 0 ? (
                <div className="rounded-[3px] border border-dashed border-cardbd p-[26px] text-center font-body text-mute2 italic">
                  No branches authored yet. Use{" "}
                  <span className="text-accent">+ New Branch</span>.
                </div>
              ) : (
                <div className="flex flex-col gap-[11px]">
                  {(lib.featured?.branches ?? []).map((b, i) => (
                    <BranchRow
                      key={`${b.label}-${i}`}
                      branch={b}
                      onEdit={() =>
                        lib.featured && lib.editBranch(lib.featured.id, i)
                      }
                      onDelete={() =>
                        lib.featured && lib.deleteBranch(lib.featured.id, i)
                      }
                    />
                  ))}
                </div>
              )}
            </div>
          </TabPanel>
        ) : null}
      </div>

      <EntityModal lib={lib} />
      <CharacterProfileModal
        character={lib.profileChar}
        onClose={lib.closeProfile}
        onEdit={lib.editCharacter}
      />
      <BeginSceneModal scenario={beginScenario} onClose={lib.closeModal} />
    </div>
  );
}
