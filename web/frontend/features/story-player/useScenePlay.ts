"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getScenarioRelationships, postTurn } from "@/lib/api";
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
  // The play session id is captured from the first streamed event and reused so
  // subsequent turns continue the same session.
  const sessionRef = useRef<string | null>(null);

  // Loader → content reveal.
  useEffect(() => {
    const timer = setTimeout(() => {
      setReveal(true);
      setLoading(false);
    }, 2200);
    return () => clearTimeout(timer);
  }, []);

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
    if (sid) sessionRef.current = sid;
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
  }, []);

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
    send,
    choose,
    profileId,
    openProfile: (id: string) => setProfileId(id),
    closeProfile: () => setProfileId(null),
  };
}
