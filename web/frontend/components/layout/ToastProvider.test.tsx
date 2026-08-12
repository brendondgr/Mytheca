import { describe, it, expect, vi } from "vitest";
import {
  render,
  screen,
  act,
  waitFor,
  waitForElementToBeRemoved,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToastProvider, useToast, type NotifyInput } from "./ToastProvider";

/**
 * Toasts animate OUT via `AnimatePresence`, so a dismissed toast stays in the
 * DOM for the length of its exit. Every removal assertion therefore waits
 * rather than checking synchronously — asserting immediately would be asserting
 * that the exit animation does not exist.
 */

/** A tiny consumer that raises a toast on demand. */
function Harness({ input }: { input: NotifyInput }) {
  const { notify } = useToast();
  return (
    <button type="button" onClick={() => notify(input)}>
      raise
    </button>
  );
}

function renderWith(input: NotifyInput) {
  return render(
    <ToastProvider>
      <Harness input={input} />
    </ToastProvider>,
  );
}

describe("ToastProvider / Toast", () => {
  it("renders an error toast with role=alert and a dismiss control", async () => {
    const user = userEvent.setup();
    renderWith({ message: "Draft failed", variant: "error", durationMs: 0 });

    await user.click(screen.getByRole("button", { name: "raise" }));
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("Draft failed");

    await user.click(screen.getByRole("button", { name: "Dismiss notification" }));
    await waitForElementToBeRemoved(() => screen.queryByRole("alert"));
  });

  it("renders an info toast as role=status", async () => {
    const user = userEvent.setup();
    renderWith({ message: "Working…", variant: "info", durationMs: 0 });

    await user.click(screen.getByRole("button", { name: "raise" }));
    expect(screen.getByRole("status")).toHaveTextContent("Working…");
  });

  it("stacks multiple toasts", async () => {
    const user = userEvent.setup();
    renderWith({ message: "One", variant: "error", durationMs: 0 });

    const raise = screen.getByRole("button", { name: "raise" });
    await user.click(raise);
    await user.click(raise);
    expect(screen.getAllByRole("alert")).toHaveLength(2);
  });

  it("renders an action button that fires its handler and dismisses", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    renderWith({
      message: "Mei left the scene.",
      variant: "info",
      durationMs: 0,
      action: { label: "Undo", onClick },
    });

    await user.click(screen.getByRole("button", { name: "raise" }));
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(onClick).toHaveBeenCalledTimes(1);
    await waitForElementToBeRemoved(() => screen.queryByRole("status"));
  });

  it("auto-dismisses after the duration elapses", async () => {
    render(
      <ToastProvider>
        <Harness input={{ message: "bye", variant: "info", durationMs: 60 }} />
      </ToastProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "raise" }));
    expect(screen.getByRole("status")).toBeInTheDocument();
    await waitForElementToBeRemoved(() => screen.queryByRole("status"));
  });

  it("holds the auto-dismiss timer while the pointer is over the toast", async () => {
    vi.useFakeTimers();
    try {
      render(
        <ToastProvider>
          <Harness input={{ message: "read me", variant: "info", durationMs: 3000 }} />
        </ToastProvider>,
      );
      act(() => {
        screen.getByRole("button", { name: "raise" }).click();
      });
      const toast = screen.getByRole("status");

      // Halfway through the countdown, the pointer arrives.
      act(() => void vi.advanceTimersByTime(1500));
      act(() => {
        toast.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      });

      // Well past the original 3000ms deadline, it is still on screen: the
      // timer is held, not merely visually frozen.
      act(() => void vi.advanceTimersByTime(10_000));
      expect(screen.getByRole("status")).toBeInTheDocument();

      // On leaving, only the REMAINING 1500ms is owed — not a fresh 3000.
      act(() => {
        toast.dispatchEvent(new MouseEvent("mouseout", { bubbles: true }));
      });
      act(() => void vi.advanceTimersByTime(1400));
      expect(screen.getByRole("status")).toBeInTheDocument();
      act(() => void vi.advanceTimersByTime(200));
    } finally {
      vi.useRealTimers();
    }
    await waitFor(() =>
      expect(screen.queryByRole("status")).not.toBeInTheDocument(),
    );
  });
});
