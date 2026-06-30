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
import { applyStatUpdate, branchOptionsToChoices, mergeFrame, sessionIdOf } from "./turn-stream";

/** Client state + interactions for a live scene: a streamed turn loop over the backend. */
export function useScenePlay(scenario: ResolvedScenario) {
  const [seed] = useState(() => buildScene(scenario));
  const [messages, setMessages] = useState<SceneMessage[]>(seed.messages);
  const [tension] = useState(seed.tension);
  const [stats, setStats] = useState<StatChip[]>(seed.stats);
  const [choices, setChoices] = useState<SceneChoice[]>(seed.choices);
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
    if (frame.type === "state_update") {
      if (frame.data.stat) setStats((s) => applyStatUpdate(s, frame.data.stat!));
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
    (text: string) => {
      const t = text.trim();
      if (!t || sending) return; // in-flight guard
      setStreamError(null);
      // Optimistic player bubble; clear any open branch choices.
      setMessages((m) => [...m.filter((x) => x.kind !== "choices"), { kind: "player", text: t }]);
      void stream
        .run((signal) => postTurn(scenario.id, { text: t, sessionId: sessionRef.current }, signal))
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

  // Selecting a branch submits a real turn (no scripted check/follow — D11).
  const choose = useCallback((c: SceneChoice) => submit(c.player || c.label), [submit]);

  const lastSpeaker = [...messages].reverse().find((m) => m.kind === "char");

  return {
    messages,
    choices,
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
