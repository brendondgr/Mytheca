"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { exportSessionUrl } from "@/lib/api";
import type { Character, ResolvedScenario, StatDefinition } from "@/lib/types";
import type { ExportFormat } from "@/components/feature/ExportMenu";
import { useScenePlay } from "./useScenePlay";
import type { SceneImage } from "./scene-data";
import { SceneHeader, type SceneViewMode } from "@/components/layout/SceneHeader";
import { CastRail } from "@/components/feature/CastRail";
import { GraphView } from "@/components/feature/GraphView";
import { DirectorRail } from "@/components/feature/DirectorRail";
import { Composer } from "@/components/feature/Composer";
import { SceneLoader } from "@/components/feature/SceneLoader";
import { SceneIntro } from "@/components/feature/SceneIntro";
import { TranscriptBeat } from "@/components/feature/TranscriptBeat";
import { CreateImageBar } from "@/components/feature/CreateImageBar";
import { SceneImageModal } from "@/components/feature/SceneImageModal";
import { CharacterDossier } from "@/components/feature/CharacterDossier";
import { CharacterProfileModal } from "@/components/feature/CharacterProfileModal";
import { TurnInspectorPanel } from "@/components/feature/TurnInspectorPanel";

/** The signature surface: a three-zone "open book" live scene. */
export function StoryPlayerView({
  scenario,
  statDefs = [],
  storylineName,
  backHref = "/",
}: {
  scenario: ResolvedScenario;
  statDefs?: StatDefinition[];
  storylineName?: string;
  backHref?: string;
}) {
  const scene = useScenePlay(scenario);
  // One string per transcript beat (its dialogue/action/thought), so the composer's Config
  // "Number of beats" readout reflects the REAL recent content, not a flat average.
  const beatTexts = useMemo(
    () => scene.messages.map((m) => [m.text, m.action, m.thought].filter(Boolean).join(" ")),
    [scene.messages],
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  // Picking a suggestion writes it into the composer for review/editing; move focus there so
  // the player can immediately edit before sending (request #2).
  const onChoose = useCallback(
    (choice: Parameters<typeof scene.choose>[0]) => {
      scene.choose(choice);
      composerRef.current?.focus();
    },
    [scene],
  );
  const [modalId, setModalId] = useState<string | null>(null);
  // The transcript scene image currently enlarged (null = the lightbox is closed).
  const [lightbox, setLightbox] = useState<SceneImage | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [viewMode, setViewMode] = useState<SceneViewMode>("chat");
  const byId = (id: string): Character | undefined =>
    scenario.cast.find((c) => c.id === id);

  // Keep the transcript pinned to the latest beat.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [scene.messages.length, scene.reveal]);

  // Download the full conversation record (server-rendered) as an attachment.
  const onExport = useCallback(
    (format: ExportFormat) => {
      if (!scene.sessionId) return;
      const url = exportSessionUrl(scenario.id, scene.sessionId, format);
      const a = document.createElement("a");
      a.href = url;
      a.rel = "noopener";
      a.click();
    },
    [scenario.id, scene.sessionId],
  );

  const profileChar = scene.profileId ? (byId(scene.profileId) ?? null) : null;
  const modalChar = modalId ? (byId(modalId) ?? null) : null;

  // The characters the player may speak AS (Player POV) — the present cast, with the avatar
  // data the custom dropdown renders (portrait falls back to the monogram).
  const povOptions = useMemo(
    () =>
      scenario.cast
        .filter((c) => (scene.presenceByChar[c.id] ?? "present") === "present")
        .map((c) => ({ id: c.id, name: c.name, mono: c.mono, color: c.color, portrait: c.portrait })),
    [scenario.cast, scene.presenceByChar],
  );

  return (
    <div className="flex h-dvh flex-col overflow-hidden">
      <h1 className="sr-only">{scenario.title} — live scene</h1>
      <SceneHeader
        title={scenario.title}
        settingName={scenario.setting.name}
        genre={scenario.genre}
        tone={scenario.tone}
        backHref={backHref}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        onExport={onExport}
        canExport={Boolean(scene.sessionId)}
        onToggleInspector={viewMode === "graph" ? undefined : () => setInspectorOpen((o) => !o)}
        inspectorOpen={inspectorOpen}
      />

      <div className="flex min-h-0 flex-1">
        <CastRail
          cast={scenario.cast}
          speakingId={scene.speakingId}
          turnOrder={scene.turnOrder}
          charById={byId}
          onProfile={scene.openProfile}
          presenceByChar={scene.presenceByChar}
          setPresence={scene.setPresence}
          statDefs={statDefs}
          statsByChar={scene.statsByChar}
          activityByChar={scene.activityByChar}
        />

        {viewMode === "graph" ? (
          <GraphView scenarioId={scenario.id} />
        ) : (
        <>
        <div className="flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto p-[20px_16px_10px] sm:p-[24px_30px_10px]">
            <div
              className="mx-auto flex max-w-[720px] flex-col gap-4 transition-[opacity,transform] duration-[550ms]"
              style={{
                opacity: scene.reveal ? 1 : 0,
                transform: scene.reveal ? "none" : "translateY(14px)",
              }}
              aria-live="polite"
              aria-relevant="additions"
              aria-busy={!scene.reveal}
            >
              <SceneIntro scenario={scenario} onProfile={scene.openProfile} />
              <div className="py-[2px] text-center font-mono text-[9px] tracking-[0.16em] text-mute2 uppercase">
                — the scene is joined —
              </div>
              {scene.messages.map((m, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, ease: "easeOut" }}
                >
                  <TranscriptBeat
                    message={m}
                    charById={byId}
                    onProfile={scene.openProfile}
                    choices={scene.choices}
                    onChoose={onChoose}
                    onOpenImage={setLightbox}
                  />
                </motion.div>
              ))}
              {scene.streamError ? (
                <p role="alert" className="text-center font-mono text-[11px] tracking-[0.08em] text-danger">
                  {scene.streamError}
                </p>
              ) : null}
              {/* The very bottom of the chat — below the last beat, above the composer. */}
              <CreateImageBar
                onCreate={scene.createImage}
                running={scene.creatingImage}
                stage={scene.imageStage}
                error={scene.imageError}
                disabled={!scene.sessionId}
                className="mt-[2px]"
              />
            </div>
          </div>
          <Composer
            value={scene.composer}
            onChange={scene.setComposer}
            onSend={scene.send}
            sendDisabled={scene.sending}
            inputRef={composerRef}
            maxTurns={scene.maxTurns}
            onMaxTurnsChange={scene.setMaxTurns}
            suggestionsCount={scene.suggestionsCount}
            onSuggestionsCountChange={scene.setSuggestionsCount}
            contextBeats={scene.contextBeats}
            onContextBeatsChange={scene.setContextBeats}
            beatTexts={beatTexts}
            pov={scene.pov}
            onPovChange={scene.setPov}
            povOptions={povOptions}
            usedTokens={scene.usedTokens}
            maxContextTokens={scene.maxContextTokens}
            usedTokensExact={scene.usedTokensExact}
          />
        </div>

        {profileChar ? (
          <CharacterDossier
            character={profileChar}
            statDefs={statDefs}
            stats={scene.statsByChar[profileChar.id]}
            relationships={scene.relationships}
            onClose={scene.closeProfile}
            onOpenProfile={setModalId}
          />
        ) : (
          <DirectorRail
            stats={scene.stats}
            activity={scene.activity}
            charById={byId}
          />
        )}

        {/* Docked to the far right of the Director rail — the chat stays visible. */}
        <TurnInspectorPanel
          open={inspectorOpen}
          onClose={() => setInspectorOpen(false)}
          turns={scene.traceTurns}
        />
        </>
        )}
      </div>

      <SceneLoader scenario={scenario} storylineName={storylineName} visible={scene.loading} />
      <CharacterProfileModal character={modalChar} onClose={() => setModalId(null)} />
      <SceneImageModal image={lightbox} onClose={() => setLightbox(null)} />
    </div>
  );
}
