"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  closePlaySession,
  getScenarioRelationships,
  getSessionHistory,
  listPlaySessions,
  postTurn,
} from "@/lib/api";
import type { TurnStreamFrame } from "@/lib/events";
import type { ResolvedScenario } from "@/lib/types";
import { useEventStream } from "@/hooks/use-event-stream";
import {
  buildScene,
  type Relationship,
  type SceneChoice,
  type SceneMessage,
  type StatChip,
} from "./scene-data";
import {
  applyStatByChar,
  applyStatUpdate,
  branchOptionsToChoices,
  foldTrace,
  graphRelationshipsToRel,
  mergeFrame,
  rehydrateFromHistory,
  sessionIdOf,
  type TraceTurn,
} from "./turn-stream";

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
  const [choices, setChoices] = useState<SceneChoice[]>(seed.choices);
  const [composer, setComposer] = useState("");
  const [loading, setLoading] = useState(true);
  const [reveal, setReveal] = useState(false);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
  // Ordered per-turn diagnostic trace (the Inspector panel). Populated only from the
  // opt-in `trace` frames the backend interleaves when we request them.
  const [traceTurns, setTraceTurns] = useState<TraceTurn[]>([]);
  // Live character↔character relationships from the story graph (P6). Falls back to the
  // seed placeholder while empty / when the graph is off.
  const [graphRels, setGraphRels] = useState<Relationship[]>([]);
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
  useEffect(() => {
    const timer = setTimeout(() => {
      setReveal(true);
      setLoading(false);
    }, 2200);
    return () => clearTimeout(timer);
  }, []);

  // Resume the scenario's most recent play-through: reload its full history (turns,
  // thoughts, live stats, and the graph/RAG trace) so nothing is ever lost and play
  // continues on the same session. Best-effort — no saved session keeps the seed scene.
  useEffect(() => {
    let alive = true;
    listPlaySessions(scenario.id)
      .then(({ sessions }) => {
        if (!alive || !sessions.length) return undefined;
        return getSessionHistory(scenario.id, sessions[0].id).then((history) => {
          if (!alive) return;
          const scene = rehydrateFromHistory(history.events, history.traces);
          rememberSession(history.session.id);
          if (scene.messages.length) setMessages(scene.messages);
          if (scene.stats.length) setStats(scene.stats);
          setStatsByChar(scene.statsByChar);
          setTraceTurns(scene.traceTurns);
          setChoices([]);
        });
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [scenario.id, rememberSession]);

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

  const onFrame = useCallback((frame: TurnStreamFrame) => {
    const sid = sessionIdOf(frame);
    if (sid && sid !== sessionRef.current) rememberSession(sid);
    if (frame.type === "trace") {
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
    if (frame.type === "branch_choices") {
      setChoices(branchOptionsToChoices(frame.data.choices));
      setMessages((m) => [...m.filter((x) => x.kind !== "choices"), { kind: "choices" }]);
      return;
    }
    setMessages((prev) => mergeFrame(prev, frame));
  }, [rememberSession]);

  const stream = useEventStream<TurnStreamFrame>(onFrame);
  const sending = stream.status === "streaming";

  const submit = useCallback(
    (text: string, outcome?: string) => {
      const t = text.trim();
      if (!t || sending) return; // in-flight guard
      setStreamError(null);
      // Optimistic player bubble; clear any open branch choices.
      setMessages((m) => [...m.filter((x) => x.kind !== "choices"), { kind: "player", text: t }]);
      void stream
        .run((signal) =>
          postTurn(
            scenario.id,
            { text: t, sessionId: sessionRef.current, trace: true, outcome: outcome || null },
            signal,
          ),
        )
        .catch(() => setStreamError((e) => e ?? "The turn could not be completed."));
    },
    [sending, scenario.id, stream],
  );

  const send = useCallback(() => {
    if (sending) return;
    const text = composer.trim();
    if (!text) return;
    setComposer("");
    submit(text);
  }, [composer, sending, submit]);

  // Selecting a branch submits a real turn (no scripted check/follow — D11); its
  // `outcome` tells the backend to play the chosen direction out over several beats.
  const choose = useCallback(
    (c: SceneChoice) => submit(c.player || c.label, c.outcome),
    [submit],
  );

  const lastSpeaker = [...messages].reverse().find((m) => m.kind === "char");

  return {
    messages,
    choices,
    tension,
    stats,
    statsByChar,
    relationships: graphRels.length ? graphRels : seed.relationships,
    turnOrder: seed.turnOrder,
    speakingId: lastSpeaker?.who ?? null,
    composer,
    setComposer,
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
  };
}
