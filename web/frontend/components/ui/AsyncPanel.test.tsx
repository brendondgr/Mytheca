import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";
import { act } from "react";
import { AsyncPanel } from "./AsyncPanel";
import { INDICATOR_DELAY_MS } from "@/hooks/use-delayed-flag";

afterEach(() => vi.useRealTimers());

function Panel(props: Partial<React.ComponentProps<typeof AsyncPanel>>) {
  return (
    <AsyncPanel
      status="success"
      skeleton={<p>placeholder</p>}
      label="Scenarios"
      {...props}
    >
      <p>Two scenarios</p>
    </AsyncPanel>
  );
}

describe("AsyncPanel", () => {
  it("renders success content", () => {
    render(<Panel status="success" />);
    expect(screen.getByText("Two scenarios")).toBeInTheDocument();
  });

  it("shows no indicator at all for a wait under the delay gate", () => {
    vi.useFakeTimers();
    render(<Panel status="loading" />);
    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS - 1));
    // The fast path must stay visually still: a placeholder that flashes and
    // vanishes reads as a stutter, not as speed.
    expect(screen.queryByText("placeholder")).not.toBeInTheDocument();
  });

  it("shows the skeleton once the wait is perceptible", () => {
    vi.useFakeTimers();
    render(<Panel status="loading" />);
    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS));
    expect(screen.getByText("placeholder")).toBeInTheDocument();
  });

  it("names what failed and offers a retry", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(
      <Panel
        status="error"
        errorTitle="The library didn't load"
        errorMessage="The server didn't answer."
        onRetry={onRetry}
      />,
    );

    // Never a bare "Something went wrong": the message says what failed, and
    // the control makes the failure recoverable instead of a dead end.
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("The library didn't load");
    expect(alert).toHaveTextContent("The server didn't answer.");

    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("makes the empty state an invitation, with the action inline", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <Panel
        status="empty"
        emptyTitle="No scenarios yet"
        emptyMessage="A scenario is a scene your cast can play."
        emptyAction={{ label: "New Scenario", onClick }}
      />,
    );

    expect(screen.getByText("No scenarios yet")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "New Scenario" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("treats an empty result as its own state, not as success", () => {
    render(<Panel status="empty" emptyTitle="No scenarios yet" />);
    // If `empty` collapsed into `success` the panel would render the success
    // children over a zero-length list — which is how panels end up blank.
    expect(screen.queryByText("Two scenarios")).not.toBeInTheDocument();
  });

  it("gives a stalled load an error with a retry, not an endless shimmer", () => {
    vi.useFakeTimers();
    const onRetry = vi.fn();
    render(<Panel status="loading" onRetry={onRetry} />);

    act(() => void vi.advanceTimersByTime(INDICATOR_DELAY_MS));
    expect(screen.getByText("placeholder")).toBeInTheDocument();

    act(() => void vi.advanceTimersByTime(12_000));
    expect(screen.getByText(/taking longer than it should/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
