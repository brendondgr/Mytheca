import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { StoryPlayerView } from "./StoryPlayerView";
import { postTurn, updateScenario } from "@/lib/api";
import type { TurnStreamFrame } from "@/lib/events";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
  SEED_STAT_DEFS,
} from "@/lib/seed-data";

// Keep the real api (mediaUrl etc.) but stub the streaming turn + the scenario write-back.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  postTurn: vi.fn(),
  updateScenario: vi.fn().mockResolvedValue({}),
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

  it("selecting a suggestion writes it into the composer for review — no auto-send", async () => {
    vi.mocked(postTurn).mockClear(); // mocks persist across tests; count from a clean slate
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.click(
      screen.getByRole("button", { name: /confront maerin about the captain/i }),
    );
    // The suggested player text lands in the composer (focused for editing), not sent.
    const box = screen.getByRole("textbox", { name: /your message/i }) as HTMLInputElement;
    expect(box.value).toMatch(/afraid of him/i);
    expect(box).toHaveFocus();
    expect(vi.mocked(postTurn)).not.toHaveBeenCalled();
  });

  it("a streamed state_update moves the stat panel", async () => {
    const speaker = embergate.cast[0];
    vi.mocked(postTurn).mockImplementation(
      streamOf(
        {
          type: "state_update", id: "s1", seq: 1, scenarioId: embergate.id,
          sessionId: "ps", ts: "t", visibility: "public",
          data: { patch: {}, stat: { characterId: speaker.id, key: "suspicion", delta: 65, value: 67, reason: "pressed hard" } },
        } as TurnStreamFrame,
      ),
    );
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    expect(screen.getByText("+2")).toBeInTheDocument(); // Suspicion starts at +2
    await user.type(screen.getByRole("textbox", { name: /your message/i }), "I press her.");
    await user.click(screen.getByRole("button", { name: /send/i }));
    expect(await screen.findByText("+67")).toBeInTheDocument(); // clamped value from the stream
  });

  it("persists scene-config controls (suggestions + beats) to the scenario when changed", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    // The controls live in the scene-config popover — open it first.
    await user.click(screen.getByRole("button", { name: /scene configuration/i }));
    await user.selectOptions(screen.getByRole("combobox", { name: /suggestions/i }), "2");
    expect(vi.mocked(updateScenario)).toHaveBeenCalledWith(
      embergate.id,
      expect.objectContaining({ suggestionsCount: 2 }),
    );
    // The new "Number of beats" slider persists context_beats.
    fireEvent.change(screen.getByRole("slider", { name: /number of beats/i }), {
      target: { value: "40" },
    });
    expect(vi.mocked(updateScenario)).toHaveBeenCalledWith(
      embergate.id,
      expect.objectContaining({ contextBeats: 40 }),
    );
  });

  it("lays four follow-up suggestions out in a 2×2 grid", async () => {
    vi.mocked(postTurn).mockImplementation(
      streamOf({
        type: "branch_choices", id: "b1", seq: 1, scenarioId: embergate.id,
        sessionId: "ps", ts: "t", visibility: "public",
        data: {
          choices: [
            { label: "Alpha", outcome: "a" },
            { label: "Bravo", outcome: "b" },
            { label: "Charlie", outcome: "c" },
            { label: "Delta", outcome: "d" },
          ],
        },
      } as TurnStreamFrame),
    );
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.type(screen.getByRole("textbox", { name: /your message/i }), "go");
    await user.click(screen.getByRole("button", { name: /send/i }));
    const choice = await screen.findByRole("button", { name: /Alpha/i });
    // The four choices share a 2-column grid container (a 2×2 layout).
    expect(choice.parentElement?.className).toMatch(/grid-cols-2/);
    expect(screen.getByRole("button", { name: /Delta/i })).toBeInTheDocument();
  });
});
