import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { SceneIntro } from "./SceneIntro";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
} from "@/lib/seed-data";

const embergate = resolveScenario(
  SEED_SCENARIOS[0],
  SEED_CHARACTERS,
  SEED_SETTINGS,
);

describe("SceneIntro", () => {
  it("surfaces the setting, genre/tone, goal, and cast", () => {
    render(<SceneIntro scenario={embergate} />);
    const band = screen.getByRole("region", { name: /scene overview/i });
    expect(band).toBeInTheDocument();
    expect(screen.getByText(/The Saltworn Tavern/)).toBeInTheDocument();
    expect(screen.getByText("Intrigue")).toBeInTheDocument();
    expect(screen.getByText(/Uncover who smuggles/i)).toBeInTheDocument();
    // Dramatis personae — each cast member named.
    expect(screen.getByText("Maerin Voss")).toBeInTheDocument();
    expect(screen.getByText("Wren Calloway")).toBeInTheDocument();
  });

  it("invokes onProfile when a cast member is clicked", async () => {
    const onProfile = vi.fn();
    const user = userEvent.setup();
    render(<SceneIntro scenario={embergate} onProfile={onProfile} />);
    await user.click(screen.getByRole("button", { name: /view maerin voss/i }));
    expect(onProfile).toHaveBeenCalledWith("maerin");
  });
});
