import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { Character } from "@/lib/types";
import type { SceneChoice, SceneMessage } from "@/features/story-player/scene-data";
import { BranchChoices, CharacterMessage, TranscriptBeat } from "./TranscriptBeat";

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
    expect(thought.className).toContain("text-body-sm");
    expect(speech.className).toContain("text-body-sm");
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

describe("BranchChoices", () => {
  const CHOICES: SceneChoice[] = [
    { id: "1", label: "Follow him", outcome: "escalate", player: "", follow: { who: "", text: "" } },
    { id: "2", label: "Let him go", outcome: "de-escalate", player: "", follow: { who: "", text: "" } },
  ];

  it("offers follow-ups without a question when the planner did not ask", () => {
    render(<BranchChoices choices={CHOICES} onChoose={vi.fn()} />);
    expect(screen.getByText("Your move — choose a path")).toBeInTheDocument();
    expect(screen.getByText("Follow him")).toBeInTheDocument();
  });

  it("leads with the planner's question when it asked instead of guessing", () => {
    render(
      <BranchChoices
        choices={CHOICES}
        onChoose={vi.fn()}
        prompt="Do you want to go after him, or let him go?"
      />,
    );
    expect(screen.getByText("The story is asking you")).toBeInTheDocument();
    expect(
      screen.getByText("Do you want to go after him, or let him go?"),
    ).toBeInTheDocument();
    // The options are suggested answers, still pickable.
    expect(screen.getByText("Let him go")).toBeInTheDocument();
  });

  it("renders a question that came with no options at all", () => {
    // The player answers in the composer; an empty options grid must not take up space.
    const { container } = render(
      <BranchChoices choices={[]} onChoose={vi.fn()} prompt="Where do you want this to go?" />,
    );
    expect(screen.getByText("Where do you want this to go?")).toBeInTheDocument();
    expect(container.querySelector(".hidden")).not.toBeNull();
  });

  it("routes the question through the transcript beat that carries it", () => {
    render(
      <TranscriptBeat
        message={{ kind: "choices", text: "Follow, or let him go?" }}
        charById={() => undefined}
        onProfile={vi.fn()}
        choices={CHOICES}
        onChoose={vi.fn()}
      />,
    );
    expect(screen.getByText("Follow, or let him go?")).toBeInTheDocument();
  });
});

describe("attachment chips on a persisted player beat", () => {
  const nameOf = (id: string) =>
    ({ cd_1: "harbor notes.md", cd_2: "ledger.md" })[id as "cd_1" | "cd_2"];

  it("shows the files a past turn carried", () => {
    render(
      <TranscriptBeat
        message={{ kind: "player", text: "Read this.", id: "u0", taggedDocIds: ["cd_1", "cd_2"] }}
        charById={() => undefined}
        choices={[]}
        onChoose={() => {}}
        docNameOf={nameOf}
      />,
    );
    expect(screen.getByText("harbor notes.md")).toBeInTheDocument();
    expect(screen.getByText("ledger.md")).toBeInTheDocument();
  });

  it("shows nothing when the turn carried no files", () => {
    render(
      <TranscriptBeat
        message={{ kind: "player", text: "Just words.", id: "u0" }}
        charById={() => undefined}
        choices={[]}
        onChoose={() => {}}
        docNameOf={nameOf}
      />,
    );
    expect(screen.queryByLabelText(/files this turn carried/i)).not.toBeInTheDocument();
  });

  it("skips an id whose document has since been deleted, rather than rendering a blank chip", () => {
    render(
      <TranscriptBeat
        message={{ kind: "player", text: "x", id: "u0", taggedDocIds: ["cd_gone"] }}
        charById={() => undefined}
        choices={[]}
        onChoose={() => {}}
        docNameOf={nameOf}
      />,
    );
    expect(screen.queryByLabelText(/files this turn carried/i)).not.toBeInTheDocument();
  });
});

describe("TranscriptBeat direction aside", () => {
  it("renders a direction as a quiet aside, not a speech bubble", () => {
    render(
      <TranscriptBeat
        message={{ kind: "direction", text: "Someone should lose their temper.", id: "u0" }}
        charById={() => undefined}
        choices={[]}
        onChoose={() => {}}
      />,
    );
    // The label is part of the text, so a screen reader gets the same distinction the
    // centred typography gives a sighted reader.
    expect(
      screen.getByText(/you directed the scene: Someone should lose their temper\./i),
    ).toBeInTheDocument();
  });
});

describe("BranchChoices — Play it out", () => {
  const CHOICES = [
    {
      id: "c1", label: "Take the deal", outcome: "she takes the deal", player: "I take it.",
      follow: { who: "", text: "" },
    },
  ];

  it("keeps the primary click as edit-first", () => {
    // A suggestion is a starting point, and the player's own wording is the point of the app.
    const onChoose = vi.fn();
    render(
      <TranscriptBeat
        message={{ kind: "choices" }}
        charById={() => undefined}
        choices={CHOICES}
        onChoose={onChoose}
        onPlayOut={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: 'Put "Take the deal" in the composer to edit' }));
    expect(onChoose).toHaveBeenCalledWith(CHOICES[0]);
  });

  it("offers a second action that runs it now", () => {
    const onPlayOut = vi.fn();
    const onChoose = vi.fn();
    render(
      <TranscriptBeat
        message={{ kind: "choices" }}
        charById={() => undefined}
        choices={CHOICES}
        onChoose={onChoose}
        onPlayOut={onPlayOut}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: 'Play out "Take the deal"' }));
    expect(onPlayOut).toHaveBeenCalledWith(CHOICES[0]);
    expect(onChoose).not.toHaveBeenCalled();
  });

  it("hides the second action when the parent does not offer it", () => {
    render(
      <TranscriptBeat
        message={{ kind: "choices" }}
        charById={() => undefined}
        choices={CHOICES}
        onChoose={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /play out/i })).not.toBeInTheDocument();
  });

  it("blocks both while a turn is in flight — but not merely for want of a session", () => {
    render(
      <TranscriptBeat
        message={{ kind: "choices" }}
        charById={() => undefined}
        choices={CHOICES}
        onChoose={() => {}}
        onPlayOut={() => {}}
        turnInFlight
      />,
    );
    for (const b of screen.getAllByRole("button")) expect(b).toBeDisabled();
  });
});

describe("BranchChoices session gating", () => {
  const CHOICES = [
    {
      id: "c1", label: "Take the deal", outcome: "o", player: "I take it.",
      follow: { who: "", text: "" },
    },
  ];

  it("stays usable before the first turn has created a session", () => {
    // A suggestion only writes into the composer, and "Play it out" creates the session the
    // way any first turn does — gating it on an existing session made the chips dead on a
    // fresh scene, which is exactly when suggestions matter most.
    render(
      <TranscriptBeat
        message={{ kind: "choices" }}
        charById={() => undefined}
        choices={CHOICES}
        onChoose={() => {}}
        onPlayOut={() => {}}
        castRequestDisabled
      />,
    );
    for (const b of screen.getAllByRole("button")) expect(b).not.toBeDisabled();
  });
});

