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
  it("renders the seeded transcript beats (narrator, dialogue, choices — no dice)", () => {
    render(<StoryPlayerView scenario={embergate} />);
    expect(
      screen.getByText(/Lamplight gutters across the Saltworn/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/The tide doesn't wait/i)).toBeInTheDocument();
    expect(screen.getByText(/Your move/i)).toBeInTheDocument();
    expect(screen.queryByText("d20 check")).not.toBeInTheDocument(); // CheckCard retired (D11)
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

  it("selecting a branch submits a real turn; a streamed state_update moves the stat panel", async () => {
    const speaker = embergate.cast[0];
    vi.mocked(postTurn).mockImplementation(
      streamOf(
        {
          type: "character_dialogue", id: "d1", seq: 1, scenarioId: embergate.id,
          sessionId: "ps", ts: "t", visibility: "public",
          data: { characterId: speaker.id, text: "Afraid is a strong word.", done: true },
        } as TurnStreamFrame,
        {
          type: "state_update", id: "s1", seq: 2, scenarioId: embergate.id,
          sessionId: "ps", ts: "t", visibility: "public",
          data: { patch: {}, stat: { characterId: speaker.id, key: "suspicion", delta: 65, value: 67, reason: "pressed hard" } },
        } as TurnStreamFrame,
      ),
    );
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    expect(screen.getByText("+2")).toBeInTheDocument(); // Suspicion starts at +2
    await user.click(
      screen.getByRole("button", { name: /confront maerin about the captain/i }),
    );
    expect(await screen.findByText(/Afraid is a strong word/i)).toBeInTheDocument();
    expect(await screen.findByText("+67")).toBeInTheDocument(); // clamped value from the stream
    expect(vi.mocked(postTurn)).toHaveBeenCalled();
  });
});
