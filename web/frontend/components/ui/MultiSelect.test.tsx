import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { useState } from "react";
import { MultiSelect, type MultiSelectOption } from "./MultiSelect";

const CHARS: MultiSelectOption[] = [
  { id: "c1", label: "Maerin", mono: "MA", color: "#3A5A78" },
  { id: "c2", label: "Doran", mono: "DO", color: "#7A3A3A" },
  { id: "c3", label: "Sable", mono: "SA", color: "#3A7A5A" },
];

const SETTINGS: MultiSelectOption[] = [
  { id: "s1", label: "The Harbor", seal: true },
  { id: "s2", label: "The Lighthouse", seal: true },
];

/** Controlled wrapper so selection actually reflects across interactions. */
function Harness({
  options,
  multiple,
  initial = [],
  onChangeSpy,
  ...rest
}: {
  options: MultiSelectOption[];
  multiple?: boolean;
  initial?: string[];
  onChangeSpy?: (next: string[]) => void;
  label?: string;
  placeholder?: string;
  emptyText?: string;
}) {
  const [selected, setSelected] = useState<string[]>(initial);
  return (
    <MultiSelect
      options={options}
      selected={selected}
      multiple={multiple}
      onChange={(next) => {
        setSelected(next);
        onChangeSpy?.(next);
      }}
      {...rest}
    />
  );
}

describe("MultiSelect", () => {
  it("opens and closes on click and Escape", async () => {
    const user = userEvent.setup();
    render(<Harness options={CHARS} multiple label="Cast" />);
    const trigger = screen.getByRole("button");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("listbox", { name: "Cast" })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("multi-select toggles options on and off, keeping the listbox open", async () => {
    const onChangeSpy = vi.fn();
    const user = userEvent.setup();
    render(<Harness options={CHARS} multiple label="Cast" onChangeSpy={onChangeSpy} />);

    await user.click(screen.getByRole("button"));
    const list = screen.getByRole("listbox");
    expect(list).toHaveAttribute("aria-multiselectable", "true");

    await user.click(within(list).getByRole("option", { name: /Maerin/ }));
    expect(onChangeSpy).toHaveBeenLastCalledWith(["c1"]);
    // Still open for multi-select.
    expect(screen.getByRole("listbox")).toBeInTheDocument();

    await user.click(within(screen.getByRole("listbox")).getByRole("option", { name: /Sable/ }));
    expect(onChangeSpy).toHaveBeenLastCalledWith(["c1", "c3"]);

    // Re-clicking a selected option removes it.
    await user.click(within(screen.getByRole("listbox")).getByRole("option", { name: /Maerin/ }));
    expect(onChangeSpy).toHaveBeenLastCalledWith(["c3"]);
  });

  it("single-select replaces the prior choice and closes", async () => {
    const onChangeSpy = vi.fn();
    const user = userEvent.setup();
    render(<Harness options={SETTINGS} label="Setting" onChangeSpy={onChangeSpy} />);

    await user.click(screen.getByRole("button"));
    expect(screen.getByRole("listbox")).not.toHaveAttribute("aria-multiselectable");

    await user.click(screen.getByRole("option", { name: /The Harbor/ }));
    expect(onChangeSpy).toHaveBeenLastCalledWith(["s1"]);
    // Single-select closes after choosing.
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

    // Reopen and pick another — replaces, never appends.
    await user.click(screen.getByRole("button"));
    await user.click(screen.getByRole("option", { name: /The Lighthouse/ }));
    expect(onChangeSpy).toHaveBeenLastCalledWith(["s2"]);
  });

  it("supports keyboard navigation and toggles with Enter", async () => {
    const onChangeSpy = vi.fn();
    const user = userEvent.setup();
    render(<Harness options={CHARS} multiple label="Cast" onChangeSpy={onChangeSpy} />);

    await user.click(screen.getByRole("button"));
    // Focus starts on the first option; ArrowDown moves to the second, Enter toggles it.
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");
    expect(onChangeSpy).toHaveBeenLastCalledWith(["c2"]);

    // End jumps to the last option.
    await user.keyboard("{End}");
    await user.keyboard("{Enter}");
    expect(onChangeSpy).toHaveBeenLastCalledWith(["c2", "c3"]);
  });

  it("renders selected entries on the trigger and an empty placeholder otherwise", async () => {
    render(<Harness options={CHARS} multiple label="Cast" initial={["c2"]} placeholder="Pick cast" />);
    const trigger = screen.getByRole("button");
    expect(trigger).toHaveTextContent("Doran");

    render(<Harness options={[]} multiple label="Cast" emptyText="No characters yet" />);
    expect(screen.getByText("No characters yet")).toBeInTheDocument();
  });
});
