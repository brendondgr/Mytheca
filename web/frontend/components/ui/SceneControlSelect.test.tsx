import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneControlSelect } from "./SceneControlSelect";

describe("SceneControlSelect", () => {
  it("renders a labeled select with the given options and value", () => {
    render(
      <SceneControlSelect label="Suggestions" value={4} options={[0, 1, 2, 3, 4]} onChange={() => {}} />,
    );
    const select = screen.getByRole("combobox", { name: /suggestions/i }) as HTMLSelectElement;
    expect(select.value).toBe("4");
    expect(screen.getAllByRole("option")).toHaveLength(5);
  });

  it("fires onChange with the numeric value on selection", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <SceneControlSelect label="Max turns" value={5} options={[1, 2, 3, 4, 5]} onChange={onChange} />,
    );
    await user.selectOptions(screen.getByRole("combobox", { name: /max turns/i }), "2");
    expect(onChange).toHaveBeenCalledWith(2); // number, not "2"
  });

  it("disables the select when asked", () => {
    render(
      <SceneControlSelect
        label="Max turns"
        value={5}
        options={[1, 2]}
        onChange={() => {}}
        disabled
      />,
    );
    expect(screen.getByRole("combobox", { name: /max turns/i })).toBeDisabled();
  });
});
