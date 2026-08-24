import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PlanModeButton } from "./PlanModeButton";

/** Renders the control with its disclosure state driven the way the composer drives it. */
function setup(overrides: Partial<Parameters<typeof PlanModeButton>[0]> = {}) {
  const onModeChange = vi.fn();
  const onOpenChange = vi.fn();
  const props = { mode: "auto" as const, onModeChange, onOpenChange, open: false, ...overrides };
  const view = render(<PlanModeButton {...props} />);
  return { ...props, view };
}

describe("PlanModeButton", () => {
  it("shows the active mode in a word when collapsed", () => {
    setup({ mode: "plan" });
    expect(screen.getByRole("button", { name: /plan mode: plan/i })).toBeInTheDocument();
  });

  it("says what the mode DOES in its accessible name, not just what it is called", () => {
    // "Plan mode: Auto" tells a screen-reader user what the control is called and nothing
    // about what pressing it will do to their next message.
    setup({ mode: "auto" });
    const button = screen.getByRole("button", { name: /plan mode: auto/i });
    expect(button).toHaveAccessibleName(/without stopping/i);
  });

  it("asks the parent to open rather than opening itself", async () => {
    // The composer owns the disclosure so it can close it when a turn starts.
    const user = userEvent.setup();
    const { onOpenChange } = setup();
    await user.click(screen.getByRole("button", { name: /plan mode/i }));
    expect(onOpenChange).toHaveBeenCalledWith(true);
  });

  it("expands into exactly two choices, as a radio group", async () => {
    setup({ open: true });
    const group = screen.getByRole("radiogroup", { name: /plan mode/i });
    const options = screen.getAllByRole("radio");
    expect(group).toBeInTheDocument();
    expect(options.map((o) => o.textContent)).toEqual(["Auto", "Plan"]);
  });

  it("marks the active choice with aria-checked, not colour alone", () => {
    setup({ open: true, mode: "plan" });
    expect(screen.getByRole("radio", { name: "Plan" })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: "Auto" })).toHaveAttribute("aria-checked", "false");
  });

  it("reports the choice and closes in one click", async () => {
    const user = userEvent.setup();
    const { onModeChange, onOpenChange } = setup({ open: true });
    await user.click(screen.getByRole("radio", { name: "Plan" }));
    expect(onModeChange).toHaveBeenCalledWith("plan");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("closes on Escape without choosing", async () => {
    const user = userEvent.setup();
    const { onModeChange, onOpenChange } = setup({ open: true });
    screen.getByRole("radio", { name: "Auto" }).focus();
    await user.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(onModeChange).not.toHaveBeenCalled();
  });

  it("is inert and honest when planning is off entirely", () => {
    // `off` is not a third position on this toggle — with no planner there is nothing to
    // approve — so the control says so rather than offering two choices that would both lie.
    setup({ mode: "off", open: true });
    expect(screen.queryByRole("radiogroup")).toBeNull();
    const button = screen.getByRole("button", { name: /plan mode: no plan/i });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleName(/config/i);
  });

  it("is disabled while a turn is streaming", () => {
    setup({ disabled: true });
    expect(screen.getByRole("button", { name: /plan mode/i })).toBeDisabled();
  });
});
