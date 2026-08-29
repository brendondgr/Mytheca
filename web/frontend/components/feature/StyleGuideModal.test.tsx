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

vi.mock("@/lib/api", () => ({
  getStyleGuide: (...args: unknown[]) => getStyleGuide(...args),
  saveStylePreset: (...args: unknown[]) => saveStylePreset(...args),
}));

describe("StyleGuideModal", () => {
  beforeEach(() => {
    getStyleGuide.mockReset().mockResolvedValue(CATALOG);
    saveStylePreset.mockReset().mockResolvedValue(CATALOG);
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

  it("saves a preset under a slug derived from the heading", async () => {
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
    await waitFor(() =>
      expect(saveStylePreset).toHaveBeenCalledWith({
        id: "harrow-lane-narrative-style",
        name: "Harrow Lane — narrative style",
        blocks: { voice: "Plain." },
      }),
    );
  });
});
