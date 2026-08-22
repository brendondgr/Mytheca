"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  closePlaySession,
  getCharacterStats,
  getLlmContextWindow,
  getScenarioRelationships,
  postGhostwrite,
  postSceneMoment,
  clearStandingDirection,
  postTurn,
  rerollBeat as apiRerollBeat,
  selectBeatTake,
  setPresence as apiSetPresence,
  updateScenario,
} from "@/lib/api";
import { estimateUsedTokens } from "@/lib/contextBudget";
import type {
  GhostwriteStreamFrame,
  MomentStreamFrame,
  PresenceStatus,
  TurnStreamFrame,
  StandingItem,
} from "@/lib/events";
import type { BeatLength, ResolvedScenario } from "@/lib/types";
import { useEventStream } from "@/hooks/use-event-stream";
import {
  splitDirectives,
  stripMentions,
  type Directive,
  type MentionOption,
} from "@/features/story-player/mentions";
import { useSessionRecord } from "./useSessionRecord";
import { mostRecent } from "./playthroughs";
import { useToast } from "@/components/layout/ToastProvider";
import {
  buildScene,
  type Relationship,
  type SceneChoice,
  type SceneMessage,
  type StatChip,
} from "./scene-data";
import {
  NO_DIRECTION,
  applyActivity,
  applyDirection,
  latestSceneMemory,
  type SceneMemory,
  dropPendingBeats,
  applyReasoning,
  applyCharacterActivity,
  applyTurnStatus,
  type ActivityEntry,
  type CharacterActivity,
  IDLE_TURN_STATUS,
  type TurnStatus,
  applyPresence,
  applyStatByChar,
  applyStatUpdate,
  baselineStatsByChar,
  branchOptionsToChoices,
  foldTrace,
  graphRelationshipsToRel,
  mergeFrame,
  type PresenceMap,
  sessionIdOf,
  type DirectionProgress,
  type TraceTurn,
} from "./turn-stream";

/**
 * How long the establishing curtain (`SceneLoader`) must be up before it may
 * dissolve, even if the scene is ready sooner.
 *
 * The curtain is the app's one deliberate motion moment and it carries real
 * information — the scenario, its setting, the cast, the goal. Flashing it for
 * 80ms and snatching it away reads as a glitch, not as speed.
 */
const SCENE_REVEAL_MIN_MS = 650;

/**
 * The hard ceiling on the curtain, whether or not the scene ever reports ready.
 *
 * Past this the transcript is revealed regardless and its own empty/error
 * states speak for themselves. An unreachable backend must not leave the reader
 * staring at a loading animation indefinitely — that is the "infinite shimmer
 * with no timeout" anti-pattern wearing a nicer coat.
 */
const SCENE_REVEAL_MAX_MS = 6000;

/** Human phrase for a presence transition, used in the auto-change toast. */
const PRESENCE_PHRASE: Record<PresenceStatus, string> = {
  present: "is back in the scene",
  unconscious: "was knocked unconscious",
  departed: "is no longer active in the scene",
  left: "left the scene",
  dead: "died",
};

/** Client state + interactions for a live scene: a streamed turn loop over the backend. */
/**
 * @param contextDocs The storyline's taggable context documents. Used only to resolve the
 *   `@name` tokens in the composer back into ids at send time — the hook never fetches or
 *   holds document text. The hook adds the **present cast** to this list itself (see
 *   `mentionOptions`), because who is present is its own state and the caller would have to
 *   read it back out to build the list.
 */
export function useScenePlay(scenario: ResolvedScenario, contextDocs: MentionOption[] = []) {
  const [seed] = useState(() => buildScene(scenario));
  const [messages, setMessages] = useState<SceneMessage[]>(seed.messages);
  const [tension] = useState(seed.tension);
  const [stats, setStats] = useState<StatChip[]>(seed.stats);
  // Per-character live stats (keyed by characterId) — feeds the character dossier so its
  // stat sliders reflect the values that stream in as `state_update` events. Kept separate
  // from the flat `stats` list, which drives the Director rail's global Scene-state chips.
  const [statsByChar, setStatsByChar] = useState<Record<string, StatChip[]>>({});
  // Live scene presence per character (Scene Presence & Director Actions). Absent → present.
  const [presenceByChar, setPresenceByChar] = useState<PresenceMap>({});
  const [choices, setChoices] = useState<SceneChoice[]>(seed.choices);
  const { notify } = useToast();
  const nameOf = useCallback(
    (id: string) => scenario.cast.find((c) => c.id === id)?.name ?? "A character",
    [scenario.cast],
  );
  const [composer, setComposer] = useState("");
  // The narrator direction for the next turn — the composer's second box, which only exists
  // under Player POV (in narrator mode the message box already IS the direction). Cleared on
  // send, and whenever POV is dropped, so stale steering never rides along with a later turn.
  const [guidance, setGuidance] = useState("");
  // Per-scene play controls (persisted on the scenario). Local state drives the composer
  // dropdowns; each change is written back so the backend reads it on the next turn.
  const [maxTurns, setMaxTurnsState] = useState<number>(scenario.maxTurns ?? 5);
  const [suggestionsCount, setSuggestionsCountState] = useState<number>(
    scenario.suggestionsCount ?? 4,
  );
  const [beatLength, setBeatLengthState] = useState<BeatLength>(
    scenario.beatLength ?? "medium",
  );
  // Player POV: the id of the character the player is speaking AS (null = the default
  // guide/narrator behavior). Drives the "Speaking as" composer select, the optimistic
  // bubble's identity, and the `povCharacterId` sent on the next turn.
  const [pov, setPov] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Reset POV when the chosen character is no longer present (died/left/etc.) — you can't keep
  // speaking as someone who has left the scene. Reconciled DURING RENDER (React's "adjust state
  // when a value changes" pattern) rather than in an effect: whenever `presenceByChar` changes,
  // re-check the POV target and drop it if it is gone. Converges (the snapshot is updated too).
  const [povPresenceSnapshot, setPovPresenceSnapshot] = useState(presenceByChar);
  if (presenceByChar !== povPresenceSnapshot) {
    setPovPresenceSnapshot(presenceByChar);
    if (pov && (presenceByChar[pov] ?? "present") !== "present") {
      setPov(null);
      setGuidance(""); // the direction box goes with it
    }
  }
  const [reveal, setReveal] = useState(false);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  // Ordered per-turn diagnostic trace (the Inspector panel). Populated only from the
  // opt-in `trace` frames the backend interleaves when we request them.
  const [traceTurns, setTraceTurns] = useState<TraceTurn[]>([]);
  // Live, per-character model deliberation (Reasoning visibility = "full"). Ephemeral:
  // never persisted, cleared as each beat finishes, and empty on resume.
  const [reasoningByChar, setReasoningByChar] = useState<Record<string, string>>({});
  // What the player asked the scene to do this turn, and how much has landed.
  const [direction, setDirection] = useState<DirectionProgress>(NO_DIRECTION);

  // Live "scene pulse" activity feed: newest entries first, capped at 12. Live-only by
  // design — not seeded from history. Both the Director rail (Phase 6) and the cast rail
  // read from this feed. Resets to [] automatically on new scene load (initial state).
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  // Per-character live status: "idle" | "thinking" | "speaking". Resets to {} when the
  // stream leaves "streaming" (nobody is stuck in thinking/speaking between turns).
  const [activityByChar, setActivityByChar] = useState<Record<string, CharacterActivity>>({});
  // The scene's SINGLE current focus — who is up right now, and whether the turn is
  // wrapping up. Drives the transcript's turn-status strip (the only speaker signal below
  // the `lg` breakpoint, where the cast rail is hidden). Reset to idle when a turn settles.
  const [turnStatus, setTurnStatus] = useState<TurnStatus>(IDLE_TURN_STATUS);
  // Model's reported context-window size in tokens (null = unknown / fetch failed → dial hidden).
  const [maxContextTokens, setMaxContextTokens] = useState<number | null>(null);
  // The EXACT input-token count the model reported for the latest turn (`usage.prompt_tokens`,
  // carried on the engine's `context` trace step) — the true "context window used", including
  // the World Primer, output contract, stat guidance, RAG lore, and transcript. `null` before
  // any turn has streamed one (or on an endpoint that reports no usage); the dial then falls
  // back to the estimate below. Seeded from persisted traces on resume.
  const [liveContextTokens, setLiveContextTokens] = useState<number | null>(null);
  // Live character↔character relationships from the story graph (P6). Falls back to the
  // seed placeholder while empty / when the graph is off.
  const [graphRels, setGraphRels] = useState<Relationship[]>([]);

  // Char/4 estimate of the tokens the transcript occupies — the fallback the context dial
  // shows before a turn has reported its EXACT `usage.prompt_tokens` (which is far larger,
  // since it also counts the primer/contract/guidance/RAG the estimate can't see).
  //
  // Measured over the WHOLE transcript now rather than a `contextBeats` slice: the depth is
  // no longer a number the client holds — the server fits it to the model's real budget
  // each turn — and estimating against a window the client is only guessing at would be
  // less honest than estimating against everything there is.
  const estimatedUsedTokens = useMemo(() => {
    const texts = messages.map((m) => [m.text, m.action, m.thought].filter(Boolean).join(" "));
    return estimateUsedTokens(texts);
  }, [messages]);

  // The play session id is captured from the first streamed event (or a resumed
  // session) and reused so subsequent turns continue the same session. Mirrored into
  // state so the Export control can react to whether there is anything to export yet.
  const sessionRef = useRef<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const rememberSession = useCallback((id: string) => {
    sessionRef.current = id;
    setSessionId(id);
  }, []);

  /**
   * What an earlier turn could not deliver and the next one will re-owe.
   *
   * Kept separate from `direction` (this turn's live progress) rather than merged into it:
   * the debt exists **between** turns, when there is no progress to show, and merging them
   * would make a standing item disappear the moment a turn started and reappear when it
   * ended.
   */
  const [standing, setStanding] = useState<StandingItem[]>([]);
  /**
   * How far back the scene reached on the last turn, and what it cost. Reported rather than
   * configured — the depth is a consequence of the model's window, not a preference.
   */
  const [sceneMemory, setSceneMemory] = useState<SceneMemory | null>(null);
  /** Where verbatim recall ends and the scene's rolling summary takes over. */
  const [summaryThroughSeq, setSummaryThroughSeq] = useState<number | null>(null);
  /** The last message the player actually sent, for ArrowUp recall. */
  const [lastSent, setLastSent] = useState("");

  /**
   * Put the last sent message back in the composer.
   *
   * Deliberately does **not** guard on the composer being empty — the shortcut hook already
   * does, and doing it in both places would mean two rules to keep in step. It is a no-op
   * with nothing to recall.
   */
  const recallLast = useCallback(() => {
    if (lastSent) setComposer(lastSent);
  }, [lastSent]);

  /**
   * Stop asking for something the scene still owes.
   *
   * Optimistic — the row goes immediately, because the player has decided and waiting on a
   * round-trip to acknowledge a cancellation reads as the control not working. A failed
   * write is reconciled by the next `loadSession`.
   */
  const dismissStanding = useCallback(
    (itemId: string | null) => {
      const sid = sessionRef.current;
      if (!sid) return;
      setStanding((items) => (itemId === null ? [] : items.filter((i) => i.id !== itemId)));
      void clearStandingDirection(scenario.id, sid, itemId === null ? null : [itemId]).catch(
        () => {},
      );
    },
    [scenario.id],
  );

  /** Each cast member's authored starting stats — the baseline a loaded session layers on. */
  const baselineRef = useRef<Record<string, StatChip[]>>({});
  /**
   * Whether a turn is streaming, readable from a callback. `sending` is derived from the
   * stream further down, so the record actions cannot see it directly. Mutating the record
   * mid-sentence would leave a half-streamed beat attached to rows that no longer exist.
   */
  const sendingRef = useRef(false);

  // Loader → content reveal.
  //
  // This used to be a blind `setTimeout(2200)` on mount: the curtain held for
  // 2.2s whether the scene was ready in 100ms or not ready at 5s. That is a
  // spinner for a 150ms request, scaled up — self-inflicted latency that the
  // user reads as the app being slow.
  //
  // It is now driven by the real readiness signal (`sceneReady`, set when the
  // resume/baseline load settles), bracketed by two bounds:
  //
  //  - a MINIMUM, so an instant load does not flash the curtain and yank it
  //    away. The SceneLoader is the app's one signature motion moment; a
  //    strobe is worse than either extreme.
  //  - a MAXIMUM, so a stalled or unreachable backend cannot hold the reader
  //    behind a curtain forever. Past the cap we reveal anyway and let the
  //    transcript's own empty/error states speak.
  const [sceneReady, setSceneReady] = useState(false);
  useEffect(() => {
    if (!sceneReady) {
      // The hard ceiling still runs while we wait for readiness.
      const cap = window.setTimeout(() => {
        setReveal(true);
        setLoading(false);
      }, SCENE_REVEAL_MAX_MS);
      return () => window.clearTimeout(cap);
    }
    const floor = window.setTimeout(() => {
      setReveal(true);
      setLoading(false);
    }, SCENE_REVEAL_MIN_MS);
    return () => window.clearTimeout(floor);
  }, [sceneReady]);

  // The play-through record — which stories exist, which is open, and every operation that
  // changes one after the fact. Extracted to its own hook when this file passed the repo's
  // 800-line ceiling; its surface is re-exported below unchanged.
  // Memoised: the record hook's callbacks take this as a dependency, so an object literal
  // rebuilt each render would give every one of them a new identity on every render.
  // `useState` setters are stable, and `notify` comes from a context that keeps it stable.
  const sceneWriters = useMemo(
    () => ({
      setMessages,
      setStats,
      setStatsByChar,
      setPresenceByChar,
      setTraceTurns,
      setChoices,
      setPov,
      setGuidance,
      setComposer,
      setLiveContextTokens,
      setStreamError,
      setStanding,
      setSceneMemory,
      setSummaryThroughSeq,
      notify,
    }),
    [notify],
  );
  const record = useSessionRecord({
    scenario,
    sessionRef,
    rememberSession,
    setSessionId,
    baselineRef,
    sendingRef,
    apply: sceneWriters,
  });
  // Destructured so the render body writes to a plain ref rather than through the hook's
  // return object, which the immutability lint rule (correctly) refuses.
  const { loadSession, refreshSessions, latestSeqRef } = record;


  // Seed live per-character stats from each cast member's persisted starting values, then
  // resume the scenario's most recent play-through on top of that baseline: reload its full
  // history (turns, thoughts, live stats, and the graph/RAG trace) so nothing is ever lost
  // and play continues on the same session. Both steps are best-effort — a failed baseline
  // fetch (per character) degrades to no baseline for that character, and no saved session
  // keeps the seed scene layered over the baseline instead of the schema defaults.
  useEffect(() => {
    let alive = true;
    (async () => {
      const pairs = await Promise.all(
        scenario.cast.map((c) =>
          getCharacterStats(c.id)
            .then((values) => [c.id, values] as const)
            .catch(() => [c.id, {}] as const),
        ),
      );
      if (!alive) return;
      const base = baselineStatsByChar(Object.fromEntries(pairs));
      baselineRef.current = base;
      setStatsByChar(base);

      const list = await refreshSessions();
      // `list_sessions` already orders by recency, but the tray now lets a play-through be
      // renamed (which bumps recency) and deleted, so read the newest explicitly rather than
      // trusting an index. An empty list is a scenario that has never been played: the seed
      // scene stays up and the first turn opens a session for it.
      const newest = mostRecent(list);
      if (!alive || !newest) return;
      await loadSession(newest.id);
    })()
      .catch(() => {})
      // Ready either way. A failed resume is a scene that starts fresh, not a
      // scene that never opens — the curtain must not outlive the attempt.
      .finally(() => {
        if (alive) setSceneReady(true);
      });
    return () => {
      alive = false;
    };
    // `loadSession` closes over `scenario`, which is stable for the life of the route.
  }, [scenario.id, scenario.cast, refreshSessions, loadSession]);

  // Save-on-close: mark the session closed when the player leaves (in-app unmount or a
  // real browser unload). Every turn already persists; this stamps the close + recency.
  useEffect(() => {
    const close = () => {
      const sid = sessionRef.current;
      if (sid) closePlaySession(scenario.id, sid);
    };
    window.addEventListener("beforeunload", close);
    return () => {
      window.removeEventListener("beforeunload", close);
      close();
    };
  }, [scenario.id]);

  // Pull live relationships from the story graph once (best-effort — empty keeps the seed).
  useEffect(() => {
    let alive = true;
    getScenarioRelationships(scenario.id)
      .then((r) => {
        if (alive && r.relationships.length) {
          setGraphRels(graphRelationshipsToRel(r.relationships, scenario.cast));
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [scenario.id, scenario.cast]);

  // Fetch the model's context-window size once on mount (best-effort — failure keeps null
  // so the ContextUsageDial stays hidden rather than showing an invalid value).
  useEffect(() => {
    getLlmContextWindow()
      .then((r) => setMaxContextTokens(r.maxContextTokens))
      .catch(() => {});
  }, []);

  // Manually set a character's scene presence (the cast-rail control + toast undo).
  // Optimistic; persists best-effort so the change survives reload and folds like an
  // engine-driven one. No-op without a session yet (nothing to attach it to).
  const setPresence = useCallback(
    (characterId: string, status: PresenceStatus, reason = "") => {
      setPresenceByChar((m) => ({ ...m, [characterId]: status }));
      const sid = sessionRef.current;
      if (!sid) return;
      void apiSetPresence(scenario.id, {
        sessionId: sid,
        characterId,
        status,
        ...(reason ? { reason } : {}),
      }).catch(() => {});
    },
    [scenario.id],
  );

  /**
   * Answer the scene's ask about an absent character.
   *
   * Accepting brings them in; declining records `departed` with a `declined` reason. The
   * decline is written rather than merely dismissed, and that is the point: a
   * `character_status_change` on this session is exactly what stops the engine asking about
   * the same character again, so "not now" has to leave a mark or it would be re-offered
   * every turn.
   */
  const answerCastRequest = useCallback(
    (characterId: string, accept: boolean) =>
      setPresence(characterId, accept ? "present" : "departed", accept ? "" : "declined"),
    [setPresence],
  );

  const onFrame = useCallback((frame: TurnStreamFrame) => {
    // Track the highest persisted seq as it streams, so a record action taken straight after
    // a turn carries a current precondition rather than a stale one from the last load.
    const seq = (frame as { seq?: number }).seq;
    if (typeof seq === "number" && seq > (latestSeqRef.current ?? -1)) latestSeqRef.current = seq;
    const sid = sessionIdOf(frame);
    if (sid && sid !== sessionRef.current) rememberSession(sid);

    // Activity feed + per-character status + the scene's turn status see ALL frames
    // (trace, story events, errors).
    setActivity((a) => applyActivity(a, frame));
    setActivityByChar((m) => applyCharacterActivity(m, frame));
    setTurnStatus((s) => applyTurnStatus(s, frame));
    setDirection((d) => applyDirection(d, frame));

    if (frame.type === "reasoning") {
      setReasoningByChar((m) => applyReasoning(m, frame));
      return;
    }

    if (frame.type === "trace") {
      // The engine's `context` step carries the exact input-token count for the turn's
      // character call — the real "context window used" the dial renders.
      if (frame.step === "context" && typeof frame.data.promptTokens === "number") {
        setLiveContextTokens(frame.data.promptTokens);
      }
      // How far back this turn reached — what the config menu reports back to the player in
      // place of the beats slider they used to have to guess with.
      if (frame.step === "window") {
        const memory = latestSceneMemory([{ step: frame.step, data: frame.data }]);
        if (memory) setSceneMemory(memory);
      }
      setTraceTurns((t) => foldTrace(t, frame));
      // One trace step also reaches the transcript: `speaker` opens the chosen character's
      // beat before any words exist, so the wait has a place to live. Every other step is
      // ignored by mergeFrame.
      if (frame.step === "speaker") setMessages((m) => mergeFrame(m, frame));
      return;
    }
    if (frame.type === "error") {
      setStreamError(frame.message);
      return;
    }
    if (frame.type === "state_update") {
      if (frame.data.stat) {
        const stat = frame.data.stat;
        setStats((s) => applyStatUpdate(s, stat));
        setStatsByChar((m) => applyStatByChar(m, stat));
      }
      return;
    }
    if (frame.type === "character_status_change") {
      const { characterId, status, auto } = frame.data;
      setPresenceByChar((m) => applyPresence(m, frame));
      // Auto = the engine removed them (death/exit/collapse) → announce with an Undo that
      // brings them back into the scene. A manual override (auto=false) is already intended.
      if (auto) {
        notify({
          title: "Scene presence",
          message: `${nameOf(characterId)} ${PRESENCE_PHRASE[status]}.`,
          action: { label: "Undo", onClick: () => setPresence(characterId, "present") },
          durationMs: 9000,
        });
      }
      return;
    }
    if (frame.type === "branch_choices") {
      setChoices(branchOptionsToChoices(frame.data.choices));
      // The planner's question (when it asked rather than guessed) rides on the beat, so it
      // survives the replace-the-open-choices filter and renders above its own options.
      const prompt = frame.data.prompt ?? "";
      setMessages((m) => [...m.filter((x) => x.kind !== "choices"), { kind: "choices", text: prompt }]);
      return;
    }
    setMessages((prev) => mergeFrame(prev, frame));
  }, [rememberSession, notify, nameOf, setPresence]);

  const stream = useEventStream<TurnStreamFrame>(onFrame);
  const sending = stream.status === "streaming";
  // Mirror into a ref so the record actions declared above can read it. Writing a ref in an
  // effect costs no extra render, unlike threading the value back up through state.
  useEffect(() => {
    sendingRef.current = sending;
  }, [sending]);


  // Choosing who to speak as. Leaving POV (back to Narrator) also drops the direction box's
  // text — in narrator mode the message box carries the direction, so keeping it would send
  // the same steer twice.
  // Leaving POV used to clear the direction, on the assumption it was a POV artefact. It is
  // not: the direction is a scene-level intent, and the row exists in both modes now. The
  // text is kept — narrator mode just explains that the message box carries it. (It is still
  // cleared on send: a direction applies to the turn it rode in on, not to every later one.)
  const choosePov = useCallback((id: string | null) => setPov(id), []);

  // ---- Create image (the transcript's scene-image action) -------------------
  // Its own stream, independent of the turn stream: a picture can be asked for between
  // turns and must not abort (or be aborted by) a turn in flight. `imageStage` drives the
  // control's staged progress; the finished `scene_image` event folds into the transcript
  // through the same reducer the turn stream uses, so live and reload agree.
  const [imageStage, setImageStage] = useState<"prompt" | "render" | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);
  const onMomentFrame = useCallback((frame: MomentStreamFrame) => {
    if (frame.type === "moment_stage") {
      setImageStage(frame.stage);
      return;
    }
    if (frame.type === "error") {
      setImageError(frame.message);
      return;
    }
    setMessages((prev) => mergeFrame(prev, frame));
  }, []);
  const momentStream = useEventStream<MomentStreamFrame>(onMomentFrame);
  const creatingImage = momentStream.status === "streaming";

  const createImage = useCallback(() => {
    const sid = sessionRef.current;
    if (!sid || creatingImage) return; // nothing to depict yet / already painting
    setImageError(null);
    setImageStage("prompt");
    void momentStream
      .run((signal) => postSceneMoment(scenario.id, { sessionId: sid }, signal))
      .catch((err: unknown) =>
        setImageError(
          err instanceof Error && err.message ? err.message : "The image could not be generated.",
        ),
      )
      .finally(() => setImageStage(null));
  }, [creatingImage, momentStream, scenario.id]);

  /**
   * Run a turn with no line from the player at all — the scene simply carries on.
   *
   * No optimistic bubble, because there is nothing to show: the player said nothing, and a
   * blank beat in the transcript would be worse than none. Everything else is the ordinary
   * turn path, so a continuation streams, traces and persists exactly like any other turn.
   */
  const continueTurn = useCallback(() => {
    if (sending) return; // in-flight guard
    setStreamError(null);
    setMessages((m) => m.filter((x) => x.kind !== "choices"));
    void stream
      .run((signal) =>
        postTurn(
          scenario.id,
          {
            text: "",
            continuation: true,
            sessionId: sessionRef.current,
            trace: true,
            povCharacterId: pov,
          },
          signal,
        ),
      )
      .catch(() => setStreamError((e) => e ?? "The turn could not be completed."))
      .finally(() => {
        setActivityByChar({});
        setTurnStatus(IDLE_TURN_STATUS);
        setMessages(dropPendingBeats);
        void refreshSessions();
      });
  }, [sending, scenario.id, stream, pov, refreshSessions]);

  /**
   * Generate another version of a beat, streaming it into the beat's existing position.
   *
   * Reloads the session when the stream ends rather than reconciling takes from the frames:
   * the take list is only complete once the server has recorded it, and `loadSession` is the
   * one path already proven to turn rows into a faithful transcript.
   */
  const rerollBeat = useCallback(
    (eventId: string, scope: "beat" | "turn" = "beat") => {
      const sid = sessionRef.current;
      if (!sid || sending) return;
      setStreamError(null);
      void stream
        .run((signal) =>
          apiRerollBeat(scenario.id, sid, eventId, { scope }, signal),
        )
        .catch(() => setStreamError((e) => e ?? "That beat could not be re-rolled."))
        .finally(() => {
          setActivityByChar({});
          setTurnStatus(IDLE_TURN_STATUS);
          setMessages(dropPendingBeats);
          void loadSession(sid);
        });
    },
    [sending, scenario.id, stream, loadSession],
  );

  /** Show one of a beat's kept versions. Optimistic; reverts on failure. */
  const selectTake = useCallback(
    async (eventId: string, take: number) => {
      const sid = sessionRef.current;
      if (!sid || sending) return;
      try {
        const row = await selectBeatTake(scenario.id, sid, eventId, take);
        const text = String((row.data as { text?: string }).text ?? "");
        setMessages((current) =>
          current.map((m) =>
            m.id === eventId
              ? { ...m, text, takes: m.takes ? { ...m.takes, active: take } : m.takes }
              : m,
          ),
        );
      } catch {
        notify({ message: "That version could not be shown.", variant: "error" });
      }
    },
    [sending, scenario.id, notify],
  );

  // ---- Ghostwriter ---------------------------------------------------------
  // Its own stream, independent of the turn stream (like the moment stream): a draft is not
  // a turn, and running it through the turn machinery would give it a place in the record
  // it must not have until the player actually sends.
  /** What the player wrote before a draft replaced it, so Undo can put it back. */
  const preDraftRef = useRef<string | null>(null);
  const [canUndoGhostwrite, setCanUndoGhostwrite] = useState(false);
  const onGhostwriteFrame = useCallback((frame: GhostwriteStreamFrame) => {
    if (frame.type === "error") {
      setStreamError(frame.message);
      return;
    }
    if (frame.text) setComposer((c) => c + frame.text);
  }, []);
  const ghostStream = useEventStream<GhostwriteStreamFrame>(onGhostwriteFrame);
  const ghostwriting = ghostStream.status === "streaming";

  /**
   * Turn the note in the composer into the line itself.
   *
   * The note is consumed: the box is cleared and the draft streams into it, so the player
   * watches their intent become a sentence in the place they will edit it. Undo restores
   * the note verbatim.
   */
  const ghostwrite = useCallback(() => {
    const sid = sessionRef.current;
    const intent = composer.trim();
    if (!sid || !intent || ghostwriting || sending) return;
    preDraftRef.current = composer;
    setCanUndoGhostwrite(true);
    setComposer("");
    setStreamError(null);
    void ghostStream
      .run((signal) =>
        postGhostwrite(
          scenario.id,
          { sessionId: sid, intent, povCharacterId: pov, mode: pov ? "character" : "narrator" },
          signal,
        ),
      )
      .catch(() => setStreamError((e) => e ?? "That line could not be drafted."));
  }, [composer, ghostwriting, sending, ghostStream, scenario.id, pov]);

  /** Put the player's own note back. */
  const undoGhostwrite = useCallback(() => {
    if (preDraftRef.current === null) return;
    setComposer(preDraftRef.current);
    preDraftRef.current = null;
    setCanUndoGhostwrite(false);
  }, []);

  const submit = useCallback(
    (
      text: string,
      direction = "",
      taggedDocIds: string[] = [],
      directedAt: string | null = null,
      directives: Directive[] = [],
    ) => {
      const t = text.trim();
      const d = direction.trim();
      // A turn is worth sending when the player said something **or** asked for something.
      // Direction-only is the whole point of the direction box under POV: steer the scene
      // without your character having to speak in order to do it.
      if ((!t && !d) || sending) return; // in-flight guard
      setStreamError(null);
      // Optimistic bubble; clear any open branch choices. Under Player POV the player's line
      // is the character's own line — a right-side player-authored character beat (the engine
      // withholds the visible event, so this optimistic beat is the only render of it).
      // With no line at all, the direction itself is shown as a quiet aside instead, so the
      // player can see what they asked for while the turn runs.
      const optimistic: SceneMessage = !t
        ? { kind: "direction", text: d }
        : pov
          ? { kind: "char", who: pov, fromPlayer: true, text: t }
          : { kind: "player", text: t };
      setMessages((m) => [...m.filter((x) => x.kind !== "choices"), optimistic]);
      void stream
        .run((signal) =>
          postTurn(
            scenario.id,
            {
              text: t,
              sessionId: sessionRef.current,
              trace: true,
              povCharacterId: pov,
              // Set from an `@` cast mention in the message box. The engine appends it to
              // `intent.addressed` and promotes a freeform line to `direct`, so the person
              // the player named is the one who answers.
              ...(directedAt ? { directedAt } : {}),
              // Present only when the player aimed a line at someone. The backend then
              // uses them verbatim and spends no call re-guessing what was already said.
              ...(directives.length ? { directives } : {}),
              // Only meaningful under POV — omitted otherwise so the backend keeps reading
              // the player's own line as the direction.
              guidance: d || null,
              // The player's @-tagged files. Reference for this turn only — the backend
              // keeps them out of the intent/direction/planner agents, so they inform what
              // is said without steering what happens.
              ...(taggedDocIds.length ? { taggedDocIds } : {}),
            },
            signal,
          ),
        )
        .catch(() => setStreamError((e) => e ?? "The turn could not be completed."))
        // Turn over (done or error): clear per-character activity and the turn status so
        // nobody is left stuck "thinking" — including when the stream dies before the
        // engine's end-of-turn trace lands. The activity feed itself is kept: it describes
        // what just happened, and outlives the turn by design.
        .finally(() => {
          setActivityByChar({});
          setTurnStatus(IDLE_TURN_STATUS);
          // A `speaker` trace opens a beat before any words exist, so the wait has a place
          // to live. The engine may then emit nothing for that speaker (a withheld beat, a
          // failed generation, an aborted turn) — clear the empty placeholder here rather
          // than in an effect, so it cannot outlive the turn and cannot cascade a render.
          setMessages(dropPendingBeats);
          // The turn changed this play-through's turn count, its recency, and — on the very
          // first turn of a never-played scenario, where the session is created server-side
          // and only announced on the stream — whether the tray knows it exists at all.
          void refreshSessions();
        });
    },
    [sending, scenario.id, stream, pov, refreshSessions],
  );

  // Persist a per-scene control change (optimistic; best-effort write-back to the scenario).
  const setMaxTurns = useCallback(
    (n: number) => {
      setMaxTurnsState(n);
      void updateScenario(scenario.id, { maxTurns: n }).catch(() => {});
    },
    [scenario.id],
  );
  const setSuggestionsCount = useCallback(
    (n: number) => {
      setSuggestionsCountState(n);
      void updateScenario(scenario.id, { suggestionsCount: n }).catch(() => {});
    },
    [scenario.id],
  );
  const setBeatLength = useCallback(
    (value: BeatLength) => {
      setBeatLengthState(value);
      void updateScenario(scenario.id, { beatLength: value }).catch(() => {});
    },
    [scenario.id],
  );

  /**
   * Everything `@` can name: the present cast, then the storyline's context files.
   *
   * One namespace, because the player types one `@` and does not think about which
   * subsystem a name belongs to. `kind` is what splits the ids back apart on send — a cast
   * mention aims the line (`directedAt`), a doc mention grounds it (`taggedDocIds`).
   */
  const mentionOptions = useMemo<MentionOption[]>(
    () => [
      ...scenario.cast
        .filter((c) => (presenceByChar[c.id] ?? "present") === "present")
        .map((c) => ({
          id: c.id,
          name: c.name,
          kind: "cast" as const,
          mono: c.mono,
          color: c.color,
          portrait: c.portrait,
        })),
      ...contextDocs.map((d) => ({ ...d, kind: "doc" as const })),
    ],
    [scenario.cast, presenceByChar, contextDocs],
  );

  const send = useCallback(() => {
    if (sending) return;
    // Resolve @-tags from the FINAL text of both boxes rather than from accumulated click
    // state, so what is sent always matches what the player actually left written; the
    // `@name` tokens themselves are stripped so the line reaches the intent and direction
    // agents as clean prose.
    const message = stripMentions(composer, mentionOptions);
    const text = message.text.trim();
    // The direction applies to THIS turn only — it is consumed with the message, not kept
    // as a standing instruction the player would have to remember to clear.
    const rawDirection = pov ? guidance : "";
    const directed = stripMentions(rawDirection, mentionOptions);
    // Either box on its own is enough to send. Only both empty is nothing to do.
    if (!text && !directed.text.trim()) return;
    const taggedDocIds = Array.from(new Set([...message.docIds, ...directed.docIds]));
    // The direction box read per line, when any line names a character. Free prose sends
    // none and is parsed server-side exactly as today.
    const directives = splitDirectives(rawDirection, mentionOptions);
    // Who the line is aimed at, from the FIRST cast mention in the **message** box only.
    // The message is what the player says; the direction box is what they ask the scene to
    // do, and a character named there is a subject of the direction, not the addressee.
    // (Cast ids from the direction box are held for the pinning work in Phase 8.)
    const directedAt = message.castIds[0] ?? null;
    // Remembered so ArrowUp from an empty box can hand it back — the player's own words,
    // not the stripped-for-the-model version, because that is what they would edit.
    setLastSent(composer);
    setComposer("");
    setGuidance("");
    submit(text, directed.text, taggedDocIds, directedAt, directives);
  }, [composer, mentionOptions, guidance, pov, sending, submit]);

  // Selecting a follow-up no longer submits: it writes the suggested (situation-based, tone-
  // matched) text into the composer so the player can review and edit it before sending
  // (request #2), keeping their writing style consistent. The choices stay visible until the
  // player actually sends, so they can reconsider or pick a different one.
  const choose = useCallback((c: SceneChoice) => setComposer(c.player || c.label), []);

  /**
   * **Play it out** — run a suggestion now instead of editing it first.
   *
   * The other half of `choose`. It goes as a direction-only turn (nothing was *said*) with
   * the choice's `outcome` set, which is what makes the engine open with the fuller
   * "progression" passage that plays a choice out over several beats rather than answering
   * it in one line. That behaviour has existed in the engine all along and no UI ever sent
   * the field, so it was reachable only from tests.
   */
  const playOut = useCallback(
    (c: SceneChoice) => {
      if (sending) return;
      const text = c.player || c.label;
      setStreamError(null);
      setMessages((m) => [
        ...m.filter((x) => x.kind !== "choices"),
        { kind: "direction", text },
      ]);
      void stream
        .run((signal) =>
          postTurn(
            scenario.id,
            {
              text: "",
              guidance: text,
              outcome: c.outcome || text,
              sessionId: sessionRef.current,
              trace: true,
              povCharacterId: pov,
            },
            signal,
          ),
        )
        .catch(() => setStreamError((e) => e ?? "The turn could not be completed."))
        .finally(() => {
          setActivityByChar({});
          setTurnStatus(IDLE_TURN_STATUS);
          setMessages(dropPendingBeats);
          void refreshSessions();
        });
    },
    [sending, scenario.id, stream, pov, refreshSessions],
  );

  const lastSpeaker = [...messages].reverse().find((m) => m.kind === "char");

  return {
    messages,
    choices,
    tension,
    stats,
    statsByChar,
    presenceByChar,
    mentionOptions,
    standing,
    dismissStanding,
    sceneMemory,
    summaryThroughSeq,
    lastSent,
    recallLast,
    playOut,
    answerCastRequest,
    // How far into the scene we are, for the Exit verbs' gate. Counts what the player
    // contributed — a spoken line, their POV character's line, or a bare direction — not
    // beats, which the model produces several of per turn.
    playerTurns: messages.filter(
      (m) => m.kind === "player" || m.kind === "direction" || (m.kind === "char" && m.fromPlayer),
    ).length,
    setPresence,
    relationships: graphRels.length ? graphRels : seed.relationships,
    turnOrder: seed.turnOrder,
    speakingId: lastSpeaker?.who ?? null,
    composer,
    setComposer,
    guidance,
    setGuidance,
    maxTurns,
    setMaxTurns,
    suggestionsCount,
    setSuggestionsCount,
    beatLength,
    setBeatLength,
    pov,
    setPov: choosePov,
    loading,
    reveal,
    sending,
    streamError,
    traceTurns,
    reasoningByChar,
    direction,
    sessionId,
    send,
    continueTurn,
    ghostwrite,
    ghostwriting,
    undoGhostwrite,
    canUndoGhostwrite,
    rerollBeat,
    selectTake,
    choose,
    profileId,
    // `null` closes the dossier — Escape needs a way to say that.
    openProfile: (id: string | null) => setProfileId(id),
    closeProfile: () => setProfileId(null),
    // The play-through tray: every saved story for this scenario, and the actions over them.
    // The play-through record, re-exported unchanged so the split is invisible downstream.
    sessions: record.sessions,
    refreshSessions: record.refreshSessions,
    openSession: record.openSession,
    startNewPlaythrough: record.startNewPlaythrough,
    renamePlaythrough: record.renamePlaythrough,
    deletePlaythrough: record.deletePlaythrough,
    branchFrom: record.branchFrom,
    editBeatText: record.editBeatText,
    rewindTo: record.rewindTo,
    rewound: record.rewound,
    clearRewound: record.clearRewound,
    activity,
    activityByChar,
    turnStatus,
    // Create image: `imageStage` is which half is running (null = idle), `creatingImage`
    // gates the control, `imageError` is the last failure (cleared on the next attempt).
    createImage,
    creatingImage,
    imageStage,
    imageError,
    // The dial's used-token count: the exact `usage.prompt_tokens` once a turn has reported
    // it, else the char/4 estimate. `usedTokensExact` lets the UI label which it is showing.
    usedTokens: liveContextTokens ?? estimatedUsedTokens,
    usedTokensExact: liveContextTokens !== null,
    maxContextTokens,
  };
}
