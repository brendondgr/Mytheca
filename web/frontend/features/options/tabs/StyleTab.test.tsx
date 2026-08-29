import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { StyleTab } from "./StyleTab";

const getStyleGuide = vi.fn();
const deleteStylePreset = vi.fn();

vi.mock("@/lib/api", () => ({
  getStyleGuide: (...a: unknown[]) => getStyleGuide(...a),
  deleteStylePreset: (...a: unknown[]) => deleteStylePreset(...a),
}));

const BUILTIN = {
  id: "romance",
  name: "Romance",
  blurb: "Close and unsaid.",
  blocks: { voice: "Less." },
  builtin: true,
};
const MINE = {
  id: "harrow",
  name: "Harrow",
  blurb: "",
  blocks: { voice: "Plain.", never: "No recaps." },
  builtin: false,
};

describe("StyleTab", () => {
  beforeEach(() => {
    getStyleGuide.mockReset().mockResolvedValue({ blocks: [], presets: [BUILTIN, MINE] });
    deleteStylePreset.mockReset().mockResolvedValue({ blocks: [], presets: [BUILTIN] });
  });

  it("separates the built-ins from the author's own", async () => {
    render(<StyleTab />);
    expect(await screen.findByText("Romance")).toBeInTheDocument();
    expect(screen.getByText("Harrow")).toBeInTheDocument();
    expect(screen.getByText("2 of 6 blocks")).toBeInTheDocument();
  });

  it("offers delete for a saved preset and not for a built-in", async () => {
    render(<StyleTab />);
    await screen.findByText("Romance");
    expect(screen.getByRole("button", { name: /delete harrow/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete romance/i })).not.toBeInTheDocument();
  });

  it("deletes a saved preset and re-renders from the returned catalog", async () => {
    const user = userEvent.setup();
    render(<StyleTab />);
    await screen.findByText("Harrow");
    await user.click(screen.getByRole("button", { name: /delete harrow/i }));
    await waitFor(() => expect(deleteStylePreset).toHaveBeenCalledWith("harrow"));
    await waitFor(() => expect(screen.queryByText("Harrow")).not.toBeInTheDocument());
  });

  it("says what to do when nothing has been saved yet", async () => {
    getStyleGuide.mockResolvedValue({ blocks: [], presets: [BUILTIN] });
    render(<StyleTab />);
    expect(await screen.findByText(/none yet/i)).toBeInTheDocument();
  });

  it("offers a retry when the list fails to load", async () => {
    const user = userEvent.setup();
    getStyleGuide.mockRejectedValueOnce(new Error("offline"));
    render(<StyleTab />);
    expect(await screen.findByRole("alert")).toHaveTextContent("offline");
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByText("Romance")).toBeInTheDocument();
  });
});
