import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { StorylineMenu } from "./StorylineMenu";
import type { Storyline } from "@/lib/types";

const STORYLINES: Storyline[] = [
  { id: "embergate", title: "Embergate", genre: "Maritime", tagline: "x", characters: [], settings: [], scenarios: [] },
  { id: "tidefall", title: "Tidefall", genre: "Naval", characters: [], settings: [], scenarios: [] },
];

function setup() {
  const handlers = {
    onSwitch: vi.fn(),
    onCreate: vi.fn(),
    onEdit: vi.fn(),
    onDelete: vi.fn(),
  };
  render(<StorylineMenu storylines={STORYLINES} activeId="embergate" {...handlers} />);
  return handlers;
}

describe("StorylineMenu", () => {
  it("offers Edit and Delete actions per storyline", async () => {
    const user = userEvent.setup();
    const { onEdit, onDelete } = setup();

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /edit tidefall/i }));
    expect(onEdit).toHaveBeenCalledWith("tidefall");

    await user.click(screen.getByTitle(/switch storyline/i)); // reopen (closed on action)
    await user.click(screen.getByRole("button", { name: /delete embergate/i }));
    expect(onDelete).toHaveBeenCalledWith("embergate");
  });

  it("still switches storylines and creates a new one", async () => {
    const user = userEvent.setup();
    const { onSwitch, onCreate } = setup();

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /^tidefall/i }));
    expect(onSwitch).toHaveBeenCalledWith("tidefall");

    await user.click(screen.getByTitle(/switch storyline/i));
    await user.click(screen.getByRole("button", { name: /new storyline/i }));
    expect(onCreate).toHaveBeenCalled();
  });
});
