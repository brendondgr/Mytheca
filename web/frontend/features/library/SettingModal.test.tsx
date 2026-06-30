import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { LibraryView } from "./LibraryView";
import * as api from "@/lib/api";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

async function openSettingCreator(user: ReturnType<typeof userEvent.setup>) {
  render(<LibraryView />);
  await screen.findAllByText("The Embergate Conspiracy");
  await user.click(screen.getByRole("button", { name: /\+ create/i }));
  await user.click(screen.getByRole("button", { name: /add a setting/i }));
  return screen.getByRole("dialog");
}

describe("SettingModal — agentic creator", () => {
  it("drafts a full setting from a seed into the form", async () => {
    const user = userEvent.setup();
    const dialog = await openSettingCreator(user);

    await user.type(
      within(dialog).getByLabelText(/describe the place to draft/i),
      "A flooded smugglers' market.",
    );
    const draftBtn = within(dialog).getByRole("button", { name: /draft with velora/i });
    expect(draftBtn).toBeEnabled();
    await user.click(draftBtn);

    expect(vi.mocked(api.draftSetting)).toHaveBeenCalled();
    await waitFor(() =>
      expect(within(dialog).getByLabelText(/^name$/i)).toHaveValue("Drafted Place"),
    );
    expect(within(dialog).getByLabelText(/atmosphere & senses/i)).toHaveValue(
      "A drafted atmosphere.",
    );
    expect(within(dialog).getByLabelText(/notable features/i)).toHaveValue("Drafted features.");
    expect(within(dialog).getByLabelText(/current state/i)).toHaveValue(
      "A drafted current state.",
    );
  });

  it("generates scene-art prompts, then renders an establishing image", async () => {
    const user = userEvent.setup();
    const dialog = await openSettingCreator(user);

    // A description enables "Generate prompts". The scene-art flow lives in a
    // pop-up reached from the compact preview's "Edit image" button.
    await user.type(within(dialog).getByLabelText(/atmosphere & senses/i), "A drowned chapel.");
    await user.click(within(dialog).getByRole("button", { name: /edit image/i }));
    const sceneArt = screen.getByRole("dialog", { name: /^scene art$/i });

    await user.click(within(sceneArt).getByRole("button", { name: /generate prompts/i }));
    await waitFor(() => {
      const positive = within(sceneArt).getByLabelText(
        /scene-art positive prompt/i,
      ) as HTMLTextAreaElement;
      expect(positive.value).toContain("watercolor");
    });

    // Rendering the image calls ComfyUI and shows the WebP preview.
    await user.click(within(sceneArt).getByRole("button", { name: /generate scene art/i }));
    expect(vi.mocked(api.generateSceneArt)).toHaveBeenCalledWith(
      expect.objectContaining({ positive: expect.stringContaining("watercolor") }),
    );
    await waitFor(() =>
      expect(screen.getAllByAltText(/establishing image of/i).length).toBeGreaterThan(0),
    );
  });

  it("creates a setting with its node metadata", async () => {
    const user = userEvent.setup();
    const dialog = await openSettingCreator(user);

    await user.type(within(dialog).getByLabelText(/^name$/i), "The Lantern Quay");
    await user.type(
      within(dialog).getByLabelText(/atmosphere & senses/i),
      "Swaying lights over black water.",
    );
    const submit = within(dialog).getByRole("button", { name: /add setting/i });
    expect(submit).toBeEnabled();
    await user.click(submit);

    expect(vi.mocked(api.createSetting)).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        name: "The Lantern Quay",
        atmosphere: "Swaying lights over black water.",
      }),
    );
    expect(await screen.findByText("The Lantern Quay")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("grounds the draft with a dropped reference file's text", async () => {
    const user = userEvent.setup();
    const dialog = await openSettingCreator(user);

    const file = new File(["Built on a sunken reef. GAZETTEER_MARKER"], "gazetteer.md", {
      type: "text/markdown",
    });
    await user.upload(within(dialog).getByLabelText(/browse files/i), file);
    expect(
      await within(dialog).findByRole("button", { name: /remove gazetteer\.md/i }),
    ).toBeInTheDocument();

    await user.type(
      within(dialog).getByLabelText(/describe the place to draft/i),
      "A reef-built harbor.",
    );
    await user.click(within(dialog).getByRole("button", { name: /draft with velora/i }));
    await waitFor(() =>
      expect(vi.mocked(api.draftSetting)).toHaveBeenCalledWith(
        "A reef-built harbor.",
        expect.stringContaining("GAZETTEER_MARKER"),
        expect.any(String),
      ),
    );
  });

  it("drafts from a Draft-tagged reference file alone (no seed sentence)", async () => {
    const user = userEvent.setup();
    const dialog = await openSettingCreator(user);

    // With no seed typed, the Draft button is disabled.
    const draftBtn = within(dialog).getByRole("button", { name: /draft with velora/i });
    expect(draftBtn).toBeDisabled();

    // Dropping a Draft-tagged file (Draft toggle defaults ON) enables it.
    const file = new File(["Built on a sunken reef. DOCONLY_MARKER"], "lore.md", {
      type: "text/markdown",
    });
    await user.upload(within(dialog).getByLabelText(/browse files/i), file);
    await within(dialog).findByRole("button", { name: /remove lore\.md/i });
    expect(draftBtn).toBeEnabled();

    await user.click(draftBtn);
    await waitFor(() =>
      expect(vi.mocked(api.draftSetting)).toHaveBeenCalledWith(
        "",
        expect.stringContaining("DOCONLY_MARKER"),
        expect.any(String),
      ),
    );
  });
});
