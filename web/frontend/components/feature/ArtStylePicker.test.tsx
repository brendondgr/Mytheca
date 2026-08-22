import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ArtStylePicker } from "./ArtStylePicker";
import { resetArtStylesCache } from "@/hooks/use-art-styles";
import { COMFY_FIXTURE } from "@/test/api-mock";

const getSettings = vi.fn();
vi.mock("@/lib/api", () => ({
  getSettings: (...args: unknown[]) => getSettings(...args),
}));

function withStyles(artStyle = "painted") {
  getSettings.mockResolvedValue({ comfy: { ...COMFY_FIXTURE, artStyle } });
}

beforeEach(() => {
  resetArtStylesCache();
  getSettings.mockReset();
  withStyles();
});

async function renderPicker(props: Partial<Parameters<typeof ArtStylePicker>[0]> = {}) {
  const onChange = props.onChange ?? vi.fn();
  render(<ArtStylePicker onChange={onChange} {...props} />);
  await screen.findByRole("radio", { name: /painted/i });
  return { onChange };
}

describe("ArtStylePicker", () => {
  it("offers the three styles as one radio group", async () => {
    await renderPicker();
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => (r as HTMLInputElement).value)).toEqual([
      "painted",
      "anime",
      "photoreal",
    ]);
    // One group, so arrow keys move within it and it takes a single tab stop.
    const names = new Set(radios.map((r) => (r as HTMLInputElement).name));
    expect(names.size).toBe(1);
  });

  it("names the group so a screen reader announces what is being chosen", async () => {
    await renderPicker();
    expect(screen.getByRole("group", { name: /art style/i })).toBeInTheDocument();
  });

  it("shows each style's blurb, so the look is named and not just labelled", async () => {
    await renderPicker();
    expect(screen.getByText(/watercolor and oil washes/i)).toBeInTheDocument();
    expect(screen.getByText(/cel-shaded/i)).toBeInTheDocument();
  });

  it("pre-selects the operator's default when no value is given", async () => {
    withStyles("photoreal");
    await renderPicker();
    expect(screen.getByRole("radio", { name: /photoreal/i })).toBeChecked();
    expect(screen.getByRole("radio", { name: /painted/i })).not.toBeChecked();
  });

  it("reflects an explicit value over the default", async () => {
    withStyles("photoreal");
    await renderPicker({ value: "anime" });
    expect(screen.getByRole("radio", { name: /anime/i })).toBeChecked();
  });

  it("reports the chosen style", async () => {
    const { onChange } = await renderPicker();
    await userEvent.click(screen.getByRole("radio", { name: /anime/i }));
    expect(onChange).toHaveBeenCalledWith("anime");
  });

  it("is reachable and operable by keyboard alone", async () => {
    const { onChange } = await renderPicker();
    await userEvent.tab();
    expect(screen.getByRole("radio", { name: /painted/i })).toHaveFocus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("anime");
  });

  it("hides the blurbs in the compact variant, where space is scarce", async () => {
    await renderPicker({ compact: true });
    expect(screen.getAllByRole("radio")).toHaveLength(3);
    expect(screen.queryByText(/watercolor and oil washes/i)).not.toBeInTheDocument();
  });

  it("disables every option when the surface is busy", async () => {
    await renderPicker({ disabled: true });
    for (const radio of screen.getAllByRole("radio")) expect(radio).toBeDisabled();
  });

  it("renders nothing when the catalog cannot be loaded", async () => {
    getSettings.mockRejectedValue(new Error("offline"));
    const { container } = render(<ArtStylePicker onChange={vi.fn()} />);
    await waitFor(() => expect(getSettings).toHaveBeenCalled());
    // The render button beside it still works, on the stored default.
    expect(container.querySelector("fieldset")).toBeNull();
  });

  it("fetches the catalog once however many pickers mount", async () => {
    render(
      <>
        <ArtStylePicker onChange={vi.fn()} />
        <ArtStylePicker onChange={vi.fn()} />
        <ArtStylePicker onChange={vi.fn()} label="Another" />
      </>,
    );
    await screen.findAllByRole("radio", { name: /painted/i });
    expect(getSettings).toHaveBeenCalledTimes(1);
  });
});
