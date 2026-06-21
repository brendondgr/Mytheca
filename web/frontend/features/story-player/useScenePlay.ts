"use client";

import { useEffect, useState } from "react";
import type { ResolvedScenario } from "@/lib/types";
import {
  buildScene,
  type SceneChoice,
  type SceneMessage,
  type StatChip,
} from "./scene-data";

/** Client state + interactions for a live scene (send / roll / choose). */
export function useScenePlay(scenario: ResolvedScenario) {
  const [seed] = useState(() => buildScene(scenario));
  const [messages, setMessages] = useState<SceneMessage[]>(seed.messages);
  const [tension, setTension] = useState(seed.tension);
  const [stats, setStats] = useState<StatChip[]>(seed.stats);
  const [composer, setComposer] = useState("");
  const [loading, setLoading] = useState(true);
  const [reveal, setReveal] = useState(false);
  const [profileId, setProfileId] = useState<string | null>(null);

  // Loader → content reveal.
  useEffect(() => {
    const timer = setTimeout(() => {
      setReveal(true);
      setLoading(false);
    }, 1400);
    return () => clearTimeout(timer);
  }, []);

  function send() {
    const text = composer.trim();
    if (!text) return;
    setComposer("");
    setMessages((m) => [
      ...m.filter((x) => x.kind !== "choices"),
      { kind: "player", text },
      {
        kind: "narrator",
        text: "The table waits. Somewhere behind the bar, a glass is set down a little too carefully.",
      },
    ]);
  }

  function roll() {
    const r = 1 + Math.floor(Math.random() * 20);
    const ok = r >= 12;
    setMessages((m) => [
      ...m,
      {
        kind: "check",
        check: "Open check · DC 12",
        roll: r,
        result: ok ? "Success" : "Failure",
        text: ok
          ? "Fortune leans your way — the moment turns in your favour."
          : "The dice are unkind. The moment slips through your fingers.",
      },
    ]);
  }

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
      {
        kind: "check",
        check: c.check,
        roll: 1 + Math.floor(Math.random() * 20),
        result: "Success",
        text: "You commit to the approach. The room shifts to meet it.",
      },
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
    send,
    roll,
    choose,
    profileId,
    openProfile: (id: string) => setProfileId(id),
    closeProfile: () => setProfileId(null),
  };
}
