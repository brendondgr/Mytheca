import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { StyleGuideModal } from "./StyleGuideModal";

const CATALOG = {
  blocks: [
    {
      id: "voice",
      label: "Voice",
      helper: "How people sound.",
      placeholder: "People talk around it…",
      reader: "prose",
      placement: "prefix",
    },
  ],
  presets: [
    {
      id: "romance",
      name: "Romance",
      blurb: "Close and unsaid.",
      blocks: { voice: "Less than they mean." },
      builtin: true,
    },
  ],
};

const getStyleGuide = vi.fn();
const saveStylePreset = vi.fn();
const reviseStyleGuide = vi.fn();

vi.mock("@/lib/api", () => ({
  getStyleGuide: (...args: unknown[]) => getStyleGuide(...args),
  saveStylePreset: (...args: unknown[]) => saveStylePreset(...args),
  reviseStyleGuide: (...args: unknown[]) => reviseStyleGuide(...args),
}));

describe("StyleGuideModal", () => {
  beforeEach(() => {
    getStyleGuide.mockReset().mockResolvedValue(CATALOG);
    saveStylePreset.mockReset().mockResolvedValue(CATALOG);
    reviseStyleGuide.mockReset().mockResolvedValue({ styleBlocks: { voice: "Clipped and cold." } });
  });

  it("fetches the catalog on open and renders the editor", async () => {
    render(
      <StyleGuideModal
        open
        onClose={vi.fn()}
        heading="Harrow Lane — narrative style"
        blocks={{}}
        onSave={vi.fn()}
      />,
    );
    expect(await screen.findByRole("textbox", { name: /voice — style/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Romance" })).toBeInTheDocument();
  });

  it("does not fetch while closed", () => {
    render(
      <StyleGuideModal
        open={false}
        onClose={vi.fn()}
        heading="Harrow Lane"
        blocks={{}}
        onSave={vi.fn()}
      />,
    );
    expect(getStyleGuide).not.toHaveBeenCalled();
  });

  it("offers a retry when the catalog fails to load, rather than dead-ending", async () => {
    const user = userEvent.setup();
    getStyleGuide.mockRejectedValueOnce(new Error("offline"));
    render(
      <StyleGuideModal
        open
        onClose={vi.fn()}
        heading="Harrow Lane"
        blocks={{}}
        onSave={vi.fn()}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("offline");
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByRole("textbox", { name: /voice — style/i })).toBeInTheDocument();
  });

  it("saves the blocks and closes", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onClose = vi.fn();
    render(
      <StyleGuideModal
        open
        onClose={onClose}
        heading="Harrow Lane"
        blocks={{}}
        onSave={onSave}
      />,
    );
    await user.type(await screen.findByRole("textbox", { name: /voice — style/i }), "Plain.");
    await user.click(screen.getByRole("button", { name: /save style/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ voice: "Plain." }));
    expect(onClose).toHaveBeenCalled();
  });

  it("offers Save as preset at the world layer only", async () => {
    render(
      <StyleGuideModal
        open
        onClose={vi.fn()}
        heading="Harrow Lane"
        blocks={{ voice: "Plain." }}
        inherited={{ voice: "World." }}
        layer="scenario"
        onSave={vi.fn()}
      />,
    );
    await screen.findByRole("textbox", { name: /voice — style/i });
    // A scene's guide is a delta; saved standalone it would read as a whole guide and is not.
    expect(screen.queryByRole("button", { name: /save as preset/i })).not.toBeInTheDocument();
  });

  it("saves a preset under the name the AUTHOR types, slugged", async () => {
    // Slugged from the name, not the heading: two worlds saving "Slow Burn" should land on
    // one entry rather than silently creating two things called the same.
    const user = userEvent.setup();
    render(
      <StyleGuideModal
        open
        onClose={vi.fn()}
        heading="Harrow Lane — narrative style"
        blocks={{ voice: "Plain." }}
        onSave={vi.fn()}
      />,
    );
    await screen.findByRole("textbox", { name: /voice — style/i });
    await user.click(screen.getByRole("button", { name: /save as preset/i }));
    await user.type(screen.getByRole("textbox", { name: /preset name/i }), "Slow Burn");
    await user.click(screen.getByRole("button", { name: /^save preset$/i }));
    await waitFor(() =>
      expect(saveStylePreset).toHaveBeenCalledWith({
        id: "slow-burn",
        name: "Slow Burn",
        blocks: { voice: "Plain." },
      }),
    );
  });

  it("asks the model to revise and shows the result in the fields", async () => {
    const user = userEvent.setup();
    render(
      <StyleGuideModal
        open
        onClose={vi.fn()}
        heading="Harrow Lane"
        blocks={{ voice: "Plain." }}
        onSave={vi.fn()}
      />,
    );
    await screen.findByRole("textbox", { name: /voice — style/i });
    await user.type(screen.getByRole("textbox", { name: /ask the model/i }), "colder");
    await user.click(screen.getByRole("button", { name: /ask/i }));
    await waitFor(() =>
      expect(reviseStyleGuide).toHaveBeenCalledWith({
        instruction: "colder",
        current: { voice: "Plain." },
      }),
    );
    expect(await screen.findByDisplayValue("Clipped and cold.")).toBeInTheDocument();
  });
});
