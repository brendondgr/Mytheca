import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SceneControlSelect } from "./SceneControlSelect";

/**
 * The control carries both a count (Max turns, Suggestions) and an enum (Beat length).
 * It used to coerce every selection with `Number(...)`, which is why an enum could not ride
 * on it — a string value came back as `NaN`. These tests pin both shapes, because the
 * numeric callers are pre-existing and must not regress to make room for the new one.
 */
describe("SceneControlSelect", () => {
  it("hands a numeric caller back a number, not a string", async () => {
    const onChange = vi.fn();
    render(
      <SceneControlSelect label="Max turns" value={5} options={[1, 5, 10]} onChange={onChange} />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Max turns"), "10");
    expect(onChange).toHaveBeenCalledWith(10);
    expect(typeof onChange.mock.calls[0][0]).toBe("number");
  });

  it("hands a string caller back the original value", async () => {
    const onChange = vi.fn();
    render(
      <SceneControlSelect
        label="Beat length"
        value="medium"
        options={["short", "medium", "long"]}
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Beat length"), "short");
    expect(onChange).toHaveBeenCalledWith("short");
  });

  it("renders an option's label while carrying its value", async () => {
    const onChange = vi.fn();
    render(
      <SceneControlSelect
        label="Beat length"
        value="medium"
        options={[
          { value: "short", label: "Short · 1–2 ¶" },
          { value: "medium", label: "Medium · 2–4 ¶" },
        ]}
        onChange={onChange}
      />,
    );
    // The reader sees the label...
    expect(screen.getByRole("option", { name: "Short · 1–2 ¶" })).toBeInTheDocument();
    // ...and the wire gets the value.
    await userEvent.selectOptions(screen.getByLabelText("Beat length"), "short");
    expect(onChange).toHaveBeenCalledWith("short");
  });

  it("reflects the current value as the selection", () => {
    render(
      <SceneControlSelect
        label="Beat length"
        value="long"
        options={["short", "medium", "long"]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText<HTMLSelectElement>("Beat length").value).toBe("long");
  });

  it("is a native select with an accessible name, and honours disabled", () => {
    render(
      <SceneControlSelect
        label="Suggestions"
        value={2}
        options={[0, 2, 4]}
        onChange={vi.fn()}
        disabled
      />,
    );
    const select = screen.getByLabelText("Suggestions");
    expect(select.tagName).toBe("SELECT");
    expect(select).toBeDisabled();
  });
});

describe("SceneControlSelect consequence + cost", () => {
  it("associates the consequence line with the control, not just beside it", () => {
    // A label tells a player what a setting is called; it never tells them what happens if
    // they change it. `aria-describedby` is what makes that difference reach a screen reader
    // rather than only a sighted one.
    render(
      <SceneControlSelect
        label="How many beats one message produces"
        value={5}
        options={[1, 5]}
        onChange={() => {}}
        help="The cap on replies — narrator beats count too."
      />,
    );
    expect(
      screen.getByRole("combobox", { name: /how many beats/i }),
    ).toHaveAccessibleDescription(/the cap on replies/i);
  });

  it("puts the cost with the consequence rather than in a separate readout", () => {
    // "What it does" and "what it costs" are one decision; splitting them makes the player
    // read twice to make it once.
    render(
      <SceneControlSelect
        label="Beats"
        value={5}
        options={[1, 5]}
        onChange={() => {}}
        help="The cap on replies."
        cost="≈ 4s per extra beat"
      />,
    );
    expect(screen.getByRole("combobox", { name: "Beats" })).toHaveAccessibleDescription(
      /the cap on replies[\s\S]*4s per extra beat/i,
    );
  });

  it("adds no description at all when there is nothing to say", () => {
    render(<SceneControlSelect label="Bare" value={1} options={[1, 2]} onChange={() => {}} />);
    expect(screen.getByRole("combobox", { name: "Bare" })).not.toHaveAttribute(
      "aria-describedby",
    );
  });

  it("omits the cost when there is no honest number for it", () => {
    // Better silent than invented: a seconds-per-beat figure made up in the UI would be
    // wrong for every operator's hardware.
    render(
      <SceneControlSelect
        label="Bare"
        value={1}
        options={[1, 2]}
        onChange={() => {}}
        help="Just the consequence."
      />,
    );
    expect(screen.getByRole("combobox", { name: "Bare" })).toHaveAccessibleDescription(
      "Just the consequence.",
    );
  });
});

