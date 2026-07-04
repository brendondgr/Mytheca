import { describe, it, expect, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ToastProvider, useToast, type NotifyInput } from "./ToastProvider";

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
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
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
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("auto-dismisses after the duration elapses", async () => {
    vi.useFakeTimers();
    try {
      render(
        <ToastProvider>
          <Harness input={{ message: "bye", variant: "info", durationMs: 3000 }} />
        </ToastProvider>,
      );
      // fireEvent-style click without user-event (fake timers).
      act(() => {
        screen.getByRole("button", { name: "raise" }).click();
      });
      expect(screen.getByRole("status")).toBeInTheDocument();
      act(() => void vi.advanceTimersByTime(3000));
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
