"use client";

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import type { Character, ResolvedScenario } from "@/lib/types";
import { useScenePlay } from "./useScenePlay";
import { tensionLabel } from "./scene-data";
import { SceneHeader } from "@/components/layout/SceneHeader";
import { CastRail } from "@/components/feature/CastRail";
import { DirectorRail } from "@/components/feature/DirectorRail";
import { Composer } from "@/components/feature/Composer";
import { SceneLoader } from "@/components/feature/SceneLoader";
import { TranscriptBeat } from "@/components/feature/TranscriptBeat";
import { CharacterProfileModal } from "@/components/feature/CharacterProfileModal";

/** The signature surface: a three-zone "open book" live scene. */
export function StoryPlayerView({ scenario }: { scenario: ResolvedScenario }) {
  const scene = useScenePlay(scenario);
  const scrollRef = useRef<HTMLDivElement>(null);
  const byId = (id: string): Character | undefined =>
    scenario.cast.find((c) => c.id === id);

  // Keep the transcript pinned to the latest beat.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [scene.messages.length, scene.reveal]);

  const profileChar = scene.profileId ? (byId(scene.profileId) ?? null) : null;

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <h1 className="sr-only">{scenario.title} — live scene</h1>
      <SceneHeader title={scenario.title} settingName={scenario.setting.name} />

      <div className="flex min-h-0 flex-1">
        <CastRail
          cast={scenario.cast}
          speakingId={scene.speakingId}
          turnOrder={scene.turnOrder}
          charById={byId}
          onProfile={scene.openProfile}
        />

        <div className="flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="min-h-0 flex-1 overflow-auto p-[20px_16px_10px] sm:p-[24px_30px_10px]">
            <div
              className="mx-auto flex max-w-[720px] flex-col gap-4 transition-[opacity,transform] duration-[550ms]"
              style={{
                opacity: scene.reveal ? 1 : 0,
                transform: scene.reveal ? "none" : "translateY(14px)",
              }}
              aria-live="polite"
              aria-relevant="additions"
              aria-busy={!scene.reveal}
            >
              <div className="py-[4px] text-center font-mono text-[9px] tracking-[0.16em] text-mute2 uppercase">
                — the scene is joined —
              </div>
              {scene.messages.map((m, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25, ease: "easeOut" }}
                >
                  <TranscriptBeat
                    message={m}
                    charById={byId}
                    onProfile={scene.openProfile}
                    choices={scene.choices}
                    onChoose={scene.choose}
                  />
                </motion.div>
              ))}
            </div>
          </div>
          <Composer
            value={scene.composer}
            onChange={scene.setComposer}
            onSend={scene.send}
            onRoll={scene.roll}
          />
        </div>

        <DirectorRail
          goal={scenario.goal}
          tension={scene.tension}
          tensionText={tensionLabel(scene.tension)}
          stats={scene.stats}
          relationships={scene.relationships}
        />
      </div>

      <SceneLoader title={scenario.title} visible={scene.loading} />
      <CharacterProfileModal character={profileChar} onClose={scene.closeProfile} />
    </div>
  );
}
