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

describe("SceneImageModal — paint again", () => {
  const image = {
    url: "/media/moments/x.webp",
    caption: "Two figures at a lamplit table.",
    prompt: "a lamplit table, rain on the window",
  };

  async function openPrompt(props: Record<string, unknown> = {}) {
    const user = userEvent.setup();
    render(<SceneImageModal image={image} onClose={() => {}} {...props} />);
    await user.click(screen.getByRole("button", { name: /show the prompt/i }));
    return user;
  }

  it("keeps the prompt read-only when repainting is not offered", async () => {
    await openPrompt();
    expect(screen.queryByRole("textbox", { name: /image prompt/i })).not.toBeInTheDocument();
    expect(screen.getByText("a lamplit table, rain on the window")).toBeInTheDocument();
  });

  it("makes it editable when it is", async () => {
    // The prompt already explained *why* the picture looks as it does; making it writable
    // turns that into how to get the picture you wanted.
    await openPrompt({ onRepaint: () => {} });
    expect(screen.getByRole("textbox", { name: /image prompt/i })).toHaveValue(
      "a lamplit table, rain on the window",
    );
  });

  it("paints again with the edited wording", async () => {
    const onRepaint = vi.fn();
    const user = await openPrompt({ onRepaint });
    const box = screen.getByRole("textbox", { name: /image prompt/i });
    await user.clear(box);
    await user.type(box, "the same table, but at dawn");
    await user.click(screen.getByRole("button", { name: /paint again/i }));
    // The second argument is the art style; undefined means "the operator's default".
    expect(onRepaint).toHaveBeenCalledWith("the same table, but at dawn", undefined);
  });

  it("refuses to paint an empty prompt", async () => {
    const onRepaint = vi.fn();
    const user = await openPrompt({ onRepaint });
    await user.clear(screen.getByRole("textbox", { name: /image prompt/i }));
    expect(screen.getByRole("button", { name: /paint again/i })).toBeDisabled();
    expect(onRepaint).not.toHaveBeenCalled();
  });

  it("blocks a second paint while one is in flight, and says so", async () => {
    await openPrompt({ onRepaint: () => {}, busy: true });
    expect(screen.getByRole("button", { name: /paint again/i })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(/painting the moment/i);
  });

  it("shows the right prompt after opening a different picture", async () => {
    // Seeded from the image and keyed on it — otherwise the second picture opens showing the
    // first one's prompt, and the player edits the wrong thing.
    const { rerender } = render(<SceneImageModal image={image} onClose={() => {}} onRepaint={() => {}} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /show the prompt/i }));
    rerender(
      <SceneImageModal
        image={{ ...image, prompt: "a different scene entirely" }}
        onClose={() => {}}
        onRepaint={() => {}}
      />,
    );
    expect(screen.getByRole("textbox", { name: /image prompt/i })).toHaveValue(
      "a different scene entirely",
    );
  });
});

