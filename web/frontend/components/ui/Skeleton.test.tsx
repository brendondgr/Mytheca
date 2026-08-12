import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { act } from "react";
import { Skeleton, SkeletonText, SkeletonLine } from "./Skeleton";

afterEach(() => vi.useRealTimers());

describe("SkeletonText", () => {
  it("runs its last line short, because real prose does", () => {
    const { container } = render(<SkeletonText lines={3} />);
    const bars = container.querySelectorAll(".skeleton");
    expect(bars).toHaveLength(3);
    expect((bars[0] as HTMLElement).style.width).toBe("100%");
    expect((bars[1] as HTMLElement).style.width).toBe("100%");
    // Uniform-width bars are the clearest tell that a skeleton is fake, and a
    // skeleton that reads as fake buys none of the perceived speed it exists
    // for.
    expect((bars[2] as HTMLElement).style.width).toBe("62%");
  });

  it("hides the bars from assistive tech", () => {
    const { container } = render(<SkeletonLine />);
    // Announcing "blank blank blank" is worse than silence; the container's
    // aria-busy is what AT actually needs.
    expect(container.querySelector(".skeleton")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("Skeleton", () => {
  it("marks the container busy while the placeholder is up", () => {
    render(
      <Skeleton loading fallback={<SkeletonText lines={2} />} label="Loading scenarios">
        <p>Real content</p>
      </Skeleton>,
    );
    expect(screen.getByLabelText("Loading scenarios")).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText("Real content")).not.toBeInTheDocument();
  });

  it("swaps to the real content when the wait ends", () => {
    const { rerender } = render(
      <Skeleton loading fallback={<SkeletonText />}>
        <p>Real content</p>
      </Skeleton>,
    );
    rerender(
      <Skeleton loading={false} fallback={<SkeletonText />}>
        <p>Real content</p>
      </Skeleton>,
    );
    expect(screen.getByText("Real content")).toBeInTheDocument();
    // Cross-fade, not a hard cut — the swap is where polish is won or lost.
    expect(screen.getByText("Real content").parentElement).toHaveClass("content-enter");
  });

  it("times out into an error rather than shimmering forever", () => {
    vi.useFakeTimers();
    render(
      <Skeleton
        loading
        timeoutMs={5000}
        fallback={<SkeletonText />}
        onTimeout={<p>The library never arrived. Try again?</p>}
      >
        <p>Real content</p>
      </Skeleton>,
    );

    act(() => void vi.advanceTimersByTime(4999));
    expect(screen.queryByText(/never arrived/)).not.toBeInTheDocument();

    // A shimmer with no ceiling hides a dead request indefinitely: the user
    // watches a confident animation that means nothing.
    act(() => void vi.advanceTimersByTime(1));
    expect(screen.getByText(/never arrived/)).toBeInTheDocument();
  });

  it("keeps waiting when the caller supplies no timeout state", () => {
    vi.useFakeTimers();
    render(
      <Skeleton loading fallback={<p>placeholder</p>}>
        <p>Real content</p>
      </Skeleton>,
    );
    act(() => void vi.advanceTimersByTime(120_000));
    expect(screen.getByText("placeholder")).toBeInTheDocument();
  });
});
