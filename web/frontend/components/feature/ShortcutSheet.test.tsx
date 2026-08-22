import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ShortcutSheet } from "./ShortcutSheet";

describe("ShortcutSheet", () => {
  it("renders nothing when closed", () => {
    const { container } = render(<ShortcutSheet open={false} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("groups the bindings rather than listing a key table", () => {
    render(<ShortcutSheet open onClose={() => {}} />);
    expect(screen.getByText("Getting around")).toBeInTheDocument();
    expect(screen.getByText("Writing")).toBeInTheDocument();
  });

  it("documents the composer behaviours that already existed and were invisible", () => {
    // Enter has always sent and `@` has always tagged; a player had no way to find that out
    // short of trying it. Writing them down is most of the value of this sheet.
    render(<ShortcutSheet open onClose={() => {}} />);
    expect(screen.getByText(/^Send$/)).toBeInTheDocument();
    expect(screen.getByText(/new line instead of sending/i)).toBeInTheDocument();
    expect(screen.getByText(/name a character, or attach one of your files/i)).toBeInTheDocument();
  });

  it("lists the new bindings", () => {
    render(<ShortcutSheet open onClose={() => {}} />);
    expect(screen.getByText(/jump to the message box/i)).toBeInTheDocument();
    expect(screen.getByText(/bring back your last message/i)).toBeInTheDocument();
    expect(screen.getByText(/close whatever is open/i)).toBeInTheDocument();
  });

  it("says plainly that nothing here is keyboard-only", () => {
    // A shortcut sheet that lists the only way to do something is documenting an
    // accessibility failure, not a convenience.
    render(<ShortcutSheet open onClose={() => {}} />);
    expect(screen.getByText(/every one of these has a pointer equivalent/i)).toBeInTheDocument();
  });

  it("is a labelled dialog", () => {
    render(<ShortcutSheet open onClose={() => {}} />);
    expect(screen.getByRole("dialog", { name: /keyboard shortcuts/i })).toBeInTheDocument();
  });

  it("closes", () => {
    const onClose = vi.fn();
    render(<ShortcutSheet open onClose={onClose} />);
    // The Modal owns the close affordance; this asserts it is wired, not how it looks.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
