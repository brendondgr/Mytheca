import { Spinner } from "@/components/ui/Spinner";

/**
 * The route-level loading fallback.
 *
 * There was none, so every page rendered its own loader from scratch and a slow
 * segment showed nothing at all until it resolved. This is the floor beneath
 * those — a surface with a better-informed skeleton still ships one, and gets
 * this only for the gap before its own code has loaded.
 *
 * `aria-live="polite"` with the text already in the DOM, not injected later: a
 * live region created at the same moment its content arrives was never
 * observed and announces nothing.
 */
export default function Loading() {
  return (
    <div
      className="flex min-h-[50dvh] flex-1 flex-col items-center justify-center gap-md"
      role="status"
      aria-live="polite"
    >
      <Spinner />
      <p className="font-mono text-eyebrow tracking-[0.18em] text-mute uppercase">
        Loading…
      </p>
    </div>
  );
}
