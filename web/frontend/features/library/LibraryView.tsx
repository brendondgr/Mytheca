"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useLibraryState } from "@/features/library/useLibraryState";
import { LibraryColumns } from "@/features/library/LibraryColumns";
import { AppHeader } from "@/components/layout/AppHeader";
import { ScenarioCarousel } from "@/components/feature/ScenarioCarousel";
import { CreateMenu } from "@/components/feature/CreateMenu";
import { OptionsMenu } from "@/components/feature/OptionsMenu";
import { StorylineMenu } from "@/components/feature/StorylineMenu";
import { EntityModal } from "@/components/feature/EntityModal";
import { CharacterModal } from "@/components/feature/CharacterModal";
import { SettingModal } from "@/components/feature/SettingModal";
import { StorylineDeleteModal } from "@/components/feature/StorylineDeleteModal";
import { ScenarioDeleteModal } from "@/components/feature/ScenarioDeleteModal";
import { PromptOverridesModal } from "@/components/feature/PromptOverridesModal";
import { CharacterProfileModal } from "@/components/feature/CharacterProfileModal";
import { BeginSceneModal } from "@/components/feature/BeginSceneModal";
import { updateStoryline } from "@/lib/api";

/** The Library surface: header → recent-scenario carousel → open columns + editors. */
export function LibraryView({ initialStorylineId }: { initialStorylineId?: string } = {}) {
  const lib = useLibraryState(initialStorylineId);
  const router = useRouter();

  // Storyline create/edit now live on a dedicated page (not a modal).
  const goCreateStoryline = () => router.push("/storylines/new");
  const goEditStoryline = (id: string) => router.push(`/storylines/${id}/edit`);
  const goDocuments = (id: string) => router.push(`/storylines/${id}/documents`);

  // Empty-state default: with no storylines, the New Storyline page IS the home.
  useEffect(() => {
    if (!lib.loading && lib.storylines.length === 0) router.replace("/storylines/new");
  }, [lib.loading, lib.storylines.length, router]);

  const beginScenario = lib.modal?.type === "begin" ? lib.featured : null;

  return (
    // At `lg` the Library is self-contained — `h-dvh` + `overflow-hidden`, three columns
    // each scrolling inside the remaining height, so the page itself never scrolls.
    //
    // Below `lg` that inverts: the page is the scroller. One column shows at a time, so
    // there is nothing for a locked shell to buy, and a viewport-locked page with an
    // inner scrolling pane fights the browser's own scroll on a phone — the address bar
    // never collapses, and the hero and the list read as two surfaces moving separately.
    <div className="flex min-h-dvh flex-col lg:h-dvh lg:min-h-0 lg:overflow-hidden">
      <h1 className="sr-only">Mytheca — Library</h1>
      {/* Sticky below `lg`, where the page scrolls under it: the storyline switcher and
          Create are the two things you reach for after scrolling, and a header that
          leaves the screen makes both a scroll back to the top. `--header-h` already
          drives `scroll-padding-top`, so anchors and focused elements clear it. */}
      <div className="sticky top-0 z-[15] lg:static">
      <AppHeader
        query={lib.query}
        onQuery={lib.setQuery}
        storylineSlot={
          <StorylineMenu
            storylines={lib.storylines}
            activeId={lib.activeStorylineId}
            onSwitch={lib.switchStoryline}
            onCreate={goCreateStoryline}
            onEdit={goEditStoryline}
            onConfigurePrompts={lib.openStorylinePrompts}
            onDocuments={goDocuments}
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
      </div>

      {lib.error && !lib.modal && !lib.storylineToDelete && !lib.scenarioToDelete ? (
        <div
          role="alert"
          className="mx-lg mt-md flex items-center justify-between gap-md rounded-sm border border-cardbd bg-card px-lg py-sm"
        >
          <span className="font-body text-body-sm text-ink">{lib.error}</span>
          <button
            type="button"
            onClick={lib.retry}
            className="cursor-pointer font-mono text-eyebrow tracking-[0.08em] text-accent-ink uppercase hover:underline"
          >
            Retry
          </button>
        </div>
      ) : null}

      {/* The columns carry the wait themselves now, as skeletons tracing the
          cards that are coming. A bare "Loading your library…" line above an
          otherwise-blank page told the user nothing about what would appear,
          and pushed the layout down when it disappeared. The announcement it
          carried is preserved: each column sets `aria-busy` while it waits. */}

      <ScenarioCarousel
        slides={lib.resolvedScenarios}
        statDefs={lib.statDefs}
        statsByCharId={lib.statsByCharId}
        index={lib.featuredIndex}
        onPrev={() => lib.cycleFeatured(-1)}
        onNext={() => lib.cycleFeatured(1)}
        onSelect={lib.setFeaturedId}
        onBegin={lib.openBegin}
        onProfile={lib.openProfile}
        onEdit={lib.editScenario}
      />

      {/* The three columns are the Library's main region — it had an `sr-only` h1 and no
          landmark to jump to. */}
      <main id="main" tabIndex={-1} className="mt-lg flex flex-col border-t border-hair-strong lg:min-h-0 lg:flex-1">
        <LibraryColumns lib={lib} />
      </main>

      <EntityModal lib={lib} />
      <CharacterModal lib={lib} />
      <SettingModal lib={lib} />
      <StorylineDeleteModal
        storyline={lib.storylineToDelete}
        pending={lib.pending}
        error={lib.error}
        onConfirm={lib.confirmDeleteStoryline}
        onCancel={lib.cancelDeleteStoryline}
      />
      <ScenarioDeleteModal
        scenario={lib.scenarioToDelete}
        pending={lib.pending}
        error={lib.error}
        onConfirm={lib.confirmDeleteScenario}
        onCancel={lib.cancelDeleteScenario}
      />
      {lib.promptsStoryline ? (
        <PromptOverridesModal
          open
          onClose={lib.closeStorylinePrompts}
          heading={`${lib.promptsStoryline.title} — writing prompts`}
          subtitle="Tune this storyline's tone, phrasing, and how the story progresses. Overrides the global defaults for every scene in this world; a scenario can override again."
          overrides={lib.promptsStoryline.promptOverrides ?? {}}
          saveLabel="Save storyline prompts"
          onSave={async (map) => {
            const id = lib.promptsStoryline!.id;
            await updateStoryline(id, { promptOverrides: map });
            lib.applyStorylinePrompts(id, map);
          }}
        />
      ) : null}
      <CharacterProfileModal
        character={lib.profileChar}
        onClose={lib.closeProfile}
        onEdit={lib.editCharacter}
      />
      <BeginSceneModal
        scenario={beginScenario}
        storylineId={lib.activeStorylineId}
        onClose={lib.closeModal}
      />
    </div>
  );
}
