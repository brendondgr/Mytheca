import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { TranscriptAnnouncer } from "./TranscriptAnnouncer";
import type { SceneMessage } from "@/features/story-player/scene-data";

const nameOf = (id?: string) => (id === "c1" ? "Mei" : (id ?? "Someone"));

function renderAnnouncer(messages: SceneMessage[], streaming: boolean) {
  return render(
    <TranscriptAnnouncer messages={messages} streaming={streaming} nameOf={nameOf} />,
  );
}

describe("TranscriptAnnouncer", () => {
  it("says nothing while a turn is still being written", () => {
    const { rerender } = renderAnnouncer([], false);
    rerender(
      <TranscriptAnnouncer
        messages={[{ kind: "narrator", text: "The door open" }]}
        streaming
        nameOf={nameOf}
      />,
    );
    // Announcing mid-stream would re-read the sentence from the beginning on
    // every delta — the backend re-emits full accumulated text, not fragments.
    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("announces the turn's beats once, on completion", () => {
    const { rerender } = renderAnnouncer([], false);

    const growing: SceneMessage[] = [{ kind: "narrator", text: "The door opens sl" }];
    rerender(<TranscriptAnnouncer messages={growing} streaming nameOf={nameOf} />);

    const done: SceneMessage[] = [
      { kind: "narrator", text: "The door opens slowly." },
      { kind: "char", who: "c1", text: '"You came."' },
    ];
    rerender(<TranscriptAnnouncer messages={done} streaming={false} nameOf={nameOf} />);

    const region = screen.getByRole("status");
    expect(region).toHaveTextContent("Narrator. The door opens slowly.");
    expect(region).toHaveTextContent('Mei said. "You came."');
  });

  it("announces only what the turn added, not the scene so far", () => {
    const prior: SceneMessage[] = [{ kind: "narrator", text: "An earlier beat." }];
    const { rerender } = renderAnnouncer(prior, false);

    rerender(<TranscriptAnnouncer messages={prior} streaming nameOf={nameOf} />);
    rerender(
      <TranscriptAnnouncer
        messages={[...prior, { kind: "char", who: "c1", text: '"New line."' }]}
        streaming={false}
        nameOf={nameOf}
      />,
    );

    const region = screen.getByRole("status");
    expect(region).toHaveTextContent('Mei said. "New line."');
    expect(region).not.toHaveTextContent("An earlier beat");
  });

  it("resolves character ids to names", () => {
    const { rerender } = renderAnnouncer([], false);
    rerender(<TranscriptAnnouncer messages={[]} streaming nameOf={nameOf} />);
    rerender(
      <TranscriptAnnouncer
        messages={[{ kind: "char", who: "c1", action: "leans in", thought: "He lied." }]}
        streaming={false}
        nameOf={nameOf}
      />,
    );
    // A screen-reader user must hear "Mei", never a database id.
    const region = screen.getByRole("status");
    expect(region).toHaveTextContent("Mei thinks, He lied.");
    expect(region).toHaveTextContent("Mei leans in");
    expect(region).not.toHaveTextContent("c1");
  });

  it("stays out of the layout so it cannot grow the root scroller", () => {
    renderAnnouncer([], false);
    // sr-only is position:absolute; with no positioned ancestor its containing
    // block is the initial containing block, so it escapes overflow:hidden and
    // grows the ROOT scroller. This repo has been bitten by exactly that.
    expect(screen.getByRole("status")).toHaveClass("sr-only");
  });
});
