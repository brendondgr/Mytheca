import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneImageModal } from "./SceneImageModal";

const IMAGE = {
  url: "/media/moments/abc.webp",
  caption: "Two figures face each other across a lamplit table.",
  prompt: "two figures across a lamplit table, wide landscape composition",
};

describe("SceneImageModal", () => {
  it("renders nothing when no image is open", () => {
    const { container } = render(<SceneImageModal image={null} onClose={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows the enlarged picture and its caption", () => {
    render(<SceneImageModal image={IMAGE} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByAltText(IMAGE.caption)).toHaveAttribute(
      "src",
      expect.stringContaining("/media/moments/abc.webp"),
    );
    expect(screen.getByText(IMAGE.caption)).toBeInTheDocument();
  });

  it("keeps the prompt behind a disclosure", async () => {
    const user = userEvent.setup();
    render(<SceneImageModal image={IMAGE} onClose={vi.fn()} />);

    expect(screen.queryByText(IMAGE.prompt)).not.toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /show the prompt/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);
    expect(screen.getByText(IMAGE.prompt)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hide the prompt/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("closes on Escape and from the Done button", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(<SceneImageModal image={IMAGE} onClose={onClose} />);

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: /^done$/i }));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
