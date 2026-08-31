"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ENTER_TRANSITION } from "@/lib/motion";
import { exportSessionUrl, updateScenario } from "@/lib/api";
import type {
  Character,
  ContextDocumentIndexEntry,
  ResolvedScenario,
  StatDefinition,
} from "@/lib/types";
import type { ExportFormat } from "@/components/feature/SceneMenu";
import { useScenePlay } from "./useScenePlay";
import { availableVerbs } from "@/lib/sceneVerbs";
import { useModelHealth } from "@/hooks/use-model-health";
import { useSceneShortcuts } from "@/hooks/use-scene-shortcuts";
import { TranscriptSearch } from "@/components/feature/TranscriptSearch";
import { matchBeats, stepMatch } from "./transcript-search";
import { ShortcutSheet } from "@/components/feature/ShortcutSheet";
import { CoachMark } from "@/components/feature/CoachMark";
import { useCoachMarks } from "@/hooks/use-coach-marks";
import { useMediaQuery } from "@/hooks/use-media-query";
import { COACH_MARKS, type CoachMarkId } from "@/lib/coachMarks";
import type { SceneImage, SceneMessage } from "./scene-data";
import { SceneHeader, type SceneViewMode } from "@/components/layout/SceneHeader";
import { PromptOverridesModal } from "@/components/feature/PromptOverridesModal";
import { StyleGuideModal } from "@/components/feature/StyleGuideModal";
import { CastRail, CastRailContent, type CastRailProps } from "@/components/feature/CastRail";
import {
  PlaythroughTray,
  PlaythroughTrayContent,
} from "@/components/feature/PlaythroughTray";
import { BeatControls } from "@/components/feature/BeatControls";
import { BeatEditor } from "@/components/feature/BeatEditor";
import { BeatTakePager } from "@/components/feature/BeatTakePager";
import { RewindNotice } from "@/components/feature/RewindNotice";
import { GraphView } from "@/components/feature/GraphView";
import { DirectorRail, DirectorRailContent, type DirectorRailProps } from "@/components/feature/DirectorRail";
import { SceneRailBar, type RailTrigger } from "@/components/feature/SceneRailBar";
import { Drawer } from "@/components/ui/Drawer";
import { Composer } from "@/components/feature/Composer";
import { PlanApproval } from "@/components/feature/PlanApproval";
import { SceneLoader } from "@/components/feature/SceneLoader";
import { SceneIntro } from "@/components/feature/SceneIntro";
import { TranscriptBeat } from "@/components/feature/TranscriptBeat";
import { TranscriptAnnouncer } from "@/components/feature/TranscriptAnnouncer";
import { TurnStatusStrip } from "@/components/feature/TurnStatusStrip";
import { JumpToLatest } from "@/components/feature/JumpToLatest";
import { useStickyBottom } from "./use-sticky-bottom";
import { TranscriptFootBar } from "@/components/feature/TranscriptFootBar";
import { SceneImageModal } from "@/components/feature/SceneImageModal";
import {
  CharacterDossier,
  CharacterDossierContent,
  type CharacterDossierProps,
} from "@/components/feature/CharacterDossier";
import { CharacterProfileModal } from "@/components/feature/CharacterProfileModal";
import { TurnInspectorPanel } from "@/components/feature/TurnInspectorPanel";
import { SceneMemoryPanel } from "@/components/feature/SceneMemoryPanel";
import { MemoryEdge } from "@/components/feature/MemoryEdge";
import { useShortcutsEnabled } from "@/hooks/use-shortcuts-enabled";


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

/**
 * Whose words the player may rewrite: **their own, and only their own.**
 *
 * A plain `player` beat, or a `char` beat they authored under POV — that one wears a
 * character's name but the player wrote it, which is why it is matched on `fromPlayer`
 * rather than on `kind`.
 *
 * Narration and the cast's lines are deliberately excluded. Rewriting the model's prose
 * puts words in a character's mouth that their own interior state was never conditioned
 * on, and the record already has the right answer to "I don't like that line": **Re-roll**
 * regenerates it in place and keeps the previous wording as a take. `PATCH …/beats/{id}`
 * still accepts any beat with prose — this is the surface gate, not an API change.
 */
export function isPlayerAuthored(m: SceneMessage): boolean {
  return m.kind === "player" || (m.kind === "char" && Boolean(m.fromPlayer));
}

/** Beat kinds the engine can generate again. The player's own line is not one —
 *  re-rolling it would mean the model writing what the player said. */
const RERUNNABLE_BEATS = new Set(["narrator", "char"]);

export function StoryPlayerView({
  scenario,
  statDefs = [],
  storylineName,
  storylinePromptOverrides,
  storylineStyleBlocks,
  contextDocs = [],
  storylineCast = [],
  settingCount = 1,
  backHref = "/",
}: {
  scenario: ResolvedScenario;
  statDefs?: StatDefinition[];
  storylineName?: string;
  /**
   * The storyline's writing-prompt overrides — the one layer the prompt modal cannot fetch
   * for itself. Without it the modal renders no origin badges at all, which is honest.
   */
  storylinePromptOverrides?: Record<string, string>;
  storylineStyleBlocks?: Record<string, string>;
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
  // "How this world writes" — the prompt overrides, reachable from the scene rather than
  // two navigations away from the only place their effect is observable.
  const [writingOpen, setWritingOpen] = useState(false);
  // The scenario layer, held locally so a save takes effect on the NEXT turn without a
  // reload — `scenario` is a prop and the turn request reads the resolved text server-side.
  const [scenePrompts, setScenePrompts] = useState<Record<string, string>>(
    scenario.promptOverrides ?? {},
  );
  // "Style…" — how THIS scene is written, where it differs from the world's guide. Held
  // locally for the same reason as the prompts above: a save has to reach the next turn
  // without a reload.
  const [styleOpen, setStyleOpen] = useState(false);
  const [sceneStyle, setSceneStyle] = useState<Record<string, string>>(
    scenario.styleBlocks ?? {},
  );
  /** The player-facing "what the scene knows" rail. Mutually exclusive with the Inspector —
   *  two 340px columns cannot both dock, and they answer different questions anyway. */
  const [memoryOpen, setMemoryOpen] = useState(false);
  /**
   * Which rail is open as a bottom sheet. Read through `openSheet` below, never directly:
   * above `lg` both rails are already on screen and a sheet would be a second copy of the
   * same landmark, so the width closes it — derived, not an effect that writes state back.
   */
  const [railDrawer, setRailDrawer] = useState<"cast" | "scene" | null>(null);
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

  // Find-in-scene. Client-side: the whole transcript is already in memory after rehydration,
  // so a round-trip would be slower AND would stop working without a substrate.
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [matchIndex, setMatchIndex] = useState(0);
  const matches = useMemo(
    () => (searchOpen ? matchBeats(scene.messages, query) : []),
    [searchOpen, scene.messages, query],
  );
  const matchTotal = matches.length;
  // Clamped during render rather than corrected in an effect: editing the query shortens the
  // list under a stale index, and an effect would render one frame pointing past the end.
  const activeMatch = matchTotal ? Math.min(matchIndex, matchTotal - 1) : 0;
  const highlighted = matchTotal ? matches[activeMatch].index : -1;

  // Every hint can now be shown at every width. The cast-rail one used to be suppressed below
  // `lg` because it pointed at a rail that did not exist there; it now points at the Cast
  // trigger in the rail bar, which does.
  const wide = useMediaQuery("(min-width: 1024px)");
  const availableMarks = useMemo<CoachMarkId[]>(
    () => ["composer", "pov", "cast-rail"],
    [],
  );
  const { mark, dismiss } = useCoachMarks(availableMarks);

  // Destructured before the memo so its dependencies are plain values rather than the whole
  // `scene` object, which is rebuilt every render and would defeat the memo entirely.
  const { recallLast, openProfile, profileId } = scene;

  /**
   * Opening a profile, from wherever. Below `lg` the dossier lives in the scene sheet, so
   * selecting a character has to raise that sheet — otherwise a tap on a cast member sets
   * state that nothing on screen renders, and reads as the app ignoring the tap.
   *
   * Routed here rather than folded into `useScenePlay.openProfile` so the hook's surface
   * stays the same for the other plans that consume it.
   */
  // Crossing into `lg` closes any open sheet, by *clearing the state* rather than by masking
  // it behind a derived value. Both were tried; masking is wrong, and observably so — the
  // stale "cast" survives the widen, so narrowing back pops a modal dialog open that nobody
  // asked for and moves focus into it. Adjusting state during render is React's own answer
  // to "reset state when an external value changes": no effect, no second commit.
  const [wasWide, setWasWide] = useState(wide);
  if (wide !== wasWide) {
    setWasWide(wide);
    if (wide && railDrawer) setRailDrawer(null);
  }
  const openSheet = wide ? null : railDrawer;

  const showProfile = useCallback(
    (id: string | null) => {
      openProfile(id);
      if (id && !wide) setRailDrawer("scene");
    },
    [openProfile, wide],
  );

  /**
   * The rails' props, built once and spread into BOTH the `lg` rail and the bottom sheet.
   *
   * Not "the same props" by hand — the same object. That is what makes "identical
   * functionality at every width" a fact about the code rather than a promise: a prop added
   * to a rail reaches the phone in the same edit, and there is no second call site to forget.
   */
  const castRailProps: CastRailProps = {
    cast: scenario.cast,
    speakingId: scene.speakingId,
    turnOrder: scene.turnOrder,
    charById: byId,
    onProfile: (id) => {
      if (mark === "cast-rail") dismiss("cast-rail");
      showProfile(id);
    },
    presenceByChar: scene.presenceByChar,
    setPresence: scene.setPresence,
    statDefs,
    statsByChar: scene.statsByChar,
    activityByChar: scene.activityByChar,
    storylineCast,
    joinDisabled: !scene.sessionId,
  };

  const directorRailProps: DirectorRailProps = {
    stats: scene.stats,
    activity: scene.activity,
    charById: byId,
    direction: scene.direction,
    standing: scene.standing,
    onDismissStanding: scene.dismissStanding,
    tasks: scene.tasks,
  };

  const dossierProps: CharacterDossierProps | null = profileChar
    ? {
        character: profileChar,
        statDefs,
        stats: scene.statsByChar[profileChar.id],
        relationships: scene.relationships,
        onClose: scene.closeProfile,
        onOpenProfile: setModalId,
      }
    : null;

  // What the Scene trigger advertises: outcomes this turn still owes, plus anything an
  // earlier turn could not deliver. Zero shows no badge at all.
  const sceneOwed =
    scene.direction.items.filter((i) => i.state !== "delivered").length + scene.standing.length;

  const railTriggers: RailTrigger[] = [
    {
      key: "cast",
      label: "Cast",
      count: castRailProps.cast.filter(
        (c) => (scene.presenceByChar[c.id] ?? "present") === "present",
      ).length,
      countLabel: (n) => `${n} in the scene`,
      open: openSheet === "cast",
      onSelect: () => setRailDrawer((open) => (open === "cast" ? null : "cast")),
    },
    {
      key: "scene",
      label: "Scene",
      count: sceneOwed,
      countLabel: (n) => `${n} still owed`,
      urgent: true,
      open: openSheet === "scene",
      onSelect: () => setRailDrawer((open) => (open === "scene" ? null : "scene")),
    },
    {
      // The memory panel is NOT wrapped in a sheet: it already takes the full width below
      // `sm` and brings its own `<aside>` and close button, so a dialog around it would nest
      // a landmark inside a dialog and give it two ways out. What it lacked was a reachable
      // trigger below `lg`, which is this.
      key: "knows",
      label: "Knows",
      dialog: false,
      open: memoryOpen,
      onSelect: () => setMemoryOpen((open) => !open),
    },
  ];

  // WCAG 2.1.4: `/` and `?` are single-character shortcuts, so there has to be a way to turn
  // them off. Standing down inside text fields — which this hook already did — is necessary
  // but is none of the three things the criterion accepts.
  const shortcutsEnabled = useShortcutsEnabled();

  useSceneShortcuts(
    useMemo(
      () => ({
        focusComposer: () => composerRef.current?.focus(),
        recallLast,
        // Ordered: the most transient thing first. Escape should close what the player most
        // recently opened, and this is the only place that knows what is layered.
        closeTopmost: () => {
          if (helpOpen) return setHelpOpen(false), true;
          if (searchOpen) return setSearchOpen(false), true;
          if (lightbox) return setLightbox(null), true;
          if (editingId) return setEditingId(null), true;
          if (modalId) return setModalId(null), true;
          if (memoryOpen) return setMemoryOpen(false), true;
          if (inspectorOpen) return setInspectorOpen(false), true;
          // The sheet before the profile behind it: closing the dossier under an open sheet
          // would leave an empty sheet on screen.
          if (openSheet) return setRailDrawer(null), true;
          if (profileId) return openProfile(null), true;
          return false;
        },
        toggleHelp: () => setHelpOpen((o) => !o),
      }),
      [
        helpOpen,
        searchOpen,
        lightbox,
        editingId,
        modalId,
        memoryOpen,
        inspectorOpen,
        openSheet,
        profileId,
        recallLast,
        openProfile,
      ],
    ),
    shortcutsEnabled,
  );

  // `Cmd/Ctrl+F` opens find-in-scene — but ONLY when the player is not writing. Someone
  // mid-sentence reaching for find-in-page means the browser's, and stealing it there is the
  // same failure as a shortcut eating a keystroke.
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "f" || !(e.metaKey || e.ctrlKey)) return;
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName?.toLowerCase();
      if (tag === "textarea" || tag === "input" || el?.isContentEditable) return;
      e.preventDefault();
      setSearchOpen(true);
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

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
        onOpenWriting={() => setWritingOpen(true)}
        onOpenStyle={() => setStyleOpen(true)}
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
        // The same tray without its popover, for the narrow header — where it drills down
        // inside the scene menu instead of opening a second popover beside it.
        trayPanel={
          <PlaythroughTrayContent
            sessions={scene.sessions}
            currentSessionId={scene.sessionId}
            onOpen={(id) => void scene.openSession(id)}
            onCreate={() => void scene.startNewPlaythrough()}
            onRename={(id, name) => void scene.renamePlaythrough(id, name)}
            onDelete={(id) => void scene.deletePlaythrough(id)}
            onDone={() => undefined}
          />
        }
        onOpenShortcuts={() => setHelpOpen(true)}
      />

      <div className="relative flex min-h-0 flex-1">
        {/* In graph mode below `lg` there is no rail bar and no rail — the one case where
            this hint still has nothing to point at. */}
        {mark === "cast-rail" && (wide || viewMode === "chat") ? (
          <CoachMark
            text={COACH_MARKS["cast-rail"]}
            onDismiss={() => dismiss("cast-rail")}
            className="absolute bottom-3xl left-[16px] lg:top-3xl lg:bottom-auto"
          />
        ) : null}
        <CastRail {...castRailProps} />

        {viewMode === "graph" ? (
          <GraphView scenarioId={scenario.id} />
        ) : (
        <>
        {/* The reading column IS the page's main region. It had no landmark at all: a
            screen-reader user could reach both rails by name and had no way to jump to the
            transcript between them. */}
        <main id="main" tabIndex={-1} className="relative flex min-w-0 flex-1 flex-col">
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
              <SceneIntro scenario={scenario} onProfile={showProfile} />
              <div className="py-3xs text-center font-mono text-eyebrow tracking-[0.16em] text-mute2 uppercase">
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
                  // Marked rather than tinted: `aria-current` carries the "this is the one
                  // you are on" to a screen reader, which a highlight colour cannot.
                  aria-current={highlighted === i ? "true" : undefined}
                  ref={
                    highlighted === i
                      ? (el) => el?.scrollIntoView({ block: "center", behavior: "smooth" })
                      : undefined
                  }
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={ENTER_TRANSITION}
                  // `group relative` anchors the per-beat controls, which stay at opacity 0
                  // until this beat is hovered or contains focus.
                  // The beat currently being written gets a couple of lines of
                  // reserved height, so the composer does not hop the instant
                  // the first token lands and again as the line wraps.
                  className={`${highlighted === i ? "rounded-sm ring-2 ring-accent" : ""} group relative${
                    scene.sending && i === scene.messages.length - 1 ? " min-h-[3.2em]" : ""
                  }`}
                >
                  {/* Only for beats that are actually persisted: a `choices` row and the
                      optimistic bubble of an in-flight turn have no row to point at. */}
                  {m.id && !scene.sending ? (
                    <span className="absolute -top-sm right-0 z-10">
                      <BeatControls
                        label={beatLabel(m, byId)}
                        rewindBeatCount={scene.messages.length - turnStartIndex(scene.messages, i)}
                        // A rewind takes the containing turn AND everything after it, so
                        // from the first turn that is the whole scene. Same confirmation
                        // copy for both read as "Rewind to Here deleted the whole thread".
                        rewindEmptiesScene={turnStartIndex(scene.messages, i) === 0}
                        onEdit={isPlayerAuthored(m) ? () => setEditingId(m.id!) : undefined}
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
                    <span className="absolute -bottom-sm right-0 z-10">
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
                    onProfile={showProfile}
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
                <p role="alert" className="text-center font-mono text-eyebrow tracking-[0.08em] text-danger-ink">
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
                    onCreateImage={(artStyle) => scene.createImage(undefined, undefined, artStyle)}
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

          {searchOpen ? (
            <div className="flex-none px-lg pt-sm sm:px-2xl">
              <TranscriptSearch
                query={query}
                onQueryChange={(next) => {
                  setQuery(next);
                  setMatchIndex(0);
                }}
                current={activeMatch}
                total={matchTotal}
                onStep={(delta) => setMatchIndex((i) => stepMatch(i, matchTotal, delta))}
                onClose={() => {
                  setSearchOpen(false);
                  setQuery("");
                }}
              />
            </div>
          ) : null}

          {/* Only while the reader has scrolled away from the live edge. */}
          {readerScrolledUp ? (
            <JumpToLatest onClick={jumpToLatest} className="bottom-3xl lg:bottom-3xl" />
          ) : null}

          {/* Anchored above the composer band, one at a time. No overlay and no backdrop:
              the scene stays fully usable, and a player who ignores these is never blocked. */}
          {mark === "composer" || mark === "pov" ? (
            <CoachMark
              text={COACH_MARKS[mark]}
              onDismiss={() => dismiss(mark)}
              className="absolute right-[16px] bottom-3xl left-auto sm:right-[30px] lg:bottom-3xl"
            />
          ) : null}

          {/* Below `lg` this row is the ONLY way to the rails — the cast list with its
              presence controls and stat values, the scene pulse, the scene state, the
              direction checklist. It sits above the composer rather than in the header
              because that is where a thumb already is. */}
          <SceneRailBar triggers={railTriggers} />

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
                  className="mytheca-menu absolute bottom-full left-0 z-40 mb-xs flex max-h-[240px] w-full max-w-[260px] flex-col gap-3xs overflow-auto p-xs"
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
                        className="w-full rounded-xs px-sm py-xs text-left font-display text-label text-ink hover:bg-hover"
                      >
                        {c.name}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null
            }
            value={scene.composer}
            onChange={(v) => {
              // Acting on the thing a hint points at IS dismissing it. Anything that can only
              // be dismissed by its × eventually traps someone.
              if (mark === "composer") dismiss("composer");
              scene.setComposer(v);
            }}
            onSend={scene.send}
            sendDisabled={scene.sending}
            inputRef={composerRef}
            // `effective`, not the scene's own values: an unpinned control shows what the
            // player picked for the next message, even though nothing was written anywhere.
            suggestionsCount={scene.effective.suggestionsCount}
            onSuggestionsCountChange={scene.setSuggestionsCount}
            plannerMode={scene.effective.planner}
            onPlannerModeChange={scene.setPlannerMode}
            register={scene.register}
            onRegisterChange={scene.setRegister}
            sceneFlow={scene.effective.sceneFlow}
            onSceneFlowChange={scene.setSceneFlow}
            sceneMode={scene.effective.sceneMode}
            onSceneModeChange={scene.setSceneMode}
            thinking={scene.thinking}
            onThinkingChange={scene.setThinking}
            tieScope={scene.effective.ties}
            onTieScopeChange={scene.setTieScope}
            graphAvailable={scene.graphAvailable}
            pinned={scene.pinned}
            onPinnedChange={scene.setPinned}
            sceneMemory={scene.sceneMemory}
            summarised={Boolean(scene.summaryThroughSeq)}
            guidance={scene.guidance}
            onGuidanceChange={scene.setGuidance}
            pov={scene.pov}
            onPovChange={(id) => {
              if (mark === "pov") dismiss("pov");
              scene.setPov(id);
            }}
            povOptions={povOptions}
            usedTokens={scene.usedTokens}
            maxContextTokens={scene.maxContextTokens}
            usedTokensExact={scene.usedTokensExact}
            onGhostwrite={scene.ghostwrite}
            onUndoGhostwrite={scene.undoGhostwrite}
            ghostwriting={scene.ghostwriting}
            canUndoGhostwrite={scene.canUndoGhostwrite}
          />
        </main>

        {dossierProps ? (
          <CharacterDossier {...dossierProps} />
        ) : (
          <DirectorRail {...directorRailProps} />
        )}

        {/* The same rails again, as bottom sheets. `railDrawer` is forced to null above `lg`
            (see the effect), so only one of the two surfaces is ever in the tree. */}
        <Drawer
          open={openSheet === "cast"}
          onClose={() => setRailDrawer(null)}
          title="Cast"
        >
          <CastRailContent {...castRailProps} />
        </Drawer>
        <Drawer
          open={openSheet === "scene"}
          onClose={() => setRailDrawer(null)}
          title={dossierProps ? `${dossierProps.character.name} — profile` : "Scene"}
        >
          {dossierProps ? (
            <CharacterDossierContent {...dossierProps} />
          ) : (
            // `live={false}`: this mounts when the sheet opens, and a log that reads out the
            // whole turn the instant it appears talks over everything else.
            <DirectorRailContent {...directorRailProps} live={false} />
          )}
        </Drawer>

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
      <SceneImageModal
        image={lightbox}
        onClose={() => setLightbox(null)}
        // Additive only: this paints a NEW beat from the player's wording. Removing or
        // replacing a picture is a different, destructive path and is not wired here.
        onRepaint={
          scene.sessionId
            ? (prompt, artStyle) => {
                scene.createImage(prompt, undefined, artStyle);
                setLightbox(null);
              }
            : undefined
        }
        busy={scene.creatingImage}
      />
      <PromptOverridesModal
        open={writingOpen}
        onClose={() => setWritingOpen(false)}
        heading="How this world writes"
        subtitle="These are the instructions the narrator and the cast are given. Changes here apply to this scene only — clear a field to fall back to the world's version."
        overrides={scenePrompts}
        // The layer below this one, so "Reset to default" reverts to what the scene would
        // inherit rather than to the shipped text.
        baseline={storylinePromptOverrides}
        storylineOverrides={storylinePromptOverrides ?? null}
        saveLabel="Save for this scene"
        onSave={async (map) => {
          await updateScenario(scenario.id, { promptOverrides: map });
          // Local, so the next turn resolves the new text without a reload.
          setScenePrompts(map);
        }}
      />
      <StyleGuideModal
        open={styleOpen}
        onClose={() => setStyleOpen(false)}
        heading="How this scene is written"
        subtitle="The world's style guide, overridden for this scene only. Leave a field empty to keep the world's."
        blocks={sceneStyle}
        // The layer below, so an empty field shows what it would inherit rather than
        // reading as "nothing is said about this".
        inherited={storylineStyleBlocks}
        layer="scenario"
        saveLabel="Save for this scene"
        onSave={async (next) => {
          await updateScenario(scenario.id, { styleBlocks: next });
          setSceneStyle(next);
        }}
      />
    </div>
  );
}
