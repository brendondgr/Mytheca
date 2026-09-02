import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { MemorySource } from "./MemorySource";

const getBeatMemory = vi.fn();
vi.mock("@/lib/api", () => ({
  getBeatMemory: (...args: unknown[]) => getBeatMemory(...args),
}));

const MEMORY = {
  id: "cm_1",
  characterId: "ch_dell",
  characterName: "Dell",
  gloss: "she went back for the cargo and left me under the water",
  quote: "I'm not dying for your conscience.",
  quoteSpeakerName: "Mara",
  scenarioId: "sc_tunnel",
  scenarioTitle: "The Flooded Tunnel",
  sessionId: "ps1",
  turnSeq: 6,
  eventId: "ev_source",
  inThisSession: true,
  contradictedBy: [],
};

function renderIt(props: Partial<React.ComponentProps<typeof MemorySource>> = {}) {
  return render(
    <MemorySource
      scenarioId="sc1"
      sessionId="ps1"
      eventId="ev_beat"
      label="Dell's beat"
      {...props}
    />,
  );
}

describe("MemorySource", () => {
  beforeEach(() => {
    getBeatMemory.mockReset();
    getBeatMemory.mockResolvedValue({ eventId: "ev_beat", memories: [MEMORY] });
  });

  it("asks for nothing until the player opens it", () => {
    renderIt();
    expect(getBeatMemory).not.toHaveBeenCalled();
  });

  it("shows the moment and the verbatim line it was written with", async () => {
    const user = userEvent.setup();
    renderIt();
    await user.click(screen.getByRole("button", { name: /what dell's beat was remembering/i }));

    expect(await screen.findByText(/went back for the cargo/i)).toBeInTheDocument();
    expect(screen.getByText(/I'm not dying for your conscience/)).toBeInTheDocument();
    expect(screen.getByText(/Mara/)).toBeInTheDocument();
    expect(screen.getByText(/The Flooded Tunnel/)).toBeInTheDocument();
  });

  it("warns that someone remembers it differently, before they say so", async () => {
    // Without this a player reasonably reads the disagreement as the app losing track.
    getBeatMemory.mockResolvedValue({
      eventId: "ev_beat",
      memories: [
        {
          ...MEMORY,
          contradictedBy: [
            { characterId: "ch_mara", characterName: "Mara", gloss: "he told me to go" },
          ],
        },
      ],
    });
    const user = userEvent.setup();
    renderIt();
    await user.click(screen.getByRole("button", { name: /remembering/i }));

    expect(await screen.findByText(/remembers this differently/i)).toBeInTheDocument();
    expect(screen.getByText(/he told me to go/i)).toBeInTheDocument();
  });

  it("treats an empty result as an answer, not a failure", async () => {
    getBeatMemory.mockResolvedValue({ eventId: "ev_beat", memories: [] });
    const user = userEvent.setup();
    renderIt();
    await user.click(screen.getByRole("button", { name: /remembering/i }));

    expect(await screen.findByText(/nothing carried over/i)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("jumps to the source beat and closes", async () => {
    const user = userEvent.setup();
    const onJumpTo = vi.fn();
    renderIt({ onJumpTo });
    await user.click(screen.getByRole("button", { name: /remembering/i }));
    await user.click(await screen.findByRole("button", { name: /jump to it/i }));

    expect(onJumpTo).toHaveBeenCalledWith("ev_source");
  });

  it("offers no jump for a memory from an earlier scenario", async () => {
    // It is real history, but it is not in this transcript — and a link that silently does
    // nothing is worse than no link.
    getBeatMemory.mockResolvedValue({
      eventId: "ev_beat",
      memories: [{ ...MEMORY, inThisSession: false }],
    });
    const user = userEvent.setup();
    renderIt({ onJumpTo: vi.fn() });
    await user.click(screen.getByRole("button", { name: /remembering/i }));

    expect(await screen.findByText(/The Flooded Tunnel/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /jump to it/i })).not.toBeInTheDocument();
  });

  it("recovers from a failed read", async () => {
    getBeatMemory.mockRejectedValueOnce(new Error("nope"));
    const user = userEvent.setup();
    renderIt();
    await user.click(screen.getByRole("button", { name: /remembering/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    getBeatMemory.mockResolvedValue({ eventId: "ev_beat", memories: [MEMORY] });
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByText(/went back for the cargo/i)).toBeInTheDocument();
  });
});
