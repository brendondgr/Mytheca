import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { SceneMemoryPanel } from "./SceneMemoryPanel";
import userEvent from "@testing-library/user-event";
import { getSceneKnowledge, postSessionRecap } from "@/lib/api";
import type { SceneKnowledge } from "@/lib/events";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getSceneKnowledge: vi.fn(),
  postSessionRecap: vi.fn(),
}));

const KNOWLEDGE: SceneKnowledge = {
  windowBeats: 40,
  windowSource: "detected",
  droppedBeats: 12,
  budgetTokens: 8000,
  promptTokens: 5120,
  taggedNames: ["harbor.md"],
  retrieval: { fired: true, reason: "fetch — named lore", matched: true },
  relationships: ["Mei: You owe Aldous a debt."],
  direction: {
    text: "The lamp goes over.",
    items: ["the lamp goes over", "Mei backs down"],
    delivered: ["the lamp goes over"],
    outstanding: ["Mei backs down"],
  },
  summary: { text: "Earlier, Mei arrived.", throughSeq: 12, updatedAt: null },
};

/**
 * One mock style throughout — `mockImplementation`, never `mockResolvedValue`.
 *
 * Mixing them is not cosmetic here: a `beforeEach` that installs `mockResolvedValue` and a
 * test that then overrides with a rejection produces a rejected promise the runner reports as
 * unhandled, even though the component catches it (verified against the component in
 * isolation). Keeping one style avoids a failure that looks like a product defect and is not.
 */
function reads(value: SceneKnowledge) {
  vi.mocked(getSceneKnowledge).mockImplementation(() => Promise.resolve(value));
}

describe("SceneMemoryPanel", () => {
  beforeEach(() => reads(KNOWLEDGE));

  it("renders nothing when closed", () => {
    const { container } = render(
      <SceneMemoryPanel open={false} onClose={() => {}} scenarioId="s" sessionId="ps" />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("says what it will show before there is a session to show it for", () => {
    // A blank rail before the first turn teaches nothing; this says what the player will get.
    const before = vi.mocked(getSceneKnowledge).mock.calls.length;
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId={null} />);
    expect(screen.getByText(/play a turn and this will show/i)).toBeInTheDocument();
    // Nothing to ask about yet, so nothing is asked.
    expect(vi.mocked(getSceneKnowledge).mock.calls.length).toBe(before);
  });

  it("answers the player's question, not the developer's", async () => {
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId="ps" />);
    // How far back it remembers, in words and figures.
    expect(await screen.findByText(/how far back the cast remembers/i)).toBeInTheDocument();
    expect(screen.getByText(/12 older beats have been folded into a summary/i)).toBeInTheDocument();
    // What was attached, what was looked up, who it knows about whom.
    expect(screen.getByText("harbor.md")).toBeInTheDocument();
    expect(screen.getByText(/folded in what it found/i)).toBeInTheDocument();
    expect(screen.getByText(/Mei: You owe Aldous a debt\./)).toBeInTheDocument();
  });

  it("shows what was asked for and what landed, by glyph AND wording", async () => {
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId="ps" />);
    expect(await screen.findByText("the lamp goes over")).toBeInTheDocument();
    // Never colour alone: the unconfirmed one says so in words.
    expect(screen.getByText(/Mei backs down — not confirmed/)).toBeInTheDocument();
  });

  it("shows the folded memory itself, read-only", async () => {
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId="ps" />);
    expect(await screen.findByText("Earlier, Mei arrived.")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("says when the window size was guessed rather than reported", async () => {
    // "We asked the model" and "we guessed" are different claims, and only one deserves to
    // be trusted with a full window.
    reads({ ...KNOWLEDGE, windowSource: "fallback" });
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId="ps" />);
    expect(await screen.findByText(/a conservative default is in force/i)).toBeInTheDocument();
  });

  it("offers a retry rather than a dead end when the read fails", async () => {
    vi.mocked(getSceneKnowledge).mockImplementation(() => Promise.reject(new Error("offline")));
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId="ps" />);
    await waitFor(() =>
      expect(screen.getByText(/could not be read/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: /try again|retry/i })).toBeInTheDocument();
  });

  it("invites the player to act when the scene has done nothing yet", async () => {
    reads({
      ...KNOWLEDGE,
      windowBeats: 0,
      direction: { text: "", items: [], delivered: [], outstanding: [] },
    });
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId="ps" />);
    expect(await screen.findByText(/nothing yet/i)).toBeInTheDocument();
  });

  it("is a labelled region so it can be reached and left", async () => {
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId="ps" />);
    expect(
      screen.getByRole("complementary", { name: "What the scene knows" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /close/i })).toBeInTheDocument();
  });
});

describe("SceneMemoryPanel recap", () => {
  beforeEach(() => {
    reads(KNOWLEDGE);
    vi.mocked(postSessionRecap).mockImplementation(() =>
      Promise.resolve({ text: "Mei arrived, then the lamp went over." }),
    );
  });

  it("offers a recap and renders it inline", async () => {
    const user = userEvent.setup();
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId="ps" />);
    await user.click(await screen.findByRole("button", { name: /recap the scene/i }));
    expect(
      await screen.findByText("Mei arrived, then the lamp went over."),
    ).toBeInTheDocument();
  });

  it("keeps the facts on screen while the recap is being written", async () => {
    // Asking for one more thing must not blank out what is already there.
    const user = userEvent.setup();
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId="ps" />);
    await user.click(await screen.findByRole("button", { name: /recap the scene/i }));
    expect(screen.getByText(/how far back the cast remembers/i)).toBeInTheDocument();
  });

  it("says so rather than looking broken when there is nothing to recap", async () => {
    vi.mocked(postSessionRecap).mockImplementation(() => Promise.resolve({ text: "" }));
    const user = userEvent.setup();
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId="ps" />);
    await user.click(await screen.findByRole("button", { name: /recap the scene/i }));
    expect(await screen.findByText(/nothing to recap yet/i)).toBeInTheDocument();
  });

  it("reports a failure without taking the panel down with it", async () => {
    vi.mocked(postSessionRecap).mockImplementation(() => Promise.reject(new Error("offline")));
    const user = userEvent.setup();
    render(<SceneMemoryPanel open onClose={() => {}} scenarioId="s" sessionId="ps" />);
    await user.click(await screen.findByRole("button", { name: /recap the scene/i }));
    expect(await screen.findByText(/could not be written just now/i)).toBeInTheDocument();
    expect(screen.getByText(/how far back the cast remembers/i)).toBeInTheDocument();
  });
});

