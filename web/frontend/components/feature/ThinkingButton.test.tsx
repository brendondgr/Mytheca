import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThinkingButton } from "./ThinkingButton";

describe("ThinkingButton", () => {
  it("reads as Default until the player chooses, and says what it does", () => {
    render(<ThinkingButton open={false} onOpenChange={() => {}} onLevelChange={() => {}} />);
    const trigger = screen.getByRole("button");
    expect(trigger).toHaveTextContent("Default");
    // The accessible name carries the consequence, not only the setting's name.
    expect(trigger).toHaveAttribute("aria-label", expect.stringContaining("longer wait"));
  });

  it("offers Default alongside the six levels", async () => {
    render(<ThinkingButton open onOpenChange={() => {}} onLevelChange={() => {}} />);
    const options = screen.getAllByRole("radio");
    expect(options.map((o) => o.textContent)).toEqual([
      "Default—",
      "Very low128",
      "Low256",
      "Medium512",
      "High1024",
      "Extra high2048",
      "Max4096",
    ]);
  });

  it("returns null for Default rather than a level", async () => {
    const onLevelChange = vi.fn();
    render(<ThinkingButton open level="high" onOpenChange={() => {}} onLevelChange={onLevelChange} />);
    await userEvent.click(screen.getByRole("radio", { name: /Default/ }));
    // `null` is not a seventh level: it means "leave the call site's own budget alone",
    // which is a different request from asking for the lowest one.
    expect(onLevelChange).toHaveBeenCalledWith(null);
  });

  it("sends the chosen level and closes", async () => {
    const onLevelChange = vi.fn();
    const onOpenChange = vi.fn();
    render(<ThinkingButton open onOpenChange={onOpenChange} onLevelChange={onLevelChange} />);
    await userEvent.click(screen.getByRole("radio", { name: /Extra high/ }));
    expect(onLevelChange).toHaveBeenCalledWith("very_high");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("marks the current level as checked", () => {
    render(<ThinkingButton open level="medium" onOpenChange={() => {}} onLevelChange={() => {}} />);
    expect(screen.getByRole("radio", { name: /Medium/ })).toHaveAttribute("aria-checked", "true");
  });

  it("closes on Escape without choosing", async () => {
    const onOpenChange = vi.fn();
    const onLevelChange = vi.fn();
    render(<ThinkingButton open onOpenChange={onOpenChange} onLevelChange={onLevelChange} />);
    await userEvent.keyboard("{Escape}");
    screen.getByRole("radiogroup").focus();
    await userEvent.type(screen.getByRole("radiogroup"), "{Escape}");
    expect(onLevelChange).not.toHaveBeenCalled();
  });
});
