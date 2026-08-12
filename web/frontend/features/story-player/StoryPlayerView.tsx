"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ENTER_TRANSITION } from "@/lib/motion";
import { exportSessionUrl } from "@/lib/api";
import type {
  Character,
  ContextDocumentIndexEntry,
  ResolvedScenario,
  StatDefinition,
} from "@/lib/types";
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
import { TranscriptAnnouncer } from "@/components/feature/TranscriptAnnouncer";
import { TurnStatusStrip } from "@/components/feature/TurnStatusStrip";
import { JumpToLatest } from "@/components/feature/JumpToLatest";
import { useStickyBottom } from "./use-sticky-bottom";
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
  contextDocs = [],
  backHref = "/",
}: {
  scenario: ResolvedScenario;
  statDefs?: StatDefinition[];
  storylineName?: string;
  /** The storyline's context documents — the rows the composer's `@` menu offers. */
  contextDocs?: ContextDocumentIndexEntry[];
  backHref?: string;
}) {
  const scene = useScenePlay(scenario, contextDocs);
  // One string per transcript beat (its dialogue/action/thought), so the composer's Config
  // "Number of beats" readout reflects the REAL recent content, not a flat average.
  const beatTexts = useMemo(
    () => scene.messages.map((m) => [m.text, m.action, m.thought].filter(Boolean).join(" ")),
    [scene.messages],
  );
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  // Follow the newest beat only while the reader is already at the bottom.
  // Anything else is yanking the page away from someone who is reading.
  // Destructured at the call site so the render body reads plain locals rather
  // than properties of an object that also carries a ref — the refs lint rule
  // cannot tell those apart.
  const {
    ref: transcriptRef,
    detached: readerScrolledUp,
    jumpToLatest,
  } = useStickyBottom([scene.messages.length, scene.reveal]);
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
        <div className="relative flex min-w-0 flex-1 flex-col">
          <div
            ref={transcriptRef}
            // `.stream-viewport` sets overflow-anchor: none so the browser's own
            // scroll anchoring does not fight the sticky-bottom hook for control
            // of the scroll position as beats stream in.
            className="stream-viewport min-h-0 flex-1 overflow-auto p-[20px_16px_10px] sm:p-[24px_30px_10px]"
          >
            <div
              className="mx-auto flex max-w-[720px] flex-col gap-4 transition-[opacity,transform] duration-slow ease-out"
              style={{
                opacity: scene.reveal ? 1 : 0,
                transform: scene.reveal ? "none" : "translateY(var(--lift-lg))",
              }}
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
                  transition={ENTER_TRANSITION}
                  // The beat currently being written gets a couple of lines of
                  // reserved height, so the composer does not hop the instant
                  // the first token lands and again as the line wraps.
                  className={
                    scene.sending && i === scene.messages.length - 1
                      ? "min-h-[3.2em]"
                      : undefined
                  }
                >
                  <TranscriptBeat
                    message={m}
                    charById={byId}
                    onProfile={scene.openProfile}
                    choices={scene.choices}
                    onChoose={onChoose}
                    onOpenImage={setLightbox}
                    streaming={scene.sending && i === scene.messages.length - 1}
                  />
                </motion.div>
              ))}
              {/* Who is up, while the turn is being written. Sits in the same slot the
                  CreateImageBar occupies between turns (the two are gated on `sending` in
                  opposite directions), so the foot of the transcript never empties out. */}
              <TurnStatusStrip
                status={scene.turnStatus}
                streaming={scene.sending}
                charById={byId}
              />
              {scene.streamError ? (
                <p role="alert" className="text-center font-mono text-[11px] tracking-[0.08em] text-danger">
                  {scene.streamError}
                </p>
              ) : null}
              {/* The very bottom of the chat — below the last beat, above the composer.
                  Only once a turn has finished: there is no moment to picture before the
                  first turn, and offering it mid-stream would paint a half-played beat.
                  Enters with the transcript's own beat animation rather than popping in. */}
              {scene.sessionId && !scene.sending ? (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={ENTER_TRANSITION}
                >
                  <CreateImageBar
                    onCreate={scene.createImage}
                    running={scene.creatingImage}
                    stage={scene.imageStage}
                    error={scene.imageError}
                    className="mt-[2px]"
                  />
                </motion.div>
              ) : null}
            </div>
          </div>

          {/* Streamed prose is announced here, once per completed turn — not by
              a live region on the transcript itself. See TranscriptAnnouncer. */}
          <TranscriptAnnouncer
            messages={scene.messages}
            streaming={scene.sending}
            nameOf={(id) => (id ? (byId(id)?.name ?? id) : "Someone")}
          />

          {/* Only while the reader has scrolled away from the live edge. */}
          {readerScrolledUp ? (
            <JumpToLatest onClick={jumpToLatest} className="bottom-[96px]" />
          ) : null}

          <Composer
            mentionOptions={contextDocs}
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
            guidance={scene.guidance}
            onGuidanceChange={scene.setGuidance}
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
