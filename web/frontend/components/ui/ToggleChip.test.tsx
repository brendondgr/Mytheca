import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ToggleChip } from "./ToggleChip";

describe("ToggleChip", () => {
  it("reflects selected state via aria-pressed and fires onClick", async () => {
    const onClick = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <ToggleChip selected={false} onClick={onClick}>
        Maerin
      </ToggleChip>,
    );
    const chip = screen.getByRole("button", { name: "Maerin" });
    expect(chip).toHaveAttribute("aria-pressed", "false");

    await user.click(chip);
    expect(onClick).toHaveBeenCalledOnce();

    rerender(
      <ToggleChip selected onClick={onClick}>
        Maerin
      </ToggleChip>,
    );
    expect(screen.getByRole("button", { name: "Maerin" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
