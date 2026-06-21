import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { StoryPlayerView } from "./StoryPlayerView";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
} from "@/lib/seed-data";

const embergate = resolveScenario(
  SEED_SCENARIOS[0],
  SEED_CHARACTERS,
  SEED_SETTINGS,
);

describe("StoryPlayerView", () => {
  it("renders the scripted transcript beats (narrator, dialogue, check, choices)", () => {
    render(<StoryPlayerView scenario={embergate} />);
    expect(
      screen.getByText(/Lamplight gutters across the Saltworn/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/The tide doesn't wait/i)).toBeInTheDocument();
    expect(screen.getByText("d20 check")).toBeInTheDocument();
    expect(screen.getByText(/Your move/i)).toBeInTheDocument();
  });

  it("appends a player turn + narrator beat on send", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.type(
      screen.getByRole("textbox", { name: /your message/i }),
      "I draw my blade.",
    );
    await user.click(screen.getByRole("button", { name: /send/i }));
    expect(screen.getByText("I draw my blade.")).toBeInTheDocument();
    expect(screen.getByText(/The table waits/i)).toBeInTheDocument();
  });

  it("applies a choice: updates a stat and advances the scene", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    expect(screen.getByText("+2")).toBeInTheDocument(); // Suspicion starts at +2
    await user.click(
      screen.getByRole("button", { name: /confront maerin about the captain/i }),
    );
    expect(screen.getByText("+4")).toBeInTheDocument(); // Suspicion +2
    expect(screen.getByText(/Afraid is a strong word/i)).toBeInTheDocument();
  });
});
