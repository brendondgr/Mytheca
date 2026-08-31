"use client";

import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { useDelayedFlag } from "@/hooks/use-delayed-flag";

/**
 * Which of the five states an async region is in.
 *
 * `empty` is not a flavour of `success` — a zero-length list needs different
 * copy and a different affordance from a populated one, and collapsing the two
 * is how panels end up rendering nothing at all.
 */
export type AsyncStatus = "idle" | "loading" | "success" | "error" | "empty";

export interface AsyncPanelProps {
  status: AsyncStatus;
  children: React.ReactNode;

  /**
   * The placeholder tracing of the incoming layout. A skeleton must mirror the
   * real thing — same line count, widths, gaps, radii — because the instant
   * real content lands in a different shape, the user learns the placeholder
   * was a lie.
   */
  skeleton?: React.ReactNode;

  /** What failed, in the interface's voice. Never "Something went wrong." */
  errorTitle?: string;
  errorMessage?: string;
  /** Without this the error is a dead end; with it, it is a hiccup. */
  onRetry?: () => void;
  retryLabel?: string;

  /** An invitation to act, not a blank panel. */
  emptyTitle?: string;
  emptyMessage?: string;
  /** The primary action, inline — the whole point of an empty state. */
  emptyAction?: { label: string; onClick: () => void };

  className?: string;
  /** Describes the region for assistive tech, e.g. "Scenarios". */
  label?: string;
}

/**
 * The five rendered states every async region owes the user.
 *
 * A component that renders only its success state is not finished; it just
 * looks finished on a fast connection with good data. This shell makes the
 * other four impossible to forget, and gives them a consistent voice.
 *
 * Loading is gated by `useDelayedFlag`, so a fast response shows no indicator
 * at all — the fastest loading state is the one that never appears. Error and
 * empty enter with the same `.content-enter` animation as success, so a
 * failure reads as part of the system rather than as a crash.
 */
export function AsyncPanel({
  status,
  children,
  skeleton,
  errorTitle = "That didn't load",
  errorMessage,
  onRetry,
  retryLabel = "Try again",
  emptyTitle,
  emptyMessage,
  emptyAction,
  className,
  label,
}: AsyncPanelProps) {
  const showLoading = useDelayedFlag(status === "loading");

  if (status === "error") {
    return (
      <div className={cn("content-enter", className)} role="alert">
        <StatePanel title={errorTitle} message={errorMessage} tone="error">
          {onRetry ? (
            <Button variant="secondary" onClick={onRetry}>
              {retryLabel}
            </Button>
          ) : null}
        </StatePanel>
      </div>
    );
  }

  if (status === "empty") {
    return (
      <div className={cn("content-enter", className)}>
        <StatePanel title={emptyTitle ?? "Nothing here yet"} message={emptyMessage}>
          {emptyAction ? (
            <Button variant="secondary" onClick={emptyAction.onClick}>
              {emptyAction.label}
            </Button>
          ) : null}
        </StatePanel>
      </div>
    );
  }

  if (status === "loading" || status === "idle") {
    // Nothing at all until the wait is perceptible. `idle` renders the same
    // nothing: work that has not started has no news to report.
    if (!showLoading || !skeleton) {
      return <div className={className} aria-busy={status === "loading" || undefined} />;
    }
    return (
      <Skeleton
        loading
        className={className}
        label={label ? `Loading ${label.toLowerCase()}` : undefined}
        fallback={skeleton}
        onTimeout={
          <StatePanel
            title="This is taking longer than it should"
            message={
              label
                ? `${label} still hasn't arrived. The server may be busy or unreachable.`
                : "The server may be busy or unreachable."
            }
            tone="error"
          >
            {onRetry ? (
              <Button variant="secondary" onClick={onRetry}>
                {retryLabel}
              </Button>
            ) : null}
          </StatePanel>
        }
      >
        {children}
      </Skeleton>
    );
  }

  return <div className={cn("content-enter", className)}>{children}</div>;
}

/** The shared frame for the error and empty states, so both read as designed. */
function StatePanel({
  title,
  message,
  tone = "neutral",
  children,
}: {
  title: string;
  message?: string;
  tone?: "neutral" | "error";
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-start gap-sm rounded-sm border border-cardbd bg-card p-lg">
      <p
        className={cn(
          "font-display text-body-sm font-semibold",
          tone === "error" ? "text-danger-ink" : "text-ink",
        )}
      >
        {/* The seal, not a warning triangle — the tone stays in the manuscript
         * even when something has gone wrong. Meaning never rests on the
         * colour alone: the title text says what happened. */}
        <span aria-hidden className="mr-xs text-gold-ink">
          ❖
        </span>
        {title}
      </p>
      {message ? (
        <p className="font-body text-body-sm leading-[1.5] text-ink-soft">{message}</p>
      ) : null}
      {children}
    </div>
  );
}
