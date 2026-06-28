import { Eyebrow } from "@/components/ui/Eyebrow";

/** Full-screen "conjuring the scene" loader (❖ spinner → content reveal). */
export function SceneLoader({
  title,
  visible,
}: {
  title: string;
  visible: boolean;
}) {
  if (!visible) return null;
  return (
    <div
      role="status"
      aria-label="Loading the scene"
      className="velora-page fixed inset-0 z-[80] flex flex-col items-center justify-center gap-6"
    >
      <div className="relative h-[62px] w-[62px]">
        <div className="absolute inset-0 animate-[embSpin_1s_linear_infinite] rounded-full border-[3px] border-cardbd border-t-accent motion-reduce:animate-none" />
        <div className="absolute inset-0 flex items-center justify-center text-[22px] text-accent">
          ❖
        </div>
      </div>
      <div className="text-center">
        <Eyebrow tracking="0.22em" color="#A8762A" className="mb-[9px] block">
          Entering Embergate
        </Eyebrow>
        <div className="font-display text-[24px] font-bold tracking-[0.03em] text-ink">
          {title}
        </div>
        <div className="mt-[11px] font-mono text-[10px] tracking-[0.16em] text-mute uppercase">
          Conjuring the scene
          <span className="animate-[embDots_1.4s_infinite] motion-reduce:hidden">.</span>
          <span className="animate-[embDots_1.4s_infinite_.2s] motion-reduce:hidden">.</span>
          <span className="animate-[embDots_1.4s_infinite_.4s] motion-reduce:hidden">.</span>
        </div>
      </div>
    </div>
  );
}
