"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { postTurn } from "@/lib/api";
import type { TurnStreamFrame } from "@/lib/events";
import type { ResolvedScenario } from "@/lib/types";
import { useEventStream } from "@/hooks/use-event-stream";
import {
  buildScene,
  type SceneChoice,
  type SceneMessage,
  type StatChip,
} from "./scene-data";
import { mergeFrame, sessionIdOf } from "./turn-stream";

/** Client state + interactions for a live scene: a streamed turn loop over the backend. */
export function useScenePlay(scenario: ResolvedScenario) {
  const [seed] = useState(() => buildScene(scenario));
  const [messages, setMessages] = useState<SceneMessage[]>(seed.messages);
  const [tension, setTension] = useState(seed.tension);
  const [stats, setStats] = useState<StatChip[]>(seed.stats);
  const [composer, setComposer] = useState("");
  const [loading, setLoading] = useState(true);
  const [reveal, setReveal] = useState(false);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [streamError, setStreamError] = useState<string | null>(null);
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

  const onFrame = useCallback((frame: TurnStreamFrame) => {
    const sid = sessionIdOf(frame);
    if (sid) sessionRef.current = sid;
    if (frame.type === "error") {
      setStreamError(frame.message);
      return;
    }
    setMessages((prev) => mergeFrame(prev, frame));
  }, []);

  const stream = useEventStream<TurnStreamFrame>(onFrame);
  const sending = stream.status === "streaming";

  const send = useCallback(() => {
    const text = composer.trim();
    if (!text || sending) return; // in-flight guard
    setComposer("");
    setStreamError(null);
    // Optimistic player bubble; clear any open branch choices.
    setMessages((m) => [...m.filter((x) => x.kind !== "choices"), { kind: "player", text }]);
    void stream
      .run((signal) => postTurn(scenario.id, { text, sessionId: sessionRef.current }, signal))
      .catch(() => setStreamError((e) => e ?? "The turn could not be completed."));
  }, [composer, sending, scenario.id, stream]);

  // Branch selection stays scripted until the branch/stat phase wires it to the engine.
  function choose(c: SceneChoice) {
    setStats((s) =>
      s.map((chip) => {
        if (c.suspicion && chip.label === "Suspicion")
          return { ...chip, value: chip.value + c.suspicion };
        if (c.trust && chip.label.toLowerCase().includes("trust"))
          return { ...chip, value: chip.value + c.trust };
        return chip;
      }),
    );
    setTension((t) => Math.min(100, t + (c.tension ?? 0)));
    setMessages((m) => [
      ...m.filter((x) => x.kind !== "choices"),
      { kind: "player", text: c.player },
      { kind: "char", who: c.follow.who, action: c.follow.action, text: c.follow.text },
    ]);
  }

  const lastSpeaker = [...messages].reverse().find((m) => m.kind === "char");

  return {
    messages,
    choices: seed.choices,
    tension,
    stats,
    relationships: seed.relationships,
    turnOrder: seed.turnOrder,
    speakingId: lastSpeaker?.who ?? null,
    composer,
    setComposer,
    loading,
    reveal,
    sending,
    streamError,
    send,
    choose,
    profileId,
    openProfile: (id: string) => setProfileId(id),
    closeProfile: () => setProfileId(null),
  };
}
