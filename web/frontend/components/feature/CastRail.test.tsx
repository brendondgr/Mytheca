import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CastRail, CastRailContent } from "./CastRail";
import type { Character, StatDefinition } from "@/lib/types";

function char(id: string, name: string): Character {
  return {
    id, name, role: "Role", color: "#000", mono: name.slice(0, 2).toUpperCase(),
    traits: "", speech: "", goal: "", secret: "",
  };
}

const cast = [char("mei", "Mei"), char("kira", "Kira")];
const noop = () => undefined;

function renderRail(props: Partial<React.ComponentProps<typeof CastRail>> = {}) {
  return render(
    <CastRail
      cast={cast}
      speakingId={null}
      turnOrder={["You", "mei", "kira"]}
      charById={(id) => cast.find((c) => c.id === id)}
      onProfile={noop}
      presenceByChar={{}}
      {...props}
    />,
  );
}

describe("CastRail presence", () => {
  it("groups present vs. out-of-scene and marks the dead with a strike", () => {
    renderRail({ presenceByChar: { kira: "dead" } });
    expect(screen.getByText("In the Scene")).toBeTruthy();
    expect(screen.getByText("Out of the Scene")).toBeTruthy();
    // Kira is dead → shows the "Dead" badge and a struck-through name.
    expect(screen.getByText("Dead")).toBeTruthy();
    expect(screen.getByText("Kira").className).toContain("line-through");
    // Mei stays present → no strike.
    expect(screen.getByText("Mei").className).not.toContain("line-through");
  });

  it("has no Out-of-the-Scene group when everyone is present", () => {
    renderRail();
    expect(screen.queryByText("Out of the Scene")).toBeNull();
  });

  it("fires setPresence when the per-character control changes", () => {
    const setPresence = vi.fn();
    renderRail({ setPresence });
    fireEvent.change(screen.getByLabelText("Presence for Mei"), { target: { value: "left" } });
    expect(setPresence).toHaveBeenCalledWith("mei", "left");
  });

  it("omits the control when no setPresence handler is given (read-only)", () => {
    renderRail();
    expect(screen.queryByLabelText("Presence for Mei")).toBeNull();
  });
});

const STAT_DEFS: StatDefinition[] = [
  { key: "trust", displayName: "Trust", description: "", min: -10, max: 10, default: 0, visibility: "public", guidance: null, appliesTo: [], bands: [] },
  { key: "morale", displayName: "Morale", description: "", min: 0, max: 10, default: 5, visibility: "hidden", guidance: null, appliesTo: [], bands: [] },
];

describe("CastRail activity status", () => {
  it("shows 'Thinking' label and the typing-dots element when activity is 'thinking'", () => {
    renderRail({ activityByChar: { mei: "thinking" } });
    expect(screen.getByText("Thinking")).toBeInTheDocument();
    expect(screen.getByTestId("typing-dots")).toBeInTheDocument();
  });

  it("shows 'Speaking' label when activity is 'speaking'", () => {
    renderRail({ activityByChar: { mei: "speaking" } });
    expect(screen.getByText("Speaking")).toBeInTheDocument();
  });

  it("shows no status label for idle characters", () => {
    renderRail({ activityByChar: { mei: "idle" } });
    expect(screen.queryByText("Thinking")).toBeNull();
    expect(screen.queryByText("Speaking")).toBeNull();
  });

  it("shows no status label when activityByChar is omitted", () => {
    renderRail();
    expect(screen.queryByText("Thinking")).toBeNull();
    expect(screen.queryByText("Speaking")).toBeNull();
  });
});

describe("CastRail stats", () => {
  it("renders no stat rows when statDefs is omitted (back-compat)", () => {
    renderRail();
    expect(screen.queryByText("Trust")).toBeNull();
  });

  it("shows each public stat's schema default beneath a cast member's name", () => {
    renderRail({ statDefs: STAT_DEFS });
    expect(screen.getAllByText("Trust")).toHaveLength(2); // Mei + Kira
    expect(screen.getAllByText("0")).toHaveLength(2); // schema default
  });

  it("prefers a live statsByChar value over the schema default", () => {
    renderRail({ statDefs: STAT_DEFS, statsByChar: { mei: [{ label: "Trust", value: 7, reason: "" }] } });
    expect(screen.getByText("7")).toBeInTheDocument();
    // Kira has no live entry — still shows the schema default.
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("omits non-public stats from the cast rail", () => {
    renderRail({ statDefs: STAT_DEFS });
    expect(screen.queryByText("Morale")).toBeNull();
  });
});

describe("CastRail — Elsewhere in the World", () => {
  const mei = char("mei", "Mei");
  const kael = char("kael", "Kael");
  const base = {
    cast: [mei],
    speakingId: null,
    turnOrder: [],
    charById: (id: string) => [mei, kael].find((c) => c.id === id),
    onProfile: () => {},
  };

  it("offers the storyline characters this scene never cast", () => {
    // The scenario's authored roster is not the whole world, and a play-through can invite
    // someone in without the scenario being re-authored.
    render(<CastRail {...base} storylineCast={[mei, kael]} setPresence={() => {}} />);
    expect(screen.getByText("Elsewhere in the World")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Bring Kael into the scene" }),
    ).toBeInTheDocument();
  });

  it("does not offer someone already in the scene", () => {
    render(<CastRail {...base} storylineCast={[mei]} setPresence={() => {}} />);
    expect(screen.queryByText("Elsewhere in the World")).not.toBeInTheDocument();
  });

  it("brings them in through the ordinary presence path", () => {
    const setPresence = vi.fn();
    render(<CastRail {...base} storylineCast={[mei, kael]} setPresence={setPresence} />);
    fireEvent.click(screen.getByRole("button", { name: "Bring Kael into the scene" }));
    expect(setPresence).toHaveBeenCalledWith("kael", "present");
  });

  it("explains why the control is unavailable before the first turn", () => {
    // There is no session to attach a presence change to yet, so the button says so rather
    // than failing silently.
    render(
      <CastRail {...base} storylineCast={[mei, kael]} setPresence={() => {}} joinDisabled />,
    );
    const button = screen.getByRole("button", { name: "Bring Kael into the scene" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("title", expect.stringMatching(/play a turn first/i));
  });

  it("hides the section entirely when presence cannot be set at all", () => {
    render(<CastRail {...base} storylineCast={[mei, kael]} />);
    expect(screen.queryByRole("button", { name: /bring kael/i })).not.toBeInTheDocument();
  });
});


describe("CastRail shell vs. content", () => {
  it("names its landmark, so it is distinguishable from the other rail", () => {
    renderRail();
    expect(screen.getByRole("complementary", { name: "Cast" })).toBeInTheDocument();
  });

  it("renders the same sections with no landmark of its own", () => {
    // What the bottom sheet mounts. It must carry the rail's capabilities — the presence
    // control, the turn order — while adding no second `complementary` to the page.
    render(
      <CastRailContent
        cast={cast}
        speakingId={null}
        turnOrder={["You", "mei", "kira"]}
        charById={(id) => cast.find((c) => c.id === id)}
        onProfile={noop}
        setPresence={vi.fn()}
      />,
    );
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(screen.getByText("In the Scene")).toBeInTheDocument();
    expect(screen.getByText("Turn order")).toBeInTheDocument();
    expect(screen.getByLabelText("Presence for Mei")).toBeInTheDocument();
  });
});

describe("CastRail presence select density", () => {
  it("carries the shared compact field size, not 16px monospace at every width", () => {
    // The same complaint as the config popover, repeated once per cast member down a rail
    // that is a bottom sheet on a phone. `Select` keeps 16px on a coarse pointer — where iOS
    // Safari would otherwise zoom the viewport on focus — and drops to the dense size on a
    // fine one.
    renderRail({ setPresence: vi.fn() });
    const select = screen.getAllByRole("combobox", { name: /^presence for /i })[0];
    expect(select.className).toContain("text-field");
    expect(select.className).toContain("pointer-fine:text-ui");
  });

  it("still offers every presence state", () => {
    renderRail({ setPresence: vi.fn() });
    const select = screen.getAllByRole("combobox", { name: /^presence for /i })[0];
    expect(
      [...select.querySelectorAll("option")].map((o) => (o as HTMLOptionElement).value),
    ).toEqual(["present", "unconscious", "departed", "left", "dead"]);
  });
});
