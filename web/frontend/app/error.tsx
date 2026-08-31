"use client";

import { useEffect } from "react";
import { Page, Stack } from "@/components/ui/Page";

/**
 * The route-level error boundary.
 *
 * Without one, a throw anywhere in a route subtree escalated to the global
 * boundary and replaced the whole themed shell with Next's stock error page.
 * This keeps the failure inside the frame and — importantly — offers `reset()`,
 * so a transient fetch failure does not cost the user their navigation.
 *
 * The message is deliberately NOT `error.message`: those are stack-shaped and
 * often carry internals. The digest is shown instead, because it is the thing
 * that matches a server log line.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // The boundary swallows it otherwise, and a silent boundary is how a
    // reproducible bug becomes an unreproducible one.
    console.error("Route error:", error);
  }, [error]);

  return (
    <Page measure="prose" className="flex items-center justify-center">
      <Stack gap="lg" className="text-center">
        <p className="font-mono text-eyebrow tracking-[0.2em] text-mute uppercase">
          Something broke
        </p>
        <h1 className="font-display text-step-2 font-bold text-ink">
          This page could not be rendered
        </h1>
        <p className="font-body text-body text-ink-soft">
          The rest of Mytheca is unaffected. Try again — if it persists, the
          backend log will carry the matching entry.
        </p>
        {error.digest ? (
          <p className="font-mono text-eyebrow tracking-[0.1em] text-mute">
            digest {error.digest}
          </p>
        ) : null}
        <div className="flex flex-wrap justify-center gap-sm">
          <button
            type="button"
            onClick={reset}
            className="inline-flex items-center rounded-xs border border-accent bg-accent px-md py-sm font-mono text-ui tracking-[0.1em] text-on-accent uppercase hover:bg-accent-hover"
          >
            Try again
          </button>
          {/* A raw anchor, deliberately, and the one place in the app that is
              correct. `next/link` performs a CLIENT-side navigation through the
              same router that just threw; if the fault is in router or shell
              state, that navigation re-enters the broken tree and lands the user
              right back here. A document load rebuilds everything from scratch,
              which is the actual escape hatch this button is for. */}
          {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
          <a
            href="/"
            className="inline-flex items-center rounded-xs border border-field-bd px-md py-sm font-mono text-ui tracking-[0.1em] text-accent uppercase hover:bg-accent hover:text-on-accent"
          >
            Back to the Library
          </a>
        </div>
      </Stack>
    </Page>
  );
}
