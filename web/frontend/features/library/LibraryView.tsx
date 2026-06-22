"use client";

import { useLibraryState } from "@/features/library/useLibraryState";
import { LibraryColumns } from "@/features/library/LibraryColumns";
import { AppHeader } from "@/components/layout/AppHeader";
import { ScenarioCarousel } from "@/components/feature/ScenarioCarousel";
import { CreateMenu } from "@/components/feature/CreateMenu";
import { StorylineMenu } from "@/components/feature/StorylineMenu";
import { EntityModal } from "@/components/feature/EntityModal";
import { CharacterProfileModal } from "@/components/feature/CharacterProfileModal";
import { BeginSceneModal } from "@/components/feature/BeginSceneModal";

/** The Library surface: header → recent-scenario carousel → open columns + editors. */
export function LibraryView() {
  const lib = useLibraryState();

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

      <div className="mt-[16px] flex min-h-0 flex-1 flex-col">
        <LibraryColumns lib={lib} />
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
