"use client";

import Link from "next/link";
import { Eyebrow } from "@/components/ui/Eyebrow";
import { Button } from "@/components/ui/Button";
import { useSceneData } from "./useSceneData";
import { StoryPlayerView } from "./StoryPlayerView";

/**
 * Route entry for the live scene: loads the scenario's real data from the
 * backend (cast + portraits, setting + scene art, stat schema) and renders the
 * player, with loading + error states. The page (`app/[storylineId]/
 * [scenarioId]/page.tsx`) stays a thin server component that passes the ids.
 */
export function StoryPlayerRoute({
  storylineId,
  scenarioId,
  backHref = "/",
}: {
  storylineId: string;
  scenarioId: string;
  backHref?: string;
}) {
  const scene = useSceneData(storylineId, scenarioId);

  if (scene.status === "loading") {
    return (
      <div
        role="status"
        aria-label="Loading the scene"
        className="mytheca-page flex min-h-dvh flex-1 flex-col items-center justify-center gap-5"
      >
        <div className="relative h-[54px] w-[54px]">
          <div className="absolute inset-0 animate-[embSpin_1s_linear_infinite] rounded-full border-[3px] border-cardbd border-t-accent motion-reduce:animate-none" />
          <div className="absolute inset-0 flex items-center justify-center text-[20px] text-accent">
            ❖
          </div>
        </div>
        <div className="font-mono text-[10px] tracking-[0.18em] text-mute uppercase">
          Summoning the scene
          <span className="animate-[embDots_1.4s_infinite] motion-reduce:hidden">.</span>
          <span className="animate-[embDots_1.4s_infinite_.2s] motion-reduce:hidden">.</span>
          <span className="animate-[embDots_1.4s_infinite_.4s] motion-reduce:hidden">.</span>
        </div>
      </div>
    );
  }

  if (scene.status === "error") {
    return (
      <div className="mytheca-page flex min-h-dvh flex-1 flex-col items-center justify-center gap-5 p-6 text-center">
        <div className="max-w-[420px]">
          <Eyebrow tracking="0.2em" color="var(--danger)" className="block">
            The scene could not be raised
          </Eyebrow>
          <p className="mt-[10px] font-body text-[15px] leading-[1.5] text-ink-soft">
            {scene.message}
          </p>
          <div className="mt-[18px] flex items-center justify-center gap-[10px]">
            <Button onClick={scene.reload}>Try again</Button>
            <Link
              href={backHref}
              className="rounded-[2px] border border-field-bd px-[16px] py-[9px] font-mono text-[10px] tracking-[0.1em] text-accent uppercase hover:bg-accent hover:text-[#F6ECDA]"
            >
              ‹ Library
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <StoryPlayerView
      scenario={scene.scenario}
      statDefs={scene.statDefs}
      storylineName={scene.storylineName}
      contextDocs={scene.contextDocs}
      storylineCast={scene.storylineCast}
      backHref={backHref}
    />
  );
}
