"use client";

import { useLibraryState } from "@/features/library/useLibraryState";
import { LibraryColumns } from "@/features/library/LibraryColumns";
import { AppHeader } from "@/components/layout/AppHeader";
import { ScenarioCarousel } from "@/components/feature/ScenarioCarousel";
import { CreateMenu } from "@/components/feature/CreateMenu";
import { OptionsMenu } from "@/components/feature/OptionsMenu";
import { StorylineMenu } from "@/components/feature/StorylineMenu";
import { EntityModal } from "@/components/feature/EntityModal";
import { CharacterModal } from "@/components/feature/CharacterModal";
import { StorylineModal } from "@/components/feature/StorylineModal";
import { StorylineDeleteModal } from "@/components/feature/StorylineDeleteModal";
import { CharacterProfileModal } from "@/components/feature/CharacterProfileModal";
import { BeginSceneModal } from "@/components/feature/BeginSceneModal";

/** The Library surface: header → recent-scenario carousel → open columns + editors. */
export function LibraryView() {
  const lib = useLibraryState();

  const beginScenario = lib.modal?.type === "begin" ? lib.featured : null;

  return (
    // h-dvh + overflow-hidden makes the Library self-contained: the page never
    // scrolls, and the three columns each scroll within the remaining height.
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden">
      <h1 className="sr-only">Velora — Library</h1>
      <AppHeader
        query={lib.query}
        onQuery={lib.setQuery}
        storylineSlot={
          <StorylineMenu
            storylines={lib.storylines}
            activeId={lib.activeStorylineId}
            onSwitch={lib.switchStoryline}
            onCreate={lib.openCreateStoryline}
            onEdit={lib.editStoryline}
            onDelete={lib.requestDeleteStoryline}
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
        optionsSlot={<OptionsMenu />}
      />

      {lib.error && !lib.modal && !lib.storylineToDelete ? (
        <div
          role="alert"
          className="mx-[18px] mt-[12px] flex items-center justify-between gap-[12px] rounded-[6px] border border-cardbd bg-card px-[14px] py-[10px]"
        >
          <span className="font-body text-[14px] text-ink">{lib.error}</span>
          <button
            type="button"
            onClick={lib.retry}
            className="cursor-pointer font-mono text-[11px] tracking-[0.08em] text-accent uppercase hover:underline"
          >
            Retry
          </button>
        </div>
      ) : null}

      {lib.loading ? (
        <p aria-live="polite" className="px-[18px] pt-[12px] font-body text-[14px] text-mute">
          Loading your library…
        </p>
      ) : null}

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
      <CharacterModal lib={lib} />
      <StorylineModal lib={lib} />
      <StorylineDeleteModal
        storyline={lib.storylineToDelete}
        pending={lib.pending}
        error={lib.error}
        onConfirm={lib.confirmDeleteStoryline}
        onCancel={lib.cancelDeleteStoryline}
      />
      <CharacterProfileModal
        character={lib.profileChar}
        onClose={lib.closeProfile}
        onEdit={lib.editCharacter}
      />
      <BeginSceneModal scenario={beginScenario} onClose={lib.closeModal} />
    </div>
  );
}
