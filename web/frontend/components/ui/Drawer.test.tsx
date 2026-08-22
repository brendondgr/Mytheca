import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";
import { useState } from "react";
import { Drawer } from "./Drawer";

function Harness({
  open = true,
  onClose = vi.fn(),
}: {
  open?: boolean;
  onClose?: () => void;
}) {
  return (
    <Drawer open={open} onClose={onClose} title="What the scene knows">
      <button type="button">first</button>
      <button type="button">second</button>
    </Drawer>
  );
}

afterEach(() => {
  document.body.style.overflow = "";
});

describe("Drawer", () => {
  it("names itself with a real heading, not a styled div", () => {
    // A dialog whose name is a paragraph cannot be found in a heading list.
    render(<Harness />);
    const dialog = screen.getByRole("dialog", { name: "What the scene knows" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("heading", { name: "What the scene knows" })).toBeInTheDocument();
  });

  it("renders nothing when closed", () => {
    render(<Harness open={false} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("moves focus into the panel on open — onto Close, which comes first", () => {
    // Deliberate: the dismiss control precedes the content, so a keyboard user's first stop
    // is the way out rather than somewhere in the middle of a rail. The dialog's NAME is
    // still the heading, which is what gets announced on arrival.
    render(<Harness />);
    expect(screen.getByRole("button", { name: /close/i })).toHaveFocus();
  });

  it("traps Tab at the end", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const close = screen.getByRole("button", { name: /close/i });

    screen.getByRole("button", { name: "second" }).focus();
    await user.tab();
    expect(close).toHaveFocus();
  });

  it("traps Shift+Tab at the start", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const close = screen.getByRole("button", { name: /close/i });

    close.focus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "second" })).toHaveFocus();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("closes on a backdrop click but not on a click inside", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Harness onClose={onClose} />);

    await user.click(screen.getByRole("button", { name: "second" }));
    expect(onClose).not.toHaveBeenCalled();

    await user.click(screen.getByTestId("drawer-backdrop"));
    expect(onClose).toHaveBeenCalled();
  });

  it("locks the body scroll while open and restores what it was", () => {
    // Restored to its PREVIOUS value, not to "": a drawer over a modal must not unlock the
    // page behind the modal that is still open.
    document.body.style.overflow = "clip";
    const { rerender } = render(<Harness />);
    expect(document.body.style.overflow).toBe("hidden");

    rerender(<Harness open={false} />);
    expect(document.body.style.overflow).toBe("clip");
  });

  it("returns focus to the trigger on close", async () => {
    const user = userEvent.setup();

    function WithTrigger() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            open it
          </button>
          <Drawer open={open} onClose={() => setOpen(false)} title="Sheet">
            <button type="button">inside</button>
          </Drawer>
        </>
      );
    }

    render(<WithTrigger />);
    const trigger = screen.getByRole("button", { name: "open it" });
    await user.click(trigger);
    expect(screen.getByRole("dialog", { name: "Sheet" })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
  });

  it("leaves the accessibility tree the moment it starts closing", async () => {
    // It stays mounted for the exit transition. Two sheets swapping would otherwise put two
    // dialogs in the tree at once — and focus is already back on the trigger by then, so
    // hiding it is safe.
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { rerender } = render(<Harness onClose={onClose} />);
    await user.keyboard("{Escape}");

    rerender(<Harness open={false} onClose={onClose} />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByTestId("drawer-backdrop")).toBeInTheDocument(); // still animating out
  });

  it("stacks below Modal so a modal opened from a drawer is on top", () => {
    // Modal defaults to 60; a drawer that sat above it would hide the thing it opened.
    render(<Harness />);
    expect(screen.getByTestId("drawer-backdrop")).toHaveStyle({ zIndex: "55" });
  });
});
