import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { CreateImageBar } from "./CreateImageBar";

describe("CreateImageBar", () => {
  it("offers a Go button that starts a render", async () => {
    const onCreate = vi.fn();
    const user = userEvent.setup();
    render(<CreateImageBar onCreate={onCreate} />);

    expect(screen.getByText(/create image/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^go$/i }));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it("explains itself and stays disabled before a session exists", async () => {
    const onCreate = vi.fn();
    const user = userEvent.setup();
    render(<CreateImageBar onCreate={onCreate} disabled />);

    expect(screen.getByText(/take a turn first/i)).toBeInTheDocument();
    const go = screen.getByRole("button", { name: /^go$/i });
    expect(go).toBeDisabled();
    await user.click(go);
    expect(onCreate).not.toHaveBeenCalled();
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
});
