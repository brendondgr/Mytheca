import { render, screen, act, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useStickyBottom } from "./use-sticky-bottom";

/** A scroller whose geometry we control, since jsdom does no layout. */
function Fixture({ beats }: { beats: number }) {
  const { ref, detached, jumpToLatest } = useStickyBottom([beats]);
  return (
    <div>
      <div data-testid="viewport" ref={ref} />
      <span data-testid="detached">{String(detached)}</span>
      <button type="button" onClick={jumpToLatest}>
        Jump to latest
      </button>
    </div>
  );
}

/** jsdom reports 0 for every layout box, so the geometry is installed by hand. */
function setGeometry(el: HTMLElement, scrollHeight: number, clientHeight: number, scrollTop: number) {
  Object.defineProperty(el, "scrollHeight", { configurable: true, value: scrollHeight });
  Object.defineProperty(el, "clientHeight", { configurable: true, value: clientHeight });
  el.scrollTop = scrollTop;
}

describe("useStickyBottom", () => {
  it("follows new beats while the reader is at the bottom", () => {
    const { rerender } = render(<Fixture beats={1} />);
    const viewport = screen.getByTestId("viewport");
    setGeometry(viewport, 1000, 400, 600); // exactly at the bottom

    rerender(<Fixture beats={2} />);
    expect(viewport.scrollTop).toBe(1000);
  });

  it("does NOT follow when the reader has scrolled up to re-read", () => {
    const { rerender } = render(<Fixture beats={1} />);
    const viewport = screen.getByTestId("viewport");

    // 400px up from the live edge — well past the 64px tolerance.
    setGeometry(viewport, 1000, 400, 200);
    act(() => void fireEvent.scroll(viewport));

    rerender(<Fixture beats={2} />);
    // This is the whole point: the position stays where the reader put it.
    // Yanking it back is the most disliked behaviour in a streaming chat UI,
    // and the story player did it on every single beat.
    expect(viewport.scrollTop).toBe(200);
    expect(screen.getByTestId("detached")).toHaveTextContent("true");
  });

  it("treats 'near the bottom' as at the bottom", () => {
    const { rerender } = render(<Fixture beats={1} />);
    const viewport = screen.getByTestId("viewport");

    // 40px of slack: sub-pixel positions, zoom, and a growing last line all
    // leave a few pixels, so an exact test would silently drop stickiness.
    setGeometry(viewport, 1000, 400, 560);
    act(() => void fireEvent.scroll(viewport));
    expect(screen.getByTestId("detached")).toHaveTextContent("false");

    rerender(<Fixture beats={2} />);
    expect(viewport.scrollTop).toBe(1000);
  });

  it("re-attaches when the reader scrolls back down by hand", () => {
    render(<Fixture beats={1} />);
    const viewport = screen.getByTestId("viewport");

    setGeometry(viewport, 1000, 400, 100);
    act(() => void fireEvent.scroll(viewport));
    expect(screen.getByTestId("detached")).toHaveTextContent("true");

    setGeometry(viewport, 1000, 400, 600);
    act(() => void fireEvent.scroll(viewport));
    expect(screen.getByTestId("detached")).toHaveTextContent("false");
  });

  it("returns to the live edge on demand", () => {
    render(<Fixture beats={1} />);
    const viewport = screen.getByTestId("viewport");
    let scrolledTo: number | null = null;
    viewport.scrollTo = ((opts: ScrollToOptions) => {
      scrolledTo = opts.top ?? null;
    }) as HTMLElement["scrollTo"];

    setGeometry(viewport, 1000, 400, 100);
    act(() => void fireEvent.scroll(viewport));
    expect(screen.getByTestId("detached")).toHaveTextContent("true");

    act(() => void screen.getByRole("button", { name: "Jump to latest" }).click());
    expect(scrolledTo).toBe(1000);
    expect(screen.getByTestId("detached")).toHaveTextContent("false");
  });
});
