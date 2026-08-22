import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CreateImageBar } from "./CreateImageBar";
import { resetArtStylesCache } from "@/hooks/use-art-styles";
import { COMFY_FIXTURE } from "@/test/api-mock";

const getSettings = vi.fn();
vi.mock("@/lib/api", () => ({
  getSettings: (...args: unknown[]) => getSettings(...args),
}));

beforeEach(() => {
  resetArtStylesCache();
  getSettings.mockReset();
  getSettings.mockResolvedValue({ comfy: COMFY_FIXTURE });
});

describe("CreateImageBar", () => {
  it("offers a Go button that starts a render", async () => {
    const onCreate = vi.fn();
    const user = userEvent.setup();
    render(<CreateImageBar onCreate={onCreate} />);

    expect(screen.getByText(/create image/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^go$/i }));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it("names each stage in a live region while it runs", () => {
    const { rerender } = render(
      <CreateImageBar onCreate={vi.fn()} running stage="prompt" />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(/reading the scene/i);
    expect(screen.queryByRole("button", { name: /^go$/i })).not.toBeInTheDocument();

    rerender(<CreateImageBar onCreate={vi.fn()} running stage="render" />);
    expect(screen.getByRole("status")).toHaveTextContent(/painting the moment/i);
  });

  it("marks the placeholder frame busy while painting", () => {
    const { container } = render(<CreateImageBar onCreate={vi.fn()} running stage="render" />);
    const frame = container.querySelector('[aria-busy="true"]');
    expect(frame).not.toBeNull();
    // The wash is a base gradient + animation, so reduced motion leaves a static frame.
    expect(frame).toHaveClass("mytheca-wash");
  });

  it("surfaces a failure as an alert", () => {
    render(<CreateImageBar onCreate={vi.fn()} error="ComfyUI never returned an image." />);
    expect(screen.getByRole("alert")).toHaveTextContent("ComfyUI never returned an image.");
  });

  it("paints in the style the player picked", async () => {
    const onCreate = vi.fn();
    const user = userEvent.setup();
    render(<CreateImageBar onCreate={onCreate} />);

    await user.click(await screen.findByRole("radio", { name: /anime/i }));
    await user.click(screen.getByRole("button", { name: /^go$/i }));
    expect(onCreate).toHaveBeenCalledWith("anime");
  });

  it("passes no style when the player leaves the default alone", async () => {
    const onCreate = vi.fn();
    const user = userEvent.setup();
    render(<CreateImageBar onCreate={onCreate} />);

    await screen.findByRole("radio", { name: /painted/i });
    await user.click(screen.getByRole("button", { name: /^go$/i }));
    // undefined, not "painted": the backend resolves the operator's default, so a player
    // who never touches the picker follows Options rather than a value frozen at mount.
    expect(onCreate).toHaveBeenCalledWith(undefined);
  });

  it("drops the blurbs so the row stays one line's worth of chrome", async () => {
    render(<CreateImageBar onCreate={vi.fn()} />);
    await screen.findByRole("radio", { name: /painted/i });
    expect(screen.queryByText(/watercolor and oil washes/i)).not.toBeInTheDocument();
  });

  it("hides the picker while a render is in flight", () => {
    render(<CreateImageBar onCreate={vi.fn()} running stage="render" />);
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
  });
});
