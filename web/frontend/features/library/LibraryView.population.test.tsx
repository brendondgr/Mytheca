import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { LibraryView } from "./LibraryView";
import * as api from "@/lib/api";
import { monoOf } from "@/lib/monogram";
import type { Character, Setting } from "@/lib/types";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

/**
 * The last link in the chain the world-population feature depends on: a world whose
 * cast and settings were generated at create time must actually SHOW them when the
 * author is redirected into it.
 *
 * This is the UI half of the regression guard (the backend half is
 * `utils/tests/backend/api/test_storyline_populate.py`). The recurring failure has
 * been generated content that exists but never reaches the columns, so this test
 * stands in for the freshly-created world: no seed data, only what population wrote.
 */

const GENERATED_CAST: Character[] = [
  {
    id: "c-gen-1",
    name: "Maerin Voss",
    role: "Smuggler",
    color: "#3A5A78",
    mono: monoOf("Maerin Voss"),
    traits: "wry · watchful",
    speech: "Clipped.",
    goal: "Clear the debt.",
    secret: "Sold the charts.",
    appearance: "Salt-bleached coat.",
    background: "Raised on the wharf.",
    personality: "Guarded.",
  } as Character,
  {
    id: "c-gen-2",
    name: "Harbormaster Cael",
    role: "Official",
    color: "#8E2B1C",
    mono: monoOf("Harbormaster Cael"),
    traits: "exacting",
    speech: "Formal.",
    goal: "Keep the ledger clean.",
    secret: "Two sets of books.",
  } as Character,
];

const GENERATED_PLACES: Setting[] = [
  {
    id: "s-gen-1",
    name: "The Salt Wharf",
    type: "Social Hub",
    desc: "Where cargo changes hands.",
    atmosphere: "Tar and cold rope.",
    features: "Crane, ledger house.",
    currentState: "Dawn, low tide.",
  } as Setting,
];

function asFreshlyPopulatedWorld() {
  vi.mocked(api.listStorylines).mockResolvedValue([
    {
      id: "newworld",
      title: "New World",
      genre: "Maritime",
      tagline: "Just created.",
      symbol: "◆",
      symbolColor: "#C8862A",
    },
  ] as never);
  vi.mocked(api.listCharacters).mockResolvedValue(GENERATED_CAST as never);
  vi.mocked(api.listSettings).mockResolvedValue(GENERATED_PLACES as never);
  vi.mocked(api.listScenarios).mockResolvedValue([] as never);
}

describe("LibraryView — a freshly populated world", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    asFreshlyPopulatedWorld();
  });

  it("loads the new world's generated cast and settings on redirect", async () => {
    render(<LibraryView initialStorylineId="newworld" />);

    // The columns are fetched for the world the author was just sent to — not the
    // first storyline, and not a stale cache.
    expect(await screen.findByText("New World")).toBeInTheDocument();
    expect(vi.mocked(api.listCharacters)).toHaveBeenCalledWith("newworld");
    expect(vi.mocked(api.listSettings)).toHaveBeenCalledWith("newworld");
  });

  it("renders every generated character in the Characters column", async () => {
    const user = userEvent.setup();
    render(<LibraryView initialStorylineId="newworld" />);
    await screen.findByText("New World");

    await user.click(screen.getByRole("tab", { name: /characters/i }));
    const panel = await screen.findByRole("tabpanel", { name: /characters/i });

    expect(await within(panel).findByText("Maerin Voss")).toBeInTheDocument();
    expect(within(panel).getByText("Harbormaster Cael")).toBeInTheDocument();
    expect(within(panel).queryByText(/no characters/i)).not.toBeInTheDocument();
  });

  it("renders every generated setting in the Settings column", async () => {
    const user = userEvent.setup();
    render(<LibraryView initialStorylineId="newworld" />);
    await screen.findByText("New World");

    await user.click(screen.getByRole("tab", { name: /settings/i }));
    const panel = await screen.findByRole("tabpanel", { name: /settings/i });

    expect(await within(panel).findByText("The Salt Wharf")).toBeInTheDocument();
    expect(within(panel).queryByText(/no settings/i)).not.toBeInTheDocument();
  });
});
