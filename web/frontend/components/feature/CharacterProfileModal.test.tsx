import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { CharacterProfileModal } from "./CharacterProfileModal";
import type { Character, StatDefinition } from "@/lib/types";

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

  it("splits the traits string into one pill per trait", () => {
    render(<CharacterProfileModal character={base} onClose={() => {}} />);
    const pills = screen.getAllByRole("listitem");
    expect(pills.map((p) => p.textContent?.replace(/^◆/, "").trim())).toEqual([
      "Patient",
      "Calculating",
    ]);
  });

  it("renders no trait pills when traits is empty", () => {
    render(
      <CharacterProfileModal character={{ ...base, traits: "" }} onClose={() => {}} />,
    );
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("does not render the secret (removed from the profile view)", () => {
    render(<CharacterProfileModal character={base} onClose={() => {}} />);
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Answers to the Court.")).not.toBeInTheDocument();
  });

  it("shows Background + the Appearance/Personality/Voice/Goal sections (no Secret)", () => {
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
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();
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

const STAT_DEFS: StatDefinition[] = [
  { key: "trust", displayName: "Trust", description: "", min: -10, max: 10, default: 0, visibility: "public", guidance: null, appliesTo: [], bands: [] },
  { key: "morale", displayName: "Morale", description: "", min: 0, max: 10, default: 5, visibility: "hidden", guidance: null, appliesTo: [], bands: [] },
];

describe("CharacterProfileModal stats", () => {
  it("renders no Stats section when statDefs is omitted (back-compat)", () => {
    render(<CharacterProfileModal character={base} onClose={() => {}} />);
    expect(screen.queryByText("Stats")).not.toBeInTheDocument();
  });

  it("shows the real persisted value over the schema default, and omits non-public stats", () => {
    render(
      <CharacterProfileModal
        character={base}
        onClose={() => {}}
        statDefs={STAT_DEFS}
        statValues={{ trust: 7 }}
      />,
    );
    expect(screen.getByText("Stats")).toBeInTheDocument();
    expect(screen.getByText("Trust")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.queryByText("Morale")).not.toBeInTheDocument();
  });

  it("falls back to the schema default for a stat never explicitly set", () => {
    render(
      <CharacterProfileModal
        character={base}
        onClose={() => {}}
        statDefs={STAT_DEFS}
      />,
    );
    expect(screen.getByText("Trust")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
