import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { Character } from "@/lib/types";
import type { SceneMessage } from "@/features/story-player/scene-data";
import { CharacterMessage, TranscriptBeat } from "./TranscriptBeat";

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

  describe("player-authored POV beat (fromPlayer)", () => {
    it("renders on the player's side wearing the character's identity, not 'You'", () => {
      renderBeat({ kind: "char", who: "mei", fromPlayer: true, text: "I have nothing to say." });
      // The character's name is the identity; the "You" label is gone.
      expect(screen.getByText("Mei")).toBeTruthy();
      expect(screen.queryByText("You")).toBeNull();
      // The player's line renders, right-aligned (its own turn).
      const line = screen.getByText("I have nothing to say.");
      expect(line.closest(".justify-end")).not.toBeNull();
    });

    it("is not the interactive left-side AI bubble (no profile button for the character)", () => {
      renderBeat({ kind: "char", who: "mei", fromPlayer: true, text: "Fine." });
      // CharacterMessage exposes a focusable name button; PlayerAsCharacterMessage does not.
      expect(screen.queryByRole("button", { name: "Mei" })).toBeNull();
    });

    it("shows an optional action label alongside the identity", () => {
      renderBeat({ kind: "char", who: "mei", fromPlayer: true, action: "steps back", text: "Enough." });
      expect(screen.getByText("steps back")).toBeTruthy();
      expect(screen.getByText("Enough.")).toBeTruthy();
    });
  });
  describe("scene image", () => {
    it("renders a centered picture beat that opens the enlarged view", async () => {
      const onOpenImage = vi.fn();
      const image = {
        url: "/media/moments/abc.webp",
        caption: "Two figures at a lamplit table.",
        prompt: "two figures at a lamplit table",
      };
      render(
        <TranscriptBeat
          message={{ kind: "image", image }}
          charById={() => undefined}
          choices={[]}
          onChoose={vi.fn()}
          onOpenImage={onOpenImage}
        />,
      );
      expect(screen.getByAltText(image.caption)).toBeTruthy();
      screen.getByRole("button", { name: /enlarge scene image/i }).click();
      expect(onOpenImage).toHaveBeenCalledWith(image);
    });

    it("renders nothing for an image beat with no picture attached", () => {
      const { container } = render(
        <TranscriptBeat
          message={{ kind: "image" }}
          charById={() => undefined}
          choices={[]}
          onChoose={vi.fn()}
        />,
      );
      expect(container).toBeEmptyDOMElement();
    });
  });
});


describe("CharacterMessage — live reasoning", () => {
  const mei: Character = {
    id: "mei",
    name: "Mei",
    mono: "M",
    color: "#b07",
  } as Character;

  it("shows the raw deliberation behind a collapsed disclosure", () => {
    render(<CharacterMessage character={mei} reasoning="She is lying about the letter." text="" />);

    const disclosure = screen.getByText(/working/i);
    expect(disclosure).toBeInTheDocument();
    // Collapsed by default: it is machinery, and it routinely gives away the beat.
    expect(disclosure.closest("details")).not.toHaveAttribute("open");
  });

  it("renders nothing extra when there is no reasoning", () => {
    render(<CharacterMessage character={mei} text="Evening." />);
    expect(screen.queryByText(/working/i)).not.toBeInTheDocument();
  });

  it("keeps the prose readable alongside it", () => {
    render(
      <CharacterMessage character={mei} reasoning="deliberating" thought="Lie." text="I was home." />,
    );
    expect(screen.getByText(/I was home\./)).toBeInTheDocument();
    expect(screen.getByText(/Lie\./)).toBeInTheDocument();
  });
});
