"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  closePlaySession,
  getCharacterStats,
  getLlmContextWindow,
  getScenarioRelationships,
  getSessionHistory,
  listPlaySessions,
  postSceneMoment,
  postTurn,
  setPresence as apiSetPresence,
  updateScenario,
} from "@/lib/api";
import { estimateUsedTokens } from "@/lib/contextBudget";
import type { MomentStreamFrame, PresenceStatus, TurnStreamFrame } from "@/lib/events";
import type { ResolvedScenario } from "@/lib/types";
import { useEventStream } from "@/hooks/use-event-stream";
import { useToast } from "@/components/layout/ToastProvider";
import {
  buildScene,
  type Relationship,
  type SceneChoice,
  type SceneMessage,
  type StatChip,
} from "./scene-data";
import {
  applyActivity,
  applyCharacterActivity,
  type ActivityEntry,
  type CharacterActivity,
  applyPresence,
  applyStatByChar,
  applyStatUpdate,
  baselineStatsByChar,
  branchOptionsToChoices,
  foldTrace,
  graphRelationshipsToRel,
  latestContextTokens,
  latestPov,
  mergeFrame,
  type PresenceMap,
  rehydrateFromHistory,
  sessionIdOf,
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
export function useScenePlay(scenario: ResolvedScenario) {
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
  const [contextBeats, setContextBeatsState] = useState<number>(scenario.contextBeats ?? 14);
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
  // Live "scene pulse" activity feed: newest entries first, capped at 12. Live-only by
  // design — not seeded from history. Both the Director rail (Phase 6) and the cast rail
  // read from this feed. Resets to [] automatically on new scene load (initial state).
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  // Per-character live status: "idle" | "thinking" | "speaking". Resets to {} when the
  // stream leaves "streaming" (nobody is stuck in thinking/speaking between turns).
  const [activityByChar, setActivityByChar] = useState<Record<string, CharacterActivity>>({});
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

  // Char/4 estimate of the tokens the last `contextBeats` messages occupy — the fallback
  // the context dial shows before a turn has reported its EXACT `usage.prompt_tokens`
  // (which is far larger, since it also counts the primer/contract/guidance/RAG the
  // estimate can't see). Recomputed whenever messages or contextBeats changes.
  const estimatedUsedTokens = useMemo(() => {
    const window = messages.slice(-contextBeats);
    const texts = window.map((m) => [m.text, m.action, m.thought].filter(Boolean).join(" "));
    return estimateUsedTokens(texts);
  }, [messages, contextBeats]);

  // The play session id is captured from the first streamed event (or a resumed
  // session) and reused so subsequent turns continue the same session. Mirrored into
  // state so the Export control can react to whether there is anything to export yet.
  const sessionRef = useRef<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const rememberSession = useCallback((id: string) => {
    sessionRef.current = id;
    setSessionId(id);
  }, []);

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
      setStatsByChar(base);

      const { sessions } = await listPlaySessions(scenario.id).catch(() => ({ sessions: [] }));
      if (!alive || !sessions.length) return;
      const history = await getSessionHistory(scenario.id, sessions[0].id);
      if (!alive) return;
      const scene = rehydrateFromHistory(history.events, history.traces, base);
      rememberSession(history.session.id);
      // Restore the "Speaking as" selection from the most recent user_turn's pov, so the
      // next line continues in that character's voice (null → the guide/narrator default).
      setPov(latestPov(history.events));
      // Seed the dial with the resumed session's last real context-token count (null when
      // none was recorded → the estimate fallback is used until the next turn streams one).
      setLiveContextTokens(latestContextTokens(history.traces));
      if (scene.messages.length) setMessages(scene.messages);
      if (scene.stats.length) setStats(scene.stats);
      setStatsByChar(scene.statsByChar);
      setPresenceByChar(scene.presenceByChar);
      setTraceTurns(scene.traceTurns);
      setChoices([]);
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
  }, [scenario.id, scenario.cast, rememberSession]);

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
    (characterId: string, status: PresenceStatus) => {
      setPresenceByChar((m) => ({ ...m, [characterId]: status }));
      const sid = sessionRef.current;
      if (!sid) return;
      void apiSetPresence(scenario.id, { sessionId: sid, characterId, status }).catch(() => {});
    },
    [scenario.id],
  );

  const onFrame = useCallback((frame: TurnStreamFrame) => {
    const sid = sessionIdOf(frame);
    if (sid && sid !== sessionRef.current) rememberSession(sid);

    // Activity feed + per-character status see ALL frames (trace, story events, errors).
    setActivity((a) => applyActivity(a, frame));
    setActivityByChar((m) => applyCharacterActivity(m, frame));

    if (frame.type === "trace") {
      // The engine's `context` step carries the exact input-token count for the turn's
      // character call — the real "context window used" the dial renders.
      if (frame.step === "context" && typeof frame.data.promptTokens === "number") {
        setLiveContextTokens(frame.data.promptTokens);
      }
      setTraceTurns((t) => foldTrace(t, frame));
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
      setMessages((m) => [...m.filter((x) => x.kind !== "choices"), { kind: "choices" }]);
      return;
    }
    setMessages((prev) => mergeFrame(prev, frame));
  }, [rememberSession, notify, nameOf, setPresence]);

  const stream = useEventStream<TurnStreamFrame>(onFrame);
  const sending = stream.status === "streaming";

  // Choosing who to speak as. Leaving POV (back to Narrator) also drops the direction box's
  // text — in narrator mode the message box carries the direction, so keeping it would send
  // the same steer twice.
  const choosePov = useCallback((id: string | null) => {
    setPov(id);
    if (id === null) setGuidance("");
  }, []);

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

  const submit = useCallback(
    (text: string, direction = "") => {
      const t = text.trim();
      if (!t || sending) return; // in-flight guard
      setStreamError(null);
      // Optimistic bubble; clear any open branch choices. Under Player POV the player's line
      // is the character's own line — a right-side player-authored character beat (the engine
      // withholds the visible event, so this optimistic beat is the only render of it).
      const optimistic: SceneMessage = pov
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
              // Only meaningful under POV — omitted otherwise so the backend keeps reading
              // the player's own line as the direction.
              guidance: direction.trim() || null,
            },
            signal,
          ),
        )
        .catch(() => setStreamError((e) => e ?? "The turn could not be completed."))
        // Turn over (done or error): clear per-character activity so nobody is stuck
        // "thinking". The activity feed itself is kept — it describes what just happened.
        .finally(() => setActivityByChar({}));
    },
    [sending, scenario.id, stream, pov],
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
  const setContextBeats = useCallback(
    (n: number) => {
      setContextBeatsState(n);
      void updateScenario(scenario.id, { contextBeats: n }).catch(() => {});
    },
    [scenario.id],
  );

  const send = useCallback(() => {
    if (sending) return;
    const text = composer.trim();
    if (!text) return;
    // The direction applies to THIS turn only — it is consumed with the message, not kept
    // as a standing instruction the player would have to remember to clear.
    const direction = pov ? guidance : "";
    setComposer("");
    setGuidance("");
    submit(text, direction);
  }, [composer, guidance, pov, sending, submit]);

  // Selecting a follow-up no longer submits: it writes the suggested (situation-based, tone-
  // matched) text into the composer so the player can review and edit it before sending
  // (request #2), keeping their writing style consistent. The choices stay visible until the
  // player actually sends, so they can reconsider or pick a different one.
  const choose = useCallback((c: SceneChoice) => setComposer(c.player || c.label), []);

  const lastSpeaker = [...messages].reverse().find((m) => m.kind === "char");

  return {
    messages,
    choices,
    tension,
    stats,
    statsByChar,
    presenceByChar,
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
    contextBeats,
    setContextBeats,
    pov,
    setPov: choosePov,
    loading,
    reveal,
    sending,
    streamError,
    traceTurns,
    sessionId,
    send,
    choose,
    profileId,
    openProfile: (id: string) => setProfileId(id),
    closeProfile: () => setProfileId(null),
    activity,
    activityByChar,
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
