import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { Select } from "./Select";

describe("Select", () => {
  it("renders its options and hands back the native value", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Select aria-label="Presence" defaultValue="present" onChange={onChange}>
        <option value="present">In the scene</option>
        <option value="dead">Dead</option>
      </Select>,
    );
    await user.selectOptions(screen.getByRole("combobox", { name: "Presence" }), "dead");
    expect(onChange).toHaveBeenCalled();
    expect(onChange.mock.calls[0][0].target.value).toBe("dead");
  });

  it("keeps the 16px field size below `sm` and drops to the dense size above it", () => {
    // The split is the whole point of this primitive, and it is the kind of thing a later
    // "simplification" deletes. 16px below `sm` is what stops iOS Safari zooming the viewport
    // when a select takes focus; above `sm` there is no such pointer and no such trap.
    render(
      <Select aria-label="Presence">
        <option value="a">A</option>
      </Select>,
    );
    const el = screen.getByRole("combobox", { name: "Presence" });
    expect(el.className).toContain("text-field");
    expect(el.className).toContain("sm:text-ui");
  });

  it("does not set a height, so the coarse-pointer floor can raise it", () => {
    render(
      <Select aria-label="Presence">
        <option value="a">A</option>
      </Select>,
    );
    expect(screen.getByRole("combobox", { name: "Presence" }).className).not.toMatch(/\bh-\[/);
  });

  it("passes through disabled", () => {
    render(
      <Select aria-label="Presence" disabled>
        <option value="a">A</option>
      </Select>,
    );
    expect(screen.getByRole("combobox", { name: "Presence" })).toBeDisabled();
  });
});
