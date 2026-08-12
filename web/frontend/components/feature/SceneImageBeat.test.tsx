import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneImageBeat } from "./SceneImageBeat";

const IMAGE = {
  url: "/media/moments/abc.webp",
  caption: "Two figures face each other across a lamplit table.",
  prompt: "two figures across a lamplit table, wide landscape composition",
};

describe("SceneImageBeat", () => {
  it("renders the picture with its caption as alt text", () => {
    render(<SceneImageBeat image={IMAGE} />);
    const img = screen.getByAltText(IMAGE.caption);
    expect(img).toHaveAttribute("src", expect.stringContaining("/media/moments/abc.webp"));
  });

  it("is a keyboard-operable button that opens the enlarged view", async () => {
    const onOpen = vi.fn();
    const user = userEvent.setup();
    render(<SceneImageBeat image={IMAGE} onOpen={onOpen} />);

    const button = screen.getByRole("button", { name: /enlarge scene image/i });
    await user.click(button);
    expect(onOpen).toHaveBeenCalledWith(IMAGE);

    // …and via the keyboard, since it is a real button.
    onOpen.mockClear();
    button.focus();
    await user.keyboard("{Enter}");
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("falls back to a generic description when the caption is empty", () => {
    render(<SceneImageBeat image={{ ...IMAGE, caption: "" }} />);
    expect(screen.getByAltText(/a picture of this moment/i)).toBeInTheDocument();
  });

  it("is not clickable without a handler", () => {
    render(<SceneImageBeat image={IMAGE} />);
    expect(screen.getByRole("button", { name: /enlarge scene image/i })).toBeDisabled();
  });
});
