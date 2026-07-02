import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { Character } from "@/lib/types";
import type { SceneMessage } from "@/features/story-player/scene-data";
import { TranscriptBeat } from "./TranscriptBeat";

const MEI: Character = {
  id: "mei",
  name: "Mei",
  role: "Broker",
  color: "#8E2B1C",
  mono: "M",
  traits: "",
  speech: "",
} as Character;

function renderBeat(message: SceneMessage) {
  return render(
    <TranscriptBeat
      message={message}
      charById={(id) => (id === "mei" ? MEI : undefined)}
      onProfile={vi.fn()}
      choices={[]}
      onChoose={vi.fn()}
    />,
  );
}

describe("TranscriptBeat", () => {
  it("renders narrator prose upright (no italic — feedback #6)", () => {
    renderBeat({ kind: "narrator", text: "Rain ticks against the shutters." });
    const prose = screen.getByText("Rain ticks against the shutters.");
    expect(prose.className).not.toContain("italic");
  });

  it("renders a character's action label upright (no italic — feedback #6)", () => {
    renderBeat({ kind: "char", who: "mei", action: "leans in, low", text: "Careful." });
    const label = screen.getByText("leans in, low");
    expect(label.className).not.toContain("italic");
  });

  it("renders a character's thought and speech in one beat, thought before the bubble", () => {
    renderBeat({ kind: "char", who: "mei", thought: "Coin first, favor later.", text: "Fine." });
    // One message under a single named, focusable character button …
    expect(screen.getAllByRole("button", { name: "Mei" })).toHaveLength(1);
    // … the muted "thinks" prelude sits above the spoken bubble.
    const thought = screen.getByText("Coin first, favor later.");
    const speech = screen.getByText("Fine.");
    expect(screen.getByText("thinks")).toBeTruthy();
    expect(thought.className).toContain("text-ink-soft"); // muted, distinct from speech
    // Thought comes before the spoken bubble in document order.
    expect(thought.compareDocumentPosition(speech) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows a thought-only beat (no spoken bubble) when the character does not speak", () => {
    renderBeat({ kind: "char", who: "mei", thought: "He'll fold." });
    expect(screen.getByText("He'll fold.")).toBeTruthy();
    expect(screen.getByText("thinks")).toBeTruthy();
  });

  it("omits the thinks prelude when a beat carries only speech", () => {
    renderBeat({ kind: "char", who: "mei", text: "Fine." });
    expect(screen.queryByText("thinks")).toBeNull();
  });

  it("combines thought and speech into one box at the same text size (request #4)", () => {
    renderBeat({ kind: "char", who: "mei", thought: "Coin first.", text: "Fine." });
    const thought = screen.getByText("Coin first.");
    const speech = screen.getByText("Fine.");
    // Same font size for both — the thought is no longer a smaller, separate block.
    expect(thought.className).toContain("text-[15.5px]");
    expect(speech.className).toContain("text-[15.5px]");
    // Both live inside the SAME bubble container.
    const box = thought.closest("div");
    expect(box).not.toBeNull();
    expect(box?.contains(speech)).toBe(true);
  });

  it("bolds quoted dialogue inside the character bubble, keeping the quotes", () => {
    renderBeat({ kind: "char", who: "mei", text: 'I said "leave now" firmly.' });
    const strong = screen.getByText('"leave now"');
    expect(strong.tagName).toBe("STRONG"); // emphasized, quotes preserved
  });
});
