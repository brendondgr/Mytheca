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
    // h-dvh + overflow-hidden makes the Library self-contained: the page never
    // scrolls, and the three columns each scroll within the remaining height.
    <div className="flex h-dvh min-h-0 flex-col overflow-hidden">
      <h1 className="sr-only">Mytheca — Library</h1>
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

      {lib.error && !lib.modal && !lib.storylineToDelete ? (
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
        counterText={`${lib.featuredIndex + 1} / ${lib.scenarios.length}`}
        onPrev={() => lib.cycleFeatured(-1)}
        onNext={() => lib.cycleFeatured(1)}
        onSelect={lib.setFeaturedId}
        onBegin={lib.openBegin}
        onProfile={lib.openProfile}
        onEdit={lib.editScenario}
      />

      {/* The three columns are the Library's main region — it had an `sr-only` h1 and no
          landmark to jump to. */}
      <main id="main" tabIndex={-1} className="mt-lg flex min-h-0 flex-1 flex-col border-t border-hair-strong">
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
