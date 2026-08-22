import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CastRequestBeat } from "./CastRequestBeat";
import type { Character } from "@/lib/types";

const KAEL: Character = {
  id: "kael",
  name: "Kael",
  role: "smuggler",
  traits: [],
  speech: "",
  color: "#8E2B1C",
  mono: "K",
  portrait: null,
} as unknown as Character;

describe("CastRequestBeat", () => {
  it("asks rather than announces, and quotes the player's own words", () => {
    // The AI never brings anyone in. This is the whole feature: a question with two
    // answers and no default, raised only because the player named an absent character.
    render(<CastRequestBeat character={KAEL} reason="Kael bursts in" />);
    expect(screen.getByText(/The scene is asking for/i)).toBeInTheDocument();
    expect(screen.getByText(/“Kael bursts in”/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Bring them in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Not now" })).toBeInTheDocument();
  });

  it("answers both ways", () => {
    const onAccept = vi.fn();
    const onDecline = vi.fn();
    render(
      <CastRequestBeat character={KAEL} onAccept={onAccept} onDecline={onDecline} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Bring them in" }));
    expect(onAccept).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(onDecline).toHaveBeenCalledTimes(1);
  });

  it("becomes a settled line once answered, never a live control again", () => {
    // A reload must not re-offer a decision the player already made.
    render(<CastRequestBeat character={KAEL} resolved />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText(/you answered about Kael/i)).toBeInTheDocument();
  });

  it("shows the ask but refuses the answer when there is no scene yet", () => {
    render(<CastRequestBeat character={KAEL} disabled onAccept={() => {}} />);
    expect(screen.getByRole("button", { name: "Bring them in" })).toBeDisabled();
  });

  it("renders nothing for a character that has since been deleted", () => {
    const { container } = render(<CastRequestBeat character={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("names the character in the section's accessible name", () => {
    render(<CastRequestBeat character={KAEL} />);
    expect(screen.getByRole("region", { name: "The scene is asking for Kael" })).toBeInTheDocument();
  });
});
