import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
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
    expect(screen.queryByText(/background/i)).not.toBeInTheDocument();
  });

  it("shows traits in the header", () => {
    render(<CharacterProfileModal character={base} onClose={() => {}} />);
    expect(screen.getByText("Patient · Calculating")).toBeInTheDocument();
  });

  it("shows all 2-column rows when all fields are present", () => {
    render(
      <CharacterProfileModal
        character={{
          ...base,
          appearance: "Tall.",
          background: "Merchant family.",
          personality: "Cold.",
        }}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(/appearance/i)).toBeInTheDocument();
    expect(screen.getByText(/background/i)).toBeInTheDocument();
    expect(screen.getByText(/personality/i)).toBeInTheDocument();
    expect(screen.getByText(/voice/i)).toBeInTheDocument();
    expect(screen.getByText(/goal/i)).toBeInTheDocument();
    expect(screen.getByText(/secret/i)).toBeInTheDocument();
  });

  it("shows Edit Character button when onEdit is provided and calls it on click", async () => {
    const user = userEvent.setup();
    const onEdit = vi.fn();
    render(<CharacterProfileModal character={base} onClose={() => {}} onEdit={onEdit} />);
    const btn = screen.getByRole("button", { name: /edit character/i });
    expect(btn).toBeInTheDocument();
    await user.click(btn);
    expect(onEdit).toHaveBeenCalledWith("mei");
  });

  it("hides Edit Character button when onEdit is omitted", () => {
    render(<CharacterProfileModal character={base} onClose={() => {}} />);
    expect(screen.queryByRole("button", { name: /edit character/i })).not.toBeInTheDocument();
  });
});
