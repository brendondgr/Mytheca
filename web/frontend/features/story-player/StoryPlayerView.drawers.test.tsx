import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { StoryPlayerView } from "./StoryPlayerView";
import { postTurn } from "@/lib/api";
import type { TurnStreamFrame } from "@/lib/events";
import {
  resolveScenario,
  SEED_CHARACTERS,
  SEED_SCENARIOS,
  SEED_SETTINGS,
  SEED_STAT_DEFS,
} from "@/lib/seed-data";

// Same stubs as the sibling route test: keep the real api helpers, silence the streaming
// turn and the async mount effects that would otherwise hit `fetch` in jsdom.
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  postTurn: vi.fn(),
  updateScenario: vi.fn().mockResolvedValue({}),
  listPlaySessions: vi.fn(async () => ({ sessions: [] })),
  getScenarioRelationships: vi.fn(async () => ({ relationships: [] })),
  closePlaySession: vi.fn(() => {}),
  getCharacterStats: vi.fn(async () => ({}) as Record<string, number>),
  getLlmContextWindow: vi.fn(async () => ({ maxContextTokens: 16384, source: "configured" as const })),
  postSceneMoment: vi.fn(),
}));

vi.mock("@/components/feature/GraphView", () => ({
  GraphView: () => <div data-testid="graph-view-stub" />,
}));

const embergate = resolveScenario(SEED_SCENARIOS[0], SEED_CHARACTERS, SEED_SETTINGS);

function streamOf(...frames: TurnStreamFrame[]) {
  return async function* () {
    for (const f of frames) yield f;
  };
}

/**
 * jsdom reports `matchMedia(...).matches === false` for every query, so `useMediaQuery`
 * answers `false` and the component is in exactly the sub-`lg` state these tests are about.
 * The desktop rails are still in the DOM (CSS is what hides them, and jsdom has none), which
 * is precisely why every assertion below is scoped `within` the dialog — a bare `getByText`
 * would happily find the desktop copy and prove nothing.
 */
async function openDrawer(name: "Cast" | "Scene") {
  const user = userEvent.setup();
  render(<StoryPlayerView scenario={embergate} statDefs={SEED_STAT_DEFS} />);
  return { user, ...(await raise(user, name)) };
}

/**
 * Open one rail sheet from the scene menu.
 *
 * The rails used to have a bar of their own above the composer — a third horizontal band
 * of chrome on the narrowest screen in the app. They are menu rows now, which means two
 * taps rather than one, and it means the ROW is gone by the time the sheet is open: it
 * closes the menu behind it, so a sheet that landed under an open panel cannot happen.
 *
 * `trigger` is therefore the menu button, not the row. That is also where focus returns
 * when the sheet closes, and the reason `SceneMenu.close` focuses its trigger
 * synchronously.
 */
async function raise(user: ReturnType<typeof userEvent.setup>, name: "Cast" | "Scene") {
  const trigger = screen.getByRole("button", { name: /scene menu/i });
  await user.click(trigger);
  await user.click(screen.getByRole("menuitemcheckbox", { name: new RegExp(`^${name}(,|$)`) }));
  return { trigger, dialog: screen.getByRole("dialog") };
}

/**
 * Drive `useMediaQuery` the way a resize does. Returns a `setWidth` that flips what
 * `(min-width: 1024px)` reports and notifies the listeners the hook subscribed with.
 */
function mockWidth(initial: number) {
  let width = initial;
  const listeners = new Set<() => void>();
  window.matchMedia = ((query: string) =>
    ({
      get matches() {
        const min = Number(/min-width:\s*(\d+)px/.exec(query)?.[1] ?? NaN);
        return Number.isNaN(min) ? false : width >= min;
      },
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: (_: string, fn: () => void) => listeners.add(fn),
      removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList) as typeof window.matchMedia;
  return (next: number) => {
    width = next;
    act(() => listeners.forEach((fn) => fn()));
  };
}

describe("story player rail drawers — the capabilities that used to be lost below lg", () => {
  it("the Cast sheet carries the presence control, the stat values and the turn order", async () => {
    // Every item here is on the checklist of things a phone could not reach at all.
    const { dialog } = await openDrawer("Cast");
    const cast = within(dialog);

    expect(cast.getByRole("heading", { name: "Cast" })).toBeInTheDocument();
    expect(
      cast.getByLabelText(`Presence for ${embergate.cast[0].name}`),
    ).toBeInTheDocument();
    expect(cast.getAllByText("Health").length).toBeGreaterThan(0);
    expect(cast.getByText("Turn order")).toBeInTheDocument();
  });

  it("the Scene sheet carries the pulse, the scene state and the direction checklist", async () => {
    vi.mocked(postTurn).mockImplementation(
      streamOf({
        type: "trace",
        step: "direction",
        data: { requirements: ["Mei admits the letter"] },
      } as unknown as TurnStreamFrame),
    );
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} statDefs={SEED_STAT_DEFS} />);

    // Direct the scene, so there is a checklist to find.
    await user.type(screen.getByRole("textbox", { name: /your message/i }), "Ask her.");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await screen.findAllByText("Mei admits the letter");

    await raise(user, "Scene");
    const sheet = within(screen.getByRole("dialog"));
    expect(sheet.getByText("Scene pulse")).toBeInTheDocument();
    expect(sheet.getByText("Scene state")).toBeInTheDocument();
    expect(sheet.getByText("Mei admits the letter")).toBeInTheDocument();
  });

  it("the Scene trigger advertises what the turn still owes", async () => {
    vi.mocked(postTurn).mockImplementation(
      streamOf({
        type: "trace",
        step: "direction",
        data: { requirements: ["Mei admits the letter", "Beth leaves"] },
      } as unknown as TurnStreamFrame),
    );
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} statDefs={SEED_STAT_DEFS} />);
    const openMenu = () => user.click(screen.getByRole("button", { name: /scene menu/i }));
    await openMenu();
    expect(screen.getByRole("menuitemcheckbox", { name: "Scene" })).toBeInTheDocument();
    await user.keyboard("{Escape}");

    await user.type(screen.getByRole("textbox", { name: /your message/i }), "Ask her.");
    await user.click(screen.getByRole("button", { name: /send/i }));

    // The count still rides in the row's NAME rather than beside it as a bare numeral —
    // "Scene 2" tells a screen-reader user nothing. One tap deeper than it used to be,
    // and that is the trade the menu makes.
    await openMenu();
    expect(
      await screen.findByRole("menuitemcheckbox", { name: "Scene, 2 still owed" }),
    ).toBeInTheDocument();
  });

  it("the pulse inside the sheet does not announce a backlog on open", async () => {
    // It mounts when the sheet opens. Announcing the whole turn at that moment would talk
    // over everything else, after the fact.
    const { dialog } = await openDrawer("Scene");
    expect(within(dialog).getByRole("log")).toHaveAttribute("aria-live", "off");
  });

  it("tapping a character in the Cast sheet switches it to their dossier", async () => {
    // Without this, a tap on a phone sets `profileId` and renders it nowhere — which reads
    // as the app ignoring the tap.
    const { user, dialog } = await openDrawer("Cast");
    const who = embergate.cast[0];
    await user.click(within(dialog).getByRole("button", { name: new RegExp(who.name) }));

    const dossier = screen.getByRole("dialog", { name: `${who.name} — profile` });
    expect(within(dossier).getByRole("heading", { name: who.name })).toBeInTheDocument();
    expect(within(dossier).getByText("Relationships")).toBeInTheDocument();
  });

  it("Escape closes the sheet and puts focus back on its trigger", async () => {
    const { user, trigger } = await openDrawer("Cast");
    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("never has two sheets open at once", async () => {
    const { user } = await openDrawer("Cast");
    await raise(user, "Scene");
    expect(screen.getAllByRole("dialog")).toHaveLength(1);
    expect(screen.getByRole("dialog", { name: "Scene" })).toBeInTheDocument();
  });

  it("the row toggles its own sheet shut", async () => {
    const { user } = await openDrawer("Cast");
    await user.click(screen.getByRole("button", { name: /scene menu/i }));
    await user.click(screen.getByRole("menuitemcheckbox", { name: /^Cast(,|$)/ }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("story player rail drawers across the lg boundary", () => {
  it("closes the sheet on widening and does NOT reopen it on narrowing back", async () => {
    // The bug this exists to prevent, caught in a real browser: masking the state behind a
    // width check leaves a stale "cast", so narrowing back raises a modal dialog nobody asked
    // for and moves focus into it.
    const setWidth = mockWidth(375);
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} statDefs={SEED_STAT_DEFS} />);

    await raise(user, "Cast");
    expect(screen.getByRole("dialog", { name: "Cast" })).toBeInTheDocument();

    setWidth(1280);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    setWidth(375);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("the trigger still works on the first tap after a width round-trip", async () => {
    // The other half of the same defect: a stale state makes the next tap toggle nothing.
    const setWidth = mockWidth(375);
    const user = userEvent.setup();
    render(<StoryPlayerView scenario={embergate} statDefs={SEED_STAT_DEFS} />);

    await raise(user, "Cast");
    setWidth(1280);
    setWidth(375);

    await raise(user, "Cast");
    expect(screen.getByRole("dialog", { name: "Cast" })).toBeInTheDocument();
  });
});
