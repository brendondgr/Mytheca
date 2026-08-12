"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * How close to the bottom still counts as "at the bottom".
 *
 * Never test for exact equality: sub-pixel scroll positions, zoom levels, and
 * a growing last line all leave a few pixels of slack, and an exact test would
 * silently drop stickiness the moment the transcript grew.
 */
const AT_BOTTOM_TOLERANCE_PX = 64;

export interface StickyBottom {
  /** Attach to the scrolling viewport. */
  ref: React.RefObject<HTMLDivElement | null>;
  /**
   * True when the reader has scrolled away from the live edge. Drives the
   * "Jump to latest" affordance — the escape hatch that makes it safe to stop
   * following.
   */
  detached: boolean;
  /** Return to the live edge and resume following. */
  jumpToLatest: () => void;
}

/**
 * Keep a streaming transcript pinned to its newest content — but only while
 * the reader is already there.
 *
 * The story player previously ran `el.scrollTop = el.scrollHeight` on every new
 * beat, unconditionally. Scroll up to re-read a line and the next token yanked
 * you back to the bottom; there was no way to read the middle of a scene while
 * it was still being written. It is the single most disliked behaviour in chat
 * UIs and this app had it in its purest form.
 *
 * The rule: follow while the reader is at the bottom, stop the instant they
 * scroll away, and offer an explicit way back. Their scroll position is theirs.
 *
 * @param deps Values whose change means new content arrived (message count,
 *             streaming text length, reveal state).
 */
export function useStickyBottom(deps: unknown[]): StickyBottom {
  const ref = useRef<HTMLDivElement>(null);
  // Following is the default: a scene opens at its newest beat.
  const stickingRef = useRef(true);
  const [detached, setDetached] = useState(false);

  const isAtBottom = useCallback((el: HTMLElement) => {
    return el.scrollHeight - el.scrollTop - el.clientHeight <= AT_BOTTOM_TOLERANCE_PX;
  }, []);

  // Watch the reader, not the content. Any scroll that leaves the bottom
  // detaches; scrolling back re-attaches, so returning to the live edge by
  // hand works exactly like pressing the pill.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const onScroll = () => {
      const atBottom = isAtBottom(el);
      stickingRef.current = atBottom;
      setDetached(!atBottom);
    };

    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [isAtBottom]);

  // New content: follow it only if we were already following.
  //
  // The dependency array is the caller's `deps` verbatim, which the exhaustive-
  // deps rule cannot statically verify — it only knows how to read an array
  // literal. That is the point of the hook: the caller names which values mean
  // "new content arrived", because only they know (message count, reveal
  // state), and this effect is deliberately keyed on exactly those.
  useEffect(() => {
    const el = ref.current;
    if (!el || !stickingRef.current) return;
    el.scrollTop = el.scrollHeight;
  }, deps);

  const jumpToLatest = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    stickingRef.current = true;
    setDetached(false);
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, []);

  return { ref, detached, jumpToLatest };
}
