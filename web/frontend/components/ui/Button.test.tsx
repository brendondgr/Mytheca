import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { Button } from "./Button";

describe("Button", () => {
  it("fires onClick when enabled", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(<Button onClick={onClick}>Go</Button>);
    await user.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("does not fire when disabled", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    render(
      <Button onClick={onClick} disabled>
        Go
      </Button>,
    );
    await user.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).not.toHaveBeenCalled();
  });

  describe("loading variant", () => {
    it("keeps the label in the DOM so the button does not change width", () => {
      const { rerender } = render(<Button>Save character</Button>);
      // The label element itself must survive the swap — it is what holds the
      // box open while the spinner is overlaid on top of it. If it were
      // replaced by the spinner, the button would shrink to the spinner's
      // width and reflow the row it sits in.
      rerender(
        <Button loading loadingLabel="Saving character">
          Save character
        </Button>,
      );
      expect(screen.getByText("Save character")).toBeInTheDocument();
    });

    it("marks itself busy, names what it is doing, and refuses clicks", async () => {
      const onClick = vi.fn();
      const user = userEvent.setup();
      render(
        <Button onClick={onClick} loading loadingLabel="Saving character">
          Save character
        </Button>,
      );

      const button = screen.getByRole("button", { name: "Saving character" });
      expect(button).toHaveAttribute("aria-busy", "true");
      expect(button).toBeDisabled();

      await user.click(button);
      expect(onClick).not.toHaveBeenCalled();
    });
  });
});
