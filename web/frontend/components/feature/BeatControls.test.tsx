import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { BeatControls } from "./BeatControls";

describe("BeatControls", () => {
  it("renders nothing when no action is available", () => {
    const { container } = render(<BeatControls />);
    expect(container).toBeEmptyDOMElement();
  });

  it("branches immediately — it removes nothing, so it costs one click", async () => {
    const user = userEvent.setup();
    const onBranch = vi.fn();
    render(<BeatControls onBranch={onBranch} label="Mei's beat" />);

    await user.click(screen.getByRole("button", { name: /branch from mei's beat/i }));
    expect(onBranch).toHaveBeenCalled();
  });

  it("confirms before rewinding, because it removes content", async () => {
    const user = userEvent.setup();
    const onRewind = vi.fn();
    render(<BeatControls onRewind={onRewind} rewindBeatCount={4} label="Mei's beat" />);

    await user.click(screen.getByRole("button", { name: /rewind to mei's beat/i }));
    expect(onRewind).not.toHaveBeenCalled();
    expect(screen.getByText(/remove 4 beats\?/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Rewind" }));
    expect(onRewind).toHaveBeenCalled();
  });

  it("names how many beats go, rather than asking the player to guess", async () => {
    const user = userEvent.setup();
    render(<BeatControls onRewind={vi.fn()} rewindBeatCount={1} />);
    await user.click(screen.getByRole("button", { name: /rewind to/i }));
    expect(screen.getByText(/remove 1 beat\?/i)).toBeInTheDocument();
  });

  it("keeps the beat when the confirmation is declined", async () => {
    const user = userEvent.setup();
    const onRewind = vi.fn();
    render(<BeatControls onRewind={onRewind} rewindBeatCount={2} />);

    await user.click(screen.getByRole("button", { name: /rewind to/i }));
    await user.click(screen.getByRole("button", { name: "Keep" }));

    expect(onRewind).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /rewind to/i })).toBeInTheDocument();
  });

  it("stays in the tab order while quiet, so it is not mouse-only", () => {
    render(<BeatControls onBranch={vi.fn()} onRewind={vi.fn()} />);
    // Present and focusable even though the cluster is visually at opacity 0 until hover.
    for (const b of screen.getAllByRole("button")) {
      expect(b).not.toHaveAttribute("tabindex", "-1");
      expect(b).toBeVisible();
    }
  });

  it("is reachable by keyboard alone", async () => {
    const user = userEvent.setup();
    const onBranch = vi.fn();
    render(<BeatControls onBranch={onBranch} />);

    await user.tab();
    expect(screen.getByRole("button", { name: /branch from/i })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onBranch).toHaveBeenCalled();
  });

  it("disables its actions while a turn is streaming", () => {
    render(<BeatControls onBranch={vi.fn()} onRewind={vi.fn()} disabled />);
    for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
  });
});
