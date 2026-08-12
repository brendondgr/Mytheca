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

// Keep the real api (mediaUrl etc.) but stub the streaming turn + the scenario write-back,
// AND the async play-session/relationship/stats-baseline effects `useScenePlay` fires on
// mount — otherwise they hit real `fetch` in jsdom and resolve/reject at nondeterministic
// times, racing the click-driven state updates below (a flaky-composer source). Empty data
// keeps the seed scene.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  postTurn: vi.fn(),
  updateScenario: vi.fn().mockResolvedValue({}),
  listPlaySessions: vi.fn(async () => ({ sessions: [] })),
  getScenarioRelationships: vi.fn(async () => ({ relationships: [] })),
  closePlaySession: vi.fn(() => {}),
  getCharacterStats: vi.fn(async () => ({}) as Record<string, number>),
  getLlmContextWindow: vi.fn(async () => ({ maxContextTokens: 16384, source: "configured" as const })),
  postSceneMoment: vi.fn(),
}));

// The graph view is exercised in its own test; here we only verify the switch
// swaps it into the center column, so stub it (also avoids a real graph fetch).
vi.mock("@/components/feature/GraphView", () => ({
  GraphView: ({ scenarioId }: { scenarioId: string }) => (
    <div data-testid="graph-view-stub">graph:{scenarioId}</div>
  ),
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
    // "Your move" appears in both the choices eyebrow and the scene-pulse empty state —
    // confirm at least one instance of the choices heading is rendered.
    expect(screen.getAllByText(/Your move/i).length).toBeGreaterThan(0);
    expect(screen.queryByText("d20 check")).not.toBeInTheDocument(); // CheckCard retired (D11)
  });

  it("surfaces the storyline stat schema in the cast rail (beneath each name)", () => {
    render(<StoryPlayerView scenario={embergate} statDefs={SEED_STAT_DEFS} />);
    // The Director rail no longer carries its own unwired stat legend.
    expect(screen.queryByText("Character stats")).not.toBeInTheDocument();
    // Each public stat now renders beneath every cast member's name in the cast rail.
    expect(screen.getAllByText("Health").length).toBeGreaterThan(0);
  });

  it("renders the Director rail's Scene pulse log region", () => {
    render(<StoryPlayerView scenario={embergate} />);
    // The right rail now shows a live-feed log (role="log", aria-live="polite").
    const log = screen.getByRole("log");
    expect(log).toBeInTheDocument();
    expect(log).toHaveAttribute("aria-live", "polite");
    // Empty on mount — shows the quiet-state message.
    expect(screen.getByText(/The scene is quiet/i)).toBeInTheDocument();
  });

  it("Director rail does NOT show Scene goal or Tension sections (regression)", () => {
    render(<StoryPlayerView scenario={embergate} />);
    expect(screen.queryByText("Scene goal")).not.toBeInTheDocument();
    expect(screen.queryByText("Tension")).not.toBeInTheDocument();
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
    const box = screen.getByRole("textbox", { name: /your message/i }) as HTMLTextAreaElement;
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

  it("switches the center column between the chat and the story graph", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    // Starts in chat: transcript is present, no graph.
    expect(screen.getByText(/Lamplight gutters across the Saltworn/i)).toBeInTheDocument();
    expect(screen.queryByTestId("graph-view-stub")).not.toBeInTheDocument();

    // Chat mode shows the chat-only Inspector toggle.
    expect(screen.getByRole("button", { name: /inspector/i })).toBeInTheDocument();

    // Flip to Graph — the transcript is replaced by the graph view, and the
    // chat-only controls (Turn Inspector toggle) drop away.
    await user.click(screen.getByRole("button", { name: /^graph$/i }));
    expect(screen.getByTestId("graph-view-stub")).toBeInTheDocument();
    expect(screen.queryByText(/Lamplight gutters across the Saltworn/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /inspector/i })).not.toBeInTheDocument();

    // Flip back to Chat — the transcript and the Inspector toggle return.
    await user.click(screen.getByRole("button", { name: /^chat$/i }));
    expect(screen.getByText(/Lamplight gutters across the Saltworn/i)).toBeInTheDocument();
    expect(screen.queryByTestId("graph-view-stub")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /inspector/i })).toBeInTheDocument();
  });
});

describe("StoryPlayerView create image", () => {
  const bar = () => screen.queryByRole("region", { name: /create an image of this moment/i });

  it("is absent before any turn has been taken", () => {
    render(<StoryPlayerView scenario={embergate} />);
    expect(bar()).not.toBeInTheDocument();
  });

  it("appears once the turn ends, at the foot of the transcript", async () => {
    const speaker = embergate.cast[0];
    vi.mocked(postTurn).mockImplementation(
      streamOf({
        type: "character_dialogue",
        id: "d-img",
        seq: 1,
        scenarioId: embergate.id,
        sessionId: "ps_img",
        ts: "t",
        visibility: "public",
        data: { characterId: speaker.id, text: "The room turns to you.", done: true },
      } as TurnStreamFrame),
    );
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    expect(bar()).not.toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: /your message/i }), "I wait.");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await screen.findByText("The room turns to you.");

    const control = await screen.findByRole("region", {
      name: /create an image of this moment/i,
    });
    expect(screen.getByRole("button", { name: /^go$/i })).toBeEnabled();
    // It sits after every transcript beat in document order (the very bottom of the chat).
    const lastBeat = screen.getByText("The room turns to you.");
    expect(
      lastBeat.compareDocumentPosition(control) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });
});
