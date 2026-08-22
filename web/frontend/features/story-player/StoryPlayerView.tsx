"use client";

import { Fragment, useCallback, useMemo, useRef, useState } from "react";
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
import { availableVerbs } from "@/lib/sceneVerbs";
import { useModelHealth } from "@/hooks/use-model-health";
import { useSceneShortcuts } from "@/hooks/use-scene-shortcuts";
import { ShortcutSheet } from "@/components/feature/ShortcutSheet";
import type { SceneImage, SceneMessage } from "./scene-data";
import { SceneHeader, type SceneViewMode } from "@/components/layout/SceneHeader";
import { CastRail } from "@/components/feature/CastRail";
import { PlaythroughTray } from "@/components/feature/PlaythroughTray";
import { BeatControls } from "@/components/feature/BeatControls";
import { BeatEditor } from "@/components/feature/BeatEditor";
import { BeatTakePager } from "@/components/feature/BeatTakePager";
import { RewindNotice } from "@/components/feature/RewindNotice";
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
import { TranscriptFootBar } from "@/components/feature/TranscriptFootBar";
import { SceneImageModal } from "@/components/feature/SceneImageModal";
import { CharacterDossier } from "@/components/feature/CharacterDossier";
import { CharacterProfileModal } from "@/components/feature/CharacterProfileModal";
import { TurnInspectorPanel } from "@/components/feature/TurnInspectorPanel";
import { SceneMemoryPanel } from "@/components/feature/SceneMemoryPanel";
import { MemoryEdge } from "@/components/feature/MemoryEdge";


/**
 * The index of the player turn a beat belongs to — the nearest player-authored beat at or
 * before it. A rewind removes that whole turn, so this is what makes the confirmation able
 * to say how many beats actually go instead of asking the player to guess.
 */
export function turnStartIndex(messages: SceneMessage[], index: number): number {
  for (let i = index; i >= 0; i -= 1) {
    const m = messages[i];
    // A direction-only turn opens with a `direction` aside instead of a spoken line — it is
    // still the start of a turn, and a rewind that misses it would report the wrong count.
    if (
      m.kind === "player" ||
      m.kind === "direction" ||
      (m.kind === "char" && m.fromPlayer)
    )
      return i;
  }
  return 0;
}

/** What a beat is called, for the controls' accessible names. */
function beatLabel(m: SceneMessage, byId: (id: string) => Character | undefined): string {
  if (m.kind === "player") return "your message";
  if (m.kind === "direction") return "your direction";
  if (m.kind === "narrator") return "the narration";
  if (m.kind === "image") return "this picture";
  if (m.kind === "char" && m.who) {
    const name = byId(m.who)?.name ?? "this character";
    return m.fromPlayer ? `your line as ${name}` : `${name}'s beat`;
  }
  return "this beat";
}

/** The signature surface: a three-zone "open book" live scene. */
/**
 * Phases the transcript itself is already showing, in place, on the speaker's own beat.
 * The status strip suppresses these so the two do not narrate the same moment.
 */
const CHARACTER_PHASES = new Set(["thinking", "speaking", "acting"]);

/** Beat kinds whose prose the player can rewrite. A picture and a set of choices
 *  have no words of their own to edit. */
const EDITABLE_BEATS = new Set(["narrator", "char", "player"]);

/** Beat kinds the engine can generate again. The player's own line is not one —
 *  re-rolling it would mean the model writing what the player said. */
const RERUNNABLE_BEATS = new Set(["narrator", "char"]);

export function StoryPlayerView({
  scenario,
  statDefs = [],
  storylineName,
  contextDocs = [],
  storylineCast = [],
  settingCount = 1,
  backHref = "/",
}: {
  scenario: ResolvedScenario;
  statDefs?: StatDefinition[];
  storylineName?: string;
  /** Every character in the storyline — the rail's "Elsewhere in the world" offers the
   *  ones this scene never cast. */
  storylineCast?: Character[];
  /** How many places the storyline has — "Move the scene" needs somewhere to go. */
  settingCount?: number;
  /** The storyline's context documents — the rows the composer's `@` menu offers. */
  contextDocs?: ContextDocumentIndexEntry[];
  backHref?: string;
}) {
  const scene = useScenePlay(scenario, contextDocs);
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
  // The beat currently open in the inline editor (its event id), or null.
  const [editingId, setEditingId] = useState<string | null>(null);
  // The transcript scene image currently enlarged (null = the lightbox is closed).
  const [lightbox, setLightbox] = useState<SceneImage | null>(null);
  /** "Someone arrives" is open, listing who could actually walk in. */
  const [castMenuOpen, setCastMenuOpen] = useState(false);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  /** The player-facing "what the scene knows" rail. Mutually exclusive with the Inspector —
   *  two 340px columns cannot both dock, and they answer different questions anyway. */
  const [memoryOpen, setMemoryOpen] = useState(false);
  // Whether the model behind the scene is actually there. Polled while the tab is visible,
  // and re-checked the moment a turn fails — which is when the player most needs to know
  // whether the failure was their endpoint rather than the story.
  const { health, recheck: recheckHealth } = useModelHealth();
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

  // People in the world who are not in this scene — what "Someone arrives" needs to mean
  // anything, and the same list the rail's "Elsewhere in the World" offers.
  const absentCast = useMemo(() => {
    const inScene = new Set(scenario.cast.map((c) => c.id));
    return storylineCast
      .filter((c) => !inScene.has(c.id))
      .map((c) => ({ id: c.id, name: c.name }));
  }, [storylineCast, scenario.cast]);

  /**
   * Where the memory edge goes: immediately above the oldest beat the cast still reads.
   *
   * Accurate to within a beat or two — transcript messages and buffer beats are not exactly
   * 1:1, since an internal thought folds into its speaker's beat. That is enough for the
   * marker's job (telling the player there IS an edge, and roughly where); the memory panel
   * carries the exact figures, read from the engine rather than counted here. `-1` hides it.
   */
  // A turn just failed. Re-check the endpoint now rather than waiting out the poll: this is
  // the exact moment "was that my model?" is worth answering, and the answer decides whether
  // the player retries or goes to Options. Derived-from-a-changed-value, not an effect.
  const [seenError, setSeenError] = useState<string | null>(null);
  if (scene.streamError && scene.streamError !== seenError) {
    setSeenError(scene.streamError);
    recheckHealth();
  } else if (!scene.streamError && seenError !== null) {
    setSeenError(null);
  }

  /** The shortcut sheet, behind `?`. */
  const [helpOpen, setHelpOpen] = useState(false);

  // Destructured before the memo so its dependencies are plain values rather than the whole
  // `scene` object, which is rebuilt every render and would defeat the memo entirely.
  const { recallLast, openProfile, profileId } = scene;

  useSceneShortcuts(
    useMemo(
      () => ({
        focusComposer: () => composerRef.current?.focus(),
        recallLast,
        // Ordered: the most transient thing first. Escape should close what the player most
        // recently opened, and this is the only place that knows what is layered.
        closeTopmost: () => {
          if (helpOpen) return setHelpOpen(false), true;
          if (lightbox) return setLightbox(null), true;
          if (editingId) return setEditingId(null), true;
          if (modalId) return setModalId(null), true;
          if (memoryOpen) return setMemoryOpen(false), true;
          if (inspectorOpen) return setInspectorOpen(false), true;
          if (profileId) return openProfile(null), true;
          return false;
        },
        toggleHelp: () => setHelpOpen((o) => !o),
      }),
      [
        helpOpen,
        lightbox,
        editingId,
        modalId,
        memoryOpen,
        inspectorOpen,
        profileId,
        recallLast,
        openProfile,
      ],
    ),
  );

  const memoryEdgeAt =
    scene.sceneMemory && scene.sceneMemory.droppedBeats > 0
      ? Math.max(0, scene.messages.length - scene.sceneMemory.windowBeats)
      : -1;

  const verbs = useMemo(
    () =>
      availableVerbs(
        {
          absentCast,
          settingCount: settingCount ?? 1,
          playerTurns: scene.playerTurns,
        },
        scenario.directionVerbs ?? [],
      ),
    [absentCast, settingCount, scene.playerTurns, scenario.directionVerbs],
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
        onToggleInspector={
          viewMode === "graph"
            ? undefined
            : () => {
                setInspectorOpen((o) => !o);
                setMemoryOpen(false);
              }
        }
        inspectorOpen={inspectorOpen}
        onToggleMemory={
          viewMode === "graph"
            ? undefined
            : () => {
                setMemoryOpen((o) => !o);
                setInspectorOpen(false);
              }
        }
        memoryOpen={memoryOpen}
        health={health}
        tray={
          <PlaythroughTray
            sessions={scene.sessions}
            currentSessionId={scene.sessionId}
            onOpen={(id) => void scene.openSession(id)}
            onCreate={() => void scene.startNewPlaythrough()}
            onRename={(id, name) => void scene.renamePlaythrough(id, name)}
            onDelete={(id) => void scene.deletePlaythrough(id)}
            // Switching stories mid-sentence would leave a half-streamed beat attached to a
            // play-through that is no longer on screen.
            disabled={scene.sending}
          />
        }
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
          storylineCast={storylineCast}
          joinDisabled={!scene.sessionId}
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
                <Fragment key={i}>
                {/* The line where verbatim memory stops. Rendered positionally rather than
                    injected into `scene.messages`, so it costs no state churn and cannot end
                    up in an export or a rewind's beat count. */}
                {memoryEdgeAt === i ? (
                  <MemoryEdge
                    droppedBeats={scene.sceneMemory?.droppedBeats ?? 0}
                    summarised={Boolean(scene.summaryThroughSeq)}
                  />
                ) : null}
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={ENTER_TRANSITION}
                  // `group relative` anchors the per-beat controls, which stay at opacity 0
                  // until this beat is hovered or contains focus.
                  // The beat currently being written gets a couple of lines of
                  // reserved height, so the composer does not hop the instant
                  // the first token lands and again as the line wraps.
                  className={`group relative${
                    scene.sending && i === scene.messages.length - 1 ? " min-h-[3.2em]" : ""
                  }`}
                >
                  {/* Only for beats that are actually persisted: a `choices` row and the
                      optimistic bubble of an in-flight turn have no row to point at. */}
                  {m.id && !scene.sending ? (
                    <span className="absolute -top-[10px] right-0 z-10">
                      <BeatControls
                        label={beatLabel(m, byId)}
                        rewindBeatCount={scene.messages.length - turnStartIndex(scene.messages, i)}
                        onEdit={EDITABLE_BEATS.has(m.kind) ? () => setEditingId(m.id!) : undefined}
                        onReroll={
                          // Never the player's own words — including a POV beat, which wears
                          // a character's identity but was written by the player.
                          RERUNNABLE_BEATS.has(m.kind) && !m.fromPlayer
                            ? (scope) => scene.rerollBeat(m.id!, scope)
                            : undefined
                        }
                        onBranch={() => void scene.branchFrom(m.id!)}
                        onRewind={() => void scene.rewindTo(m.id!)}
                        disabled={scene.sending}
                      />
                    </span>
                  ) : null}
                  {/* Only on a beat that has been re-rolled — one version is not a choice. */}
                  {m.takes && m.id ? (
                    <span className="absolute -bottom-[8px] right-0 z-10">
                      <BeatTakePager
                        count={m.takes.count}
                        active={m.takes.active}
                        label={beatLabel(m, byId)}
                        onSelect={(take) => void scene.selectTake(m.id!, take)}
                        disabled={scene.sending}
                      />
                    </span>
                  ) : null}
                  {editingId && editingId === m.id ? (
                    <BeatEditor
                      initialText={m.text ?? ""}
                      label={beatLabel(m, byId)}
                      onSave={(text) => {
                        void scene.editBeatText(m.id!, text);
                        setEditingId(null);
                      }}
                      onCancel={() => setEditingId(null)}
                    />
                  ) : (
                  <TranscriptBeat
                    message={m}
                    charById={byId}
                    onProfile={scene.openProfile}
                    choices={scene.choices}
                    onChoose={onChoose}
                    onOpenImage={setLightbox}
                    streaming={scene.sending && i === scene.messages.length - 1}
                    reasoningByChar={scene.reasoningByChar}
                    docNameOf={(id) => contextDocs.find((d) => d.id === id)?.name}
                    onCastAccept={(id) => scene.answerCastRequest(id, true)}
                    onCastDecline={(id) => scene.answerCastRequest(id, false)}
                    onPlayOut={scene.playOut}
                    // Without a session there is nothing to attach a presence change to, and
                    // mid-turn the roster is already in flight.
                    castRequestDisabled={!scene.sessionId || scene.sending}
                    turnInFlight={scene.sending}
                  />
                  )}
                </motion.div>
                </Fragment>
              ))}
              {/* What the turn is doing, while it is being written. Sits in the same slot
                  the CreateImageBar occupies between turns (the two are gated on `sending`
                  in opposite directions), so the foot of the transcript never empties out.

                  Once a speaker has been chosen, their own beat is already open above with
                  a typing indicator in it, so the strip stands down to avoid saying the
                  same thing twice. It keeps the pre-generation phases — gathering, reading,
                  planning — which no beat can show, because no beat exists yet. */}
              {/* A rewind removes half the page; without this it reads as a bug. Announced,
                  because the visual change is the only other signal and a non-sighted
                  reader cannot receive it. */}
              {scene.rewound ? (
                <RewindNotice
                  removedEvents={scene.rewound.removedEvents}
                  onUndo={
                    scene.rewound.snapshotSessionId
                      ? () => {
                          const id = scene.rewound?.snapshotSessionId;
                          if (id) void scene.openSession(id);
                          scene.clearRewound();
                        }
                      : undefined
                  }
                  onDismiss={scene.clearRewound}
                />
              ) : null}
              <TurnStatusStrip
                status={scene.turnStatus}
                streaming={scene.sending && !CHARACTER_PHASES.has(scene.turnStatus.phase)}
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
                  <TranscriptFootBar
                    onContinue={scene.continueTurn}
                    continuing={scene.sending}
                    onCreateImage={scene.createImage}
                    creatingImage={scene.creatingImage}
                    imageStage={scene.imageStage}
                    imageError={scene.imageError}
                    disabled={scene.sending}
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
            // Cast + context files in one `@` namespace, built by the hook because who is
            // present is its own state.
            mentionOptions={scene.mentionOptions}
            verbs={verbs}
            /* "Someone arrives" does not insert a phrasing — it names the people who could
               actually walk in, and choosing one raises a request the player still approves. */
            onExpandCast={() => setCastMenuOpen((open) => !open)}
            castMenu={
              castMenuOpen && absentCast.length ? (
                <ul
                  aria-label="Who arrives"
                  className="mytheca-menu absolute bottom-full left-0 z-40 mb-[6px] flex max-h-[240px] w-full max-w-[260px] flex-col gap-[2px] overflow-auto p-[6px]"
                >
                  {absentCast.map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => {
                          setCastMenuOpen(false);
                          // A name, not an arrival: this writes a direction the engine turns
                          // into a request the player still has to approve.
                          scene.setGuidance(
                            (scene.guidance ? `${scene.guidance.trimEnd()}\n` : "") +
                              `${c.name} arrives.`,
                          );
                        }}
                        className="w-full rounded-[3px] px-[8px] py-[6px] text-left font-display text-[13px] text-ink hover:bg-hover"
                      >
                        {c.name}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null
            }
            value={scene.composer}
            onChange={scene.setComposer}
            onSend={scene.send}
            sendDisabled={scene.sending}
            inputRef={composerRef}
            maxTurns={scene.maxTurns}
            onMaxTurnsChange={scene.setMaxTurns}
            suggestionsCount={scene.suggestionsCount}
            onSuggestionsCountChange={scene.setSuggestionsCount}
            beatLength={scene.beatLength}
            onBeatLengthChange={scene.setBeatLength}
            sceneMemory={scene.sceneMemory}
            summarised={Boolean(scene.summaryThroughSeq)}
            guidance={scene.guidance}
            onGuidanceChange={scene.setGuidance}
            pov={scene.pov}
            onPovChange={scene.setPov}
            povOptions={povOptions}
            usedTokens={scene.usedTokens}
            maxContextTokens={scene.maxContextTokens}
            usedTokensExact={scene.usedTokensExact}
            onGhostwrite={scene.ghostwrite}
            onUndoGhostwrite={scene.undoGhostwrite}
            ghostwriting={scene.ghostwriting}
            canUndoGhostwrite={scene.canUndoGhostwrite}
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
            direction={scene.direction}
            standing={scene.standing}
            onDismissStanding={scene.dismissStanding}
          />
        )}

        {/* Docked to the far right of the Director rail — the chat stays visible. */}
        <TurnInspectorPanel
          open={inspectorOpen}
          onClose={() => setInspectorOpen(false)}
          turns={scene.traceTurns}
        />
        <ShortcutSheet open={helpOpen} onClose={() => setHelpOpen(false)} />
        <SceneMemoryPanel
          open={memoryOpen}
          onClose={() => setMemoryOpen(false)}
          scenarioId={scenario.id}
          sessionId={scene.sessionId}
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
