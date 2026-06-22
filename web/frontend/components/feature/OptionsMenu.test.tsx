import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { OptionsMenu } from "./OptionsMenu";

const setTheme = vi.fn();
vi.mock("@/hooks/use-theme", () => ({
  useTheme: () => ({ theme: "light", setTheme }),
}));

describe("OptionsMenu", () => {
  it("opens, links to /options, and switches theme via colored swatches", async () => {
    const user = userEvent.setup();
    render(<OptionsMenu />);

    const trigger = screen.getByRole("button", { name: /options/i });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    expect(screen.getByRole("link", { name: /settings menu/i })).toHaveAttribute(
      "href",
      "/options",
    );

    await user.click(screen.getByRole("button", { name: /ember/i }));
    expect(setTheme).toHaveBeenCalledWith("dark");
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    render(<OptionsMenu />);
    const trigger = screen.getByRole("button", { name: /options/i });
    await user.click(trigger);
    await user.keyboard("{Escape}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });
});
