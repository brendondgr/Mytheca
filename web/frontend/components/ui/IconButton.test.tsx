import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { IconButton } from "./IconButton";

describe("IconButton", () => {
  it("names itself from `label`, since the content is only a glyph", () => {
    render(<IconButton label="Edit scenario">✎</IconButton>);
    expect(screen.getByRole("button", { name: "Edit scenario" })).toBeInTheDocument();
  });

  it("fires when enabled", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<IconButton label="Edit" onClick={onClick} />);
    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("carries a press state and a coarse-pointer hit area", () => {
    render(<IconButton label="Edit" />);
    const button = screen.getByRole("button", { name: "Edit" });
    // `.press` gives the :active scale — the only interaction feedback that
    // exists on touch, so it is not optional. `.touch-target-overlay` projects
    // a 44x44 hit area on coarse pointers without changing the visual 24px box.
    expect(button).toHaveClass("press");
    expect(button).toHaveClass("touch-target-overlay");
  });

  it("does not light up under the cursor when disabled", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<IconButton label="Delete" onClick={onClick} disabled />);

    const button = screen.getByRole("button", { name: "Delete" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(onClick).not.toHaveBeenCalled();

    // Every hover rule is scoped with `enabled:`, so a disabled control stays
    // visually inert. A button that reacts to the cursor but does nothing
    // reads as broken rather than as unavailable.
    for (const cls of Array.from(button.classList)) {
      if (cls.includes("hover:")) expect(cls.startsWith("enabled:")).toBe(true);
    }
    expect(button).toHaveClass("disabled:cursor-not-allowed");
  });
});
