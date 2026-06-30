import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { StoryPlayerView } from "./StoryPlayerView";
import { postTurn } from "@/lib/api";
import type { TurnStreamFrame } from "@/lib/events";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
  SEED_STAT_DEFS,
} from "@/lib/seed-data";

// Keep the real api (mediaUrl etc.) but stub the streaming turn.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  postTurn: vi.fn(),
}));

function streamOf(...frames: TurnStreamFrame[]) {
  return async function* () {
    for (const f of frames) yield f;
  };
}

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

  it("surfaces the storyline stat schema in the director rail", () => {
    render(<StoryPlayerView scenario={embergate} statDefs={SEED_STAT_DEFS} />);
    expect(screen.getByText("Character stats")).toBeInTheDocument();
    expect(screen.getByText("Health")).toBeInTheDocument();
  });

  it("streams a turn on send: player bubble + the streamed reply", async () => {
    const speaker = embergate.cast[0];
    vi.mocked(postTurn).mockImplementation(
      streamOf(
        {
          type: "character_dialogue",
          id: "d1",
          seq: 1,
          scenarioId: embergate.id,
          sessionId: "ps_live",
          ts: "t",
          visibility: "public",
          data: { characterId: speaker.id, text: "The room turns to you.", done: true },
        } as TurnStreamFrame,
      ),
    );
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.type(
      screen.getByRole("textbox", { name: /your message/i }),
      "I draw my blade.",
    );
    await user.click(screen.getByRole("button", { name: /send/i }));
    expect(screen.getByText("I draw my blade.")).toBeInTheDocument();
    expect(await screen.findByText("The room turns to you.")).toBeInTheDocument();
    expect(vi.mocked(postTurn)).toHaveBeenCalledWith(
      embergate.id,
      expect.objectContaining({ text: "I draw my blade." }),
      expect.anything(),
    );
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
