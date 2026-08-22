import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { BeatEditor } from "./BeatEditor";

const setup = (over: Partial<React.ComponentProps<typeof BeatEditor>> = {}) => {
  const props = {
    initialText: "Mei sets the cup down.",
    onSave: vi.fn(),
    onCancel: vi.fn(),
    label: "Mei's beat",
    ...over,
  };
  render(<BeatEditor {...props} />);
  return props;
};

describe("BeatEditor", () => {
  it("opens with the beat's current text, focused", () => {
    setup();
    const field = screen.getByLabelText(/editing mei's beat/i);
    expect(field).toHaveValue("Mei sets the cup down.");
    expect(field).toHaveFocus();
  });

  it("is a labelled form field rather than a contenteditable", () => {
    setup();
    const field = screen.getByLabelText(/editing mei's beat/i);
    expect(field.tagName).toBe("TEXTAREA");
    expect(field).not.toHaveAttribute("contenteditable");
  });

  it("saves the rewritten text", async () => {
    const user = userEvent.setup();
    const props = setup();
    const field = screen.getByLabelText(/editing/i);
    await user.clear(field);
    await user.type(field, "Mei says nothing at all.");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(props.onSave).toHaveBeenCalledWith("Mei says nothing at all.");
  });

  it("will not save an unchanged beat", async () => {
    setup();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("will not save an empty beat", async () => {
    const user = userEvent.setup();
    setup();
    await user.clear(screen.getByLabelText(/editing/i));
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("cancels on Escape without saving", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.type(screen.getByLabelText(/editing/i), " more");
    await user.keyboard("{Escape}");

    expect(props.onCancel).toHaveBeenCalled();
    expect(props.onSave).not.toHaveBeenCalled();
  });

  it("saves on Ctrl+Enter", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.type(screen.getByLabelText(/editing/i), " Quietly.");
    await user.keyboard("{Control>}{Enter}{/Control}");

    expect(props.onSave).toHaveBeenCalledWith("Mei sets the cup down. Quietly.");
  });

  it("treats plain Enter as a newline, because a beat is prose", async () => {
    const user = userEvent.setup();
    const props = setup();
    const field = screen.getByLabelText(/editing/i);
    await user.type(field, "{Enter}A second paragraph.");

    expect(props.onSave).not.toHaveBeenCalled();
    expect(field).toHaveValue("Mei sets the cup down.\nA second paragraph.");
  });

  it("cancels on the Cancel button", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(props.onCancel).toHaveBeenCalled();
  });

  it("shows progress and blocks a double save while in flight", () => {
    setup({ saving: true, initialText: "x" });
    expect(screen.getByRole("button", { name: /saving/i })).toBeDisabled();
  });
});
