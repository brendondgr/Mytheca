import * as React from "react";
import { renderToString } from "react-dom/server";
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useHydrated } from "./use-hydrated";

function Probe() {
  return <span data-testid="probe">{String(useHydrated())}</span>;
}

describe("useHydrated", () => {
  it("is false on the server", () => {
    // The server snapshot is what decides the SSR output. If this ever returned
    // true, a portal gated on it would render markup into the HTML that the
    // server cannot actually produce.
    expect(renderToString(<Probe />)).toContain("false");
  });

  it("is true on the client", () => {
    render(<Probe />);
    expect(screen.getByTestId("probe")).toHaveTextContent("true");
  });
});

describe("portal hydration contract", () => {
  it("a portal gated on useHydrated renders nothing server-side", () => {
    // This is the regression under test. `Toast` portals its container into
    // document.body unconditionally so AnimatePresence can animate the LAST
    // toast out — which means that without a gate, the first client render
    // inserts a <body> child the server HTML does not contain, and React
    // reports a hydration mismatch and regenerates the tree.
    function GatedPortal() {
      const hydrated = useHydrated();
      if (!hydrated) return null;
      return <div data-testid="portal-container" />;
    }
    expect(renderToString(<GatedPortal />)).toBe("");
  });
});
