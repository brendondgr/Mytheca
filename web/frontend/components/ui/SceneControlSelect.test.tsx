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
