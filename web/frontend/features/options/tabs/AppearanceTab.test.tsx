import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { AppearanceTab } from "./AppearanceTab";

const setTheme = vi.fn();
vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({ theme: "light", setTheme }),
}));

describe("AppearanceTab", () => {
  it("renders label-free colored swatches and switches theme", async () => {
    const user = userEvent.setup();
    render(<AppearanceTab />);

    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(3);
    // Parchment is active (theme = light); accessible names come from aria-label.
    expect(screen.getByRole("radio", { name: /parchment/i })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    await user.click(screen.getByRole("radio", { name: /slate/i }));
    expect(setTheme).toHaveBeenCalledWith("slate");
  });
});
