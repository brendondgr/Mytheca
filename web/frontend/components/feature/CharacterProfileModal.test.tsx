import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { CharacterProfileModal } from "./CharacterProfileModal";
import type { Character } from "@/lib/types";

const base: Character = {
  id: "mei",
  name: "Mei Voss",
  role: "Antagonist",
  color: "#8E2B1C",
  mono: "MV",
  traits: "Patient · Calculating",
  speech: "Measured.",
  goal: "Hide the routes.",
  secret: "Answers to the Court.",
};

describe("CharacterProfileModal", () => {
  it("shows base-identity prose and the portrait when present", () => {
    render(
      <CharacterProfileModal
        character={{
          ...base,
          appearance: "Tall, silver at the temples.",
          background: "Rose through the salt guild.",
          personality: "Gracious, cold beneath.",
          portrait: "/media/portraits/mei.webp",
        }}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText("Tall, silver at the temples.")).toBeInTheDocument();
    expect(screen.getByText("Rose through the salt guild.")).toBeInTheDocument();
    expect(screen.getByText("Gracious, cold beneath.")).toBeInTheDocument();
    // Portrait replaces the monogram initials.
    expect(screen.getByAltText("Portrait of Mei Voss")).toBeInTheDocument();
    expect(screen.queryByText("MV")).not.toBeInTheDocument();
  });

  it("falls back to the monogram and omits empty prose lines", () => {
    render(<CharacterProfileModal character={base} onClose={() => {}} />);
    expect(screen.getByText("MV")).toBeInTheDocument();
    expect(screen.queryByText(/appearance/i)).not.toBeInTheDocument();
  });
});
