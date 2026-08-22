import { act, render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { StoryPlayerView, isPlayerAuthored } from "./StoryPlayerView";
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

  it("holds the chosen speaker's place while the turn streams, and clears it when it ends", async () => {
    // The cast rail is hidden below `lg`, so this is the only speaker signal on a narrow
    // viewport. A chosen speaker now opens their OWN beat immediately (the status strip
    // stands down for character phases rather than narrating the same moment twice), and
    // an empty placeholder must not outlive the turn that created it.
    const speaker = embergate.cast[0];
    let release = () => {};
    const parked = new Promise<void>((resolve) => {
      release = resolve;
    });
    vi.mocked(postTurn).mockImplementation(async function* () {
      yield {
        type: "trace", n: 1, step: "speaker", title: "up", detail: "",
        data: { characterId: speaker.id, name: speaker.name },
      } as TurnStreamFrame;
      await parked;
    });
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.type(screen.getByRole("textbox", { name: /your message/i }), "Well?");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(
      await screen.findByText(`${speaker.name} is composing a reply`),
    ).toBeInTheDocument();

    await act(async () => {
      release();
    });
    await waitFor(() =>
      expect(
        screen.queryByText(`${speaker.name} is composing a reply`),
      ).not.toBeInTheDocument(),
    );
  });

  it("selecting a suggestion writes it into the composer for review — no auto-send", async () => {
    vi.mocked(postTurn).mockClear(); // mocks persist across tests; count from a clean slate
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    // A suggestion now carries two actions — put it in the composer, or play it out — so the
    // primary one is named explicitly.
    await user.click(
      screen.getByRole("button", {
        name: /Put "Confront Maerin about the Captain" in the composer/i,
      }),
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
    await user.selectOptions(screen.getByRole("combobox", { name: /follow-up ideas/i }), "2");
    expect(vi.mocked(updateScenario)).toHaveBeenCalledWith(
      embergate.id,
      expect.objectContaining({ suggestionsCount: 2 }),
    );
    // ...and the beat-length tier, which is the whole point of the control: without the
    // PATCH the dropdown moves and the next turn is written at the old length.
    fireEvent.change(screen.getByRole("combobox", { name: /how much a character says/i }), {
      target: { value: "short" },
    });
    expect(vi.mocked(updateScenario)).toHaveBeenCalledWith(
      embergate.id,
      expect.objectContaining({ beatLength: "short" }),
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
    // Each suggestion is now a row with two actions (edit it, or play it out), so the row —
    // not the button — is the grid child.
    const choice = await screen.findByRole("button", { name: /Put "Alpha" in the composer/i });
    // The four choices share a 2-column grid container (a 2×2 layout).
    expect(choice.parentElement?.parentElement?.className).toMatch(/grid-cols-2/);
    expect(
      screen.getByRole("button", { name: /Put "Delta" in the composer/i }),
    ).toBeInTheDocument();
  });

  it("switches the center column between the chat and the story graph", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    // Starts in chat: transcript is present, no graph.
    expect(screen.getByText(/Lamplight gutters across the Saltworn/i)).toBeInTheDocument();
    expect(screen.queryByTestId("graph-view-stub")).not.toBeInTheDocument();

    // Chat mode offers the chat-only Inspector toggle — now inside the scene menu, which
    // is where the header's controls folded so it could gain capability while losing width.
    const openSceneMenu = async () =>
      user.click(screen.getByRole("button", { name: /scene menu/i }));
    await openSceneMenu();
    expect(
      screen.getByRole("menuitemcheckbox", { name: /turn inspector/i }),
    ).toBeInTheDocument();
    await user.keyboard("{Escape}");

    // Flip to Graph — the transcript is replaced by the graph view, and the
    // chat-only controls (Turn Inspector toggle) drop away.
    await user.click(screen.getByRole("button", { name: /^graph$/i }));
    expect(screen.getByTestId("graph-view-stub")).toBeInTheDocument();
    expect(screen.queryByText(/Lamplight gutters across the Saltworn/i)).not.toBeInTheDocument();
    await openSceneMenu();
    expect(
      screen.queryByRole("menuitemcheckbox", { name: /turn inspector/i }),
    ).not.toBeInTheDocument();
    await user.keyboard("{Escape}");

    // Flip back to Chat — the transcript and the Inspector toggle return.
    await user.click(screen.getByRole("button", { name: /^chat$/i }));
    expect(screen.getByText(/Lamplight gutters across the Saltworn/i)).toBeInTheDocument();
    expect(screen.queryByTestId("graph-view-stub")).not.toBeInTheDocument();
    await openSceneMenu();
    expect(
      screen.getByRole("menuitemcheckbox", { name: /turn inspector/i }),
    ).toBeInTheDocument();
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

describe("StoryPlayerView — what the scene knows", () => {
  it("opens the memory rail and closes the Inspector, and vice versa", async () => {
    // Two 340px columns cannot both dock, and they answer different questions anyway: this
    // one is the player's, the Inspector is the developer's.
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);

    // jsdom reports no media query match, so this is the narrow header: the memory toggle
    // lives in the scene menu rather than inline. (The rail bar's "Knows" trigger is the
    // other way to the same state.)
    await user.click(screen.getByRole("button", { name: /scene menu/i }));
    await user.click(screen.getByRole("menuitemcheckbox", { name: "What the scene knows" }));
    expect(
      screen.getByRole("complementary", { name: "What the scene knows" }),
    ).toBeInTheDocument();

    // The menu is still open — a toggle keeps it that way, so the state change the player
    // just made stays visible.
    await user.click(screen.getByRole("menuitemcheckbox", { name: "Turn Inspector" }));
    expect(screen.getByRole("complementary", { name: "Turn inspector" })).toBeInTheDocument();
    expect(
      screen.queryByRole("complementary", { name: "What the scene knows" }),
    ).not.toBeInTheDocument();
  });

  it("shows no memory edge until beats have actually dropped out", () => {
    // A marker that is always there stops meaning anything.
    render(<StoryPlayerView scenario={embergate} />);
    expect(screen.queryByRole("separator")).not.toBeInTheDocument();
  });
});

describe("StoryPlayerView keyboard", () => {
  it("opens and closes the shortcut sheet with ?", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);

    await user.keyboard("?");
    expect(screen.getByRole("dialog", { name: /keyboard shortcuts/i })).toBeInTheDocument();

    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /keyboard shortcuts/i })).not.toBeInTheDocument(),
    );
  });

  it("jumps to the message box with /", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.keyboard("/");
    expect(screen.getByRole("textbox", { name: /your message/i })).toHaveFocus();
  });

  it("types / into the composer instead of stealing it", async () => {
    // The first thing a player will do is type a slash in a sentence.
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    const box = screen.getByRole("textbox", { name: /your message/i });
    await user.click(box);
    await user.type(box, "he said and/or she did");
    expect(box).toHaveValue("he said and/or she did");
  });

  it("closes the memory rail with Escape", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    // Opened from the rail bar rather than the header menu: a toggle keeps the menu open, so
    // the header path would spend the first Escape closing the menu. Same state either way.
    await user.click(screen.getByRole("button", { name: "Knows" }));
    expect(
      screen.getByRole("complementary", { name: "What the scene knows" }),
    ).toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(
      screen.queryByRole("complementary", { name: "What the scene knows" }),
    ).not.toBeInTheDocument();
  });
});

describe("StoryPlayerView coach marks", () => {
  beforeEach(() => localStorage.clear());

  it("shows exactly one hint at a time", () => {
    render(<StoryPlayerView scenario={embergate} />);
    const hints = screen
      .getAllByRole("status")
      .filter((el) => /Type what you say|Speak as one of the cast|The cast is here/.test(el.textContent ?? ""));
    expect(hints).toHaveLength(1);
  });

  it("moves to the next hint once one is dismissed", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    expect(screen.getByText(/type what you say/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.getByText(/speak as one of the cast/i)).toBeInTheDocument();
  });

  it("counts acting on the thing as dismissing its hint", async () => {
    // Anything that can only be dismissed by its × eventually traps someone.
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.type(screen.getByRole("textbox", { name: /your message/i }), "hello");
    expect(screen.queryByText(/type what you say/i)).not.toBeInTheDocument();
  });

  it("offers the cast hint below lg now that the cast is reachable there", async () => {
    // jsdom's matchMedia reports no match, so this is the sub-`lg` case. The hint used to be
    // withheld here because it pointed at a rail that did not exist; it now points at the
    // Cast trigger above the composer, which does.
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.click(screen.getByRole("button", { name: "Got it" }));
    await user.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.getByText(/the cast is here/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Got it" }));
    expect(screen.queryByRole("button", { name: "Got it" })).not.toBeInTheDocument();
  });
});

describe("StoryPlayerView transcript search", () => {
  it("opens with Cmd+F when the player is not writing", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.keyboard("{Meta>}f{/Meta}");
    expect(screen.getByRole("search", { name: /search this scene/i })).toBeInTheDocument();
  });

  it("leaves Cmd+F to the browser while the composer has focus", async () => {
    // Someone mid-sentence reaching for find-in-page means the browser's. Stealing it there
    // is the same failure as a shortcut eating a keystroke.
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.click(screen.getByRole("textbox", { name: /your message/i }));
    await user.keyboard("{Meta>}f{/Meta}");
    expect(screen.queryByRole("search", { name: /search this scene/i })).not.toBeInTheDocument();
  });

  it("closes with Escape", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.keyboard("{Meta>}f{/Meta}");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("search", { name: /search this scene/i })).not.toBeInTheDocument();
  });

  it("marks the active match for assistive tech, not only by colour", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.keyboard("{Meta>}f{/Meta}");
    // The seeded scene's opening narration is searchable text.
    const box = screen.getByRole("searchbox", { name: /find in this scene/i });
    await user.type(box, "the");
    await waitFor(() =>
      expect(document.querySelector('[aria-current="true"]')).toBeInTheDocument(),
    );
  });
});


describe("StoryPlayerView single-character shortcuts (WCAG 2.1.4)", () => {
  beforeEach(() => localStorage.clear());

  it("responds to / by default", async () => {
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.keyboard("/");
    expect(screen.getByRole("textbox", { name: /your message/i })).toHaveFocus();
  });

  it("can be turned off, which is what the criterion actually requires", async () => {
    // Standing down inside text fields is necessary and is none of the three things WCAG
    // 2.1.4 accepts: a screen-reader user browsing the transcript is not in a text field.
    localStorage.setItem("mytheca-scene-shortcuts", "off");
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);

    await user.keyboard("/");
    expect(screen.getByRole("textbox", { name: /your message/i })).not.toHaveFocus();

    await user.keyboard("?");
    expect(screen.queryByRole("dialog", { name: /keyboard shortcuts/i })).not.toBeInTheDocument();
  });
});


describe("StoryPlayerView — Edit is offered only on the player's own words", () => {
  it("gives an AI beat Re-roll but no Edit", async () => {
    // The owner's rule: the player may rewrite what they said, and nothing else. The
    // record's answer to a bad line from the cast is Re-roll, which regenerates it in
    // place and keeps the previous wording as a take.
    const speaker = embergate.cast[0];
    vi.mocked(postTurn).mockImplementation(
      streamOf({
        type: "character_dialogue",
        id: "d1",
        seq: 1,
        scenarioId: embergate.id,
        sessionId: "ps_live",
        ts: "t",
        visibility: "public",
        data: { characterId: speaker.id, text: "The room turns to you.", done: true },
      } as TurnStreamFrame),
    );
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} />);
    await user.type(screen.getByRole("textbox", { name: /your message/i }), "I draw my blade.");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await screen.findByText("The room turns to you.");

    const bar = await screen.findByRole("toolbar", { name: new RegExp(`Actions for ${speaker.name}`, "i") });
    expect(bar).toBeInTheDocument();
    expect(within(bar).queryByRole("button", { name: /^Edit /i })).not.toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: /^Re-roll /i })).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: /^Rewind to /i })).toBeInTheDocument();
  });
});

describe("isPlayerAuthored", () => {
  it("is true for the player's own line", () => {
    expect(isPlayerAuthored({ kind: "player", text: "I stand." })).toBe(true);
  });

  it("is true for a POV line — the player wrote it, whoever's name it wears", () => {
    expect(isPlayerAuthored({ kind: "char", who: "mei", fromPlayer: true, text: "Sit." })).toBe(true);
  });

  it("is false for the cast's own prose and for the narration", () => {
    expect(isPlayerAuthored({ kind: "char", who: "mei", text: "Sit." })).toBe(false);
    expect(isPlayerAuthored({ kind: "narrator", text: "The lamp gutters." })).toBe(false);
  });

  it("is false for beats that are not prose at all", () => {
    expect(isPlayerAuthored({ kind: "choices" })).toBe(false);
    expect(
      isPlayerAuthored({ kind: "image", image: { url: "/x.webp", caption: "", prompt: "" } }),
    ).toBe(false);
  });
});
