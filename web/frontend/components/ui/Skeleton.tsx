"use client";

import { useEffect, useState } from "react";
import { cn } from "@/lib/cn";

/**
 * How long a skeleton may shimmer before it is treated as a failure.
 *
 * A loop with no ceiling hides a dead request indefinitely — the user watches
 * a confident animation that means nothing. Every skeleton therefore has a
 * deadline, after which the caller is expected to show an error with a retry.
 */
export const SKELETON_TIMEOUT_MS = 12_000;

/**
 * A single placeholder bar.
 *
 * `aria-hidden` on purpose: the bars are decoration standing in for content
 * that does not exist yet, and announcing "blank blank blank" is worse than
 * silence. The *container* carries `aria-busy="true"` instead, which is the
 * thing assistive tech actually needs to know.
 */
export function SkeletonLine({
  width = "100%",
  height = "0.85em",
  className,
}: {
  width?: string | number;
  height?: string | number;
  className?: string;
}) {
  return (
    <span
      aria-hidden="true"
      className={cn("skeleton block", className)}
      style={{ width, height }}
    />
  );
}

/**
 * A block of placeholder text.
 *
 * The last line runs short (55–70%), because real prose does. Uniform-width
 * bars are the single clearest tell that a skeleton is fake, and a skeleton
 * that reads as fake buys none of the perceived-speed it exists for.
 */
export function SkeletonText({
  lines = 3,
  className,
  lineClassName,
}: {
  lines?: number;
  className?: string;
  lineClassName?: string;
}) {
  return (
    <span aria-hidden="true" className={cn("flex flex-col gap-xs", className)}>
      {Array.from({ length: lines }, (_, i) => (
        <SkeletonLine
          key={i}
          width={i === lines - 1 ? "62%" : "100%"}
          className={lineClassName}
        />
      ))}
    </span>
  );
}

/** A placeholder for a rectangular region — an image frame, a chart, a canvas. */
export function SkeletonBlock({
  className,
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return <span aria-hidden="true" className={cn("skeleton block", className)} style={style} />;
}

/**
 * Wraps a skeleton and enforces its deadline.
 *
 * While loading it renders the placeholder with `aria-busy="true"`. If the wait
 * outlives `timeoutMs` it renders `onTimeout` instead — which callers pass as
 * the same error-with-retry they would show for an explicit failure, so a
 * request that simply never answers is not a nicer experience than one that
 * fails outright.
 */
export function Skeleton({
  loading,
  children,
  fallback,
  onTimeout,
  timeoutMs = SKELETON_TIMEOUT_MS,
  className,
  label,
}: {
  /** Whether the real content is still on its way. */
  loading: boolean;
  /** The real content, shown once `loading` is false. */
  children: React.ReactNode;
  /** The placeholder tracing of that content. */
  fallback: React.ReactNode;
  /** Shown if the wait outlives `timeoutMs`. Omit to keep waiting forever. */
  onTimeout?: React.ReactNode;
  timeoutMs?: number;
  className?: string;
  /** Describes what is loading, e.g. "Loading your library". */
  label?: string;
}) {
  const [timedOut, setTimedOut] = useState(false);
  const [wasLoading, setWasLoading] = useState(loading);

  if (wasLoading !== loading) {
    setWasLoading(loading);
    if (!loading) setTimedOut(false);
  }

  // The dependency is the *presence* of a timeout state, not the node itself:
  // `onTimeout` is JSX and gets a fresh identity on every parent render, so
  // depending on it would restart the deadline continuously and the timeout
  // would never fire on any actively-rendering page.
  const hasTimeoutState = Boolean(onTimeout);
  useEffect(() => {
    if (!loading || !hasTimeoutState) return;
    const timer = window.setTimeout(() => setTimedOut(true), timeoutMs);
    return () => window.clearTimeout(timer);
  }, [loading, hasTimeoutState, timeoutMs]);

  if (loading && timedOut && onTimeout) {
    return <div className={className}>{onTimeout}</div>;
  }

  if (loading) {
    return (
      <div className={className} aria-busy="true" aria-label={label}>
        {fallback}
      </div>
    );
  }

  // Cross-fade rather than hard-cut: the swap is where the polish is won or
  // lost, and a hard cut makes even a fast load feel like a jolt.
  return <div className={cn("content-enter", className)}>{children}</div>;
}
