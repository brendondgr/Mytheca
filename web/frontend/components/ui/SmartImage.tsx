"use client";

import { useCallback, useState } from "react";
import { cn } from "@/lib/cn";

/**
 * An image that reserves its space, fades in when it arrives, and shows
 * something calm while it does not exist yet.
 *
 * Images are the most common source of layout jank, and Mytheca's are the worst
 * case: portraits and scene art are generated on demand and served from the
 * backend's `/media` mount, so they arrive late and at unpredictable speeds.
 *
 * Three things this gets right that a bare `<img>` does not:
 *
 * 1. **Space is reserved** by a required `aspect` on the frame, so nothing
 *    below the image moves when it lands.
 * 2. **Cached images still appear.** The `load` event does not fire for an
 *    image already in the cache when React attaches the handler, so a
 *    fade-in keyed only to `onLoad` leaves cached images permanently invisible.
 *    This checks `img.complete` on mount. It is the single most common bug in
 *    hand-rolled image fade-ins.
 * 3. **A failed load is a state, not a broken glyph** — the frame keeps its
 *    placeholder rather than showing the browser's torn-page icon.
 */
interface SmartImageBaseProps {
  src: string | null | undefined;
  /**
   * Required, and required to be *meaningful*. Decorative images should pass
   * `""` explicitly — an omitted alt is an oversight, an empty one is a
   * decision.
   */
  alt: string;
  className?: string;
  imgClassName?: string;
  /** Shown before the image arrives, and if it never does (e.g. a monogram). */
  placeholder?: React.ReactNode;
  /**
   * Set on the LCP image only. Loads eagerly and decodes synchronously —
   * lazy-loading the largest above-the-fold image is a direct LCP regression.
   */
  priority?: boolean;
  objectFit?: "cover" | "contain";
}

/**
 * The two ways an image can be sized, as a union so they cannot be mixed up.
 *
 * This used to be a single required `aspect`, and every full-bleed caller
 * worked around it by passing `className="absolute inset-0"`. That silently did
 * not work: `cn` is a plain string joiner, so the element carried BOTH
 * `relative` (from this component) and `absolute` (from the caller), and
 * Tailwind emits `.relative` after `.absolute`, so `relative` won. The frames
 * became in-flow blocks sitting *above* the text they were supposed to sit
 * behind. Making the choice explicit is what stops that recurring.
 */
export type SmartImageProps = SmartImageBaseProps &
  (
    | {
        /**
         * The image is the background of a box its PARENT already sizes — a
         * card, a hero panel, a loader backdrop. The frame is `absolute
         * inset-0`, so the text layered over it is unaffected.
         */
        fill: true;
        aspect?: never;
      }
    | {
        /**
         * CSS aspect-ratio for the frame, e.g. `"2 / 3"` or `"16 / 9"`. The
         * frame reserves this space in normal flow, so nothing below it moves
         * when the image lands.
         */
        aspect: string;
        fill?: false;
      }
  );

export function SmartImage({
  src,
  alt,
  aspect,
  fill = false,
  className,
  imgClassName,
  placeholder,
  priority = false,
  objectFit = "cover",
}: SmartImageProps) {
  const [state, setState] = useState<"pending" | "loaded" | "failed">("pending");
  const [renderedSrc, setRenderedSrc] = useState(src);

  const markLoaded = useCallback(() => setState("loaded"), []);
  const markFailed = useCallback(() => setState("failed"), []);

  // A new `src` on an already-mounted <img> always fires `load` again, even
  // from cache, so resetting to pending during render is enough here.
  if (renderedSrc !== src) {
    setRenderedSrc(src);
    setState("pending");
  }

  /**
   * The cached-image fix, done in the ref callback rather than an effect.
   *
   * On first mount the browser may have finished the image before React
   * attaches `onLoad` — that event then never fires, and an image keyed only
   * to it stays invisible forever. The ref callback runs at commit, the moment
   * the element exists, which is the earliest point `complete` can be read.
   * `naturalWidth` separates a genuinely decoded image from one that
   * "completed" by failing.
   */
  const attachImg = useCallback((img: HTMLImageElement | null) => {
    if (img?.complete) setState(img.naturalWidth > 0 ? "loaded" : "failed");
  }, []);

  return (
    <span
      // In `fill` mode the parent owns the box, so the frame is absolutely
      // positioned and carries no aspect-ratio of its own. Positioning is
      // decided HERE rather than being passed in, because a caller-supplied
      // `absolute` cannot beat a hardcoded `relative` — same specificity, and
      // Tailwind emits `.relative` last.
      className={cn(
        "block overflow-hidden",
        fill ? "absolute inset-0" : "relative",
        className,
      )}
      style={fill ? undefined : { aspectRatio: aspect }}
    >
      {/* The placeholder stays mounted underneath rather than being swapped
       * out, so the frame is never empty for a frame between the two. */}
      {state !== "loaded" ? (
        <span className="absolute inset-0 flex items-center justify-center">
          {placeholder ?? <span className="skeleton block h-full w-full" />}
        </span>
      ) : null}

      {src ? (
        // eslint-disable-next-line @next/next/no-img-element -- generated portrait/scene art from our own media mount; next/image's optimizer would have to round-trip to the backend for files we already serve at their final size
        <img
          ref={attachImg}
          src={src}
          alt={alt}
          onLoad={markLoaded}
          onError={markFailed}
          loading={priority ? "eager" : "lazy"}
          decoding={priority ? "sync" : "async"}
          data-loaded={state === "loaded" ? "true" : undefined}
          className={cn(
            "absolute inset-0 h-full w-full",
            objectFit === "cover" ? "object-cover" : "object-contain",
            "opacity-0 transition-opacity duration-base ease-out data-[loaded=true]:opacity-100",
            imgClassName,
          )}
        />
      ) : null}
    </span>
  );
}
