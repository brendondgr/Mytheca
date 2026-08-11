import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, it, expect, vi } from "vitest";
import { StorylineCreatorView } from "./StorylineCreatorView";
import * as api from "@/lib/api";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

beforeEach(() => vi.clearAllMocks());

function md(name: string, text: string): File {
  return new File([text], name, { type: "text/markdown" });
}

describe("StorylineCreatorView", () => {
  it("renders the fields with the Assistant left sidebar and the Context right sidebar", () => {
    render(<StorylineCreatorView />);
    expect(screen.getByRole("heading", { name: /new storyline/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/^title$/i)).toBeInTheDocument();
    // Both sidebars are separate, always-visible landmarks (no tabs).
    expect(screen.getByRole("complementary", { name: /storyline assistant/i })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: /context files/i })).toBeInTheDocument();
  });

  it("triages dropped files into grouped buckets", async () => {
    const user = userEvent.setup();
    render(<StorylineCreatorView />);
    await user.upload(screen.getByLabelText(/browse files/i), md("hero.md", "A person."));
    expect(await screen.findByRole("button", { name: /remove hero\.md/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /triage uncategorized \(1\)/i }));
    expect(await screen.findByText(/character details/i)).toBeInTheDocument();
  });

  it("drops files pre-categorized when an 'Add as' bucket is chosen (no triage)", async () => {
    const user = userEvent.setup();
    render(<StorylineCreatorView />);
    await user.selectOptions(screen.getByRole("combobox", { name: /add as/i }), "character");
    await user.upload(screen.getByLabelText(/browse files/i), md("hero.md", "A person."));
    expect(await screen.findByText(/character details/i)).toBeInTheDocument();
    const row = screen.getByRole("combobox", { name: /category for hero\.md/i });
    expect(row).toHaveValue("character");
    expect(vi.mocked(api.triageDocumentsStream)).not.toHaveBeenCalled();
  });

  it("shows the context-budget meter", () => {
    render(<StorylineCreatorView />);
    expect(screen.getByText(/context budget/i)).toBeInTheDocument();
  });

  it("drafts via the Assistant and fills the form on approve", async () => {
    const user = userEvent.setup();
    render(<StorylineCreatorView />);
    await user.type(screen.getByLabelText(/message the assistant/i), "draft a title");
    await user.click(screen.getByRole("button", { name: /^send/i }));
    // The proposed plan renders; approving fills the Title field.
    expect(await screen.findByText("Assistant Draft")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /approve & fill form/i }));
    await waitFor(() => expect(screen.getByLabelText(/^title$/i)).toHaveValue("Assistant Draft"));
  });

  it("creates a storyline by hand and navigates to it", async () => {
    const { useRouter } = await import("next/navigation");
    const push = vi.mocked(useRouter().push);
    push.mockClear();
    const user = userEvent.setup();
    render(<StorylineCreatorView />);

    await user.type(screen.getByLabelText(/^title$/i), "Manual World");
    await user.click(screen.getByRole("button", { name: /create world/i }));
    // Creating asks what to build before it writes anything.
    expect(vi.mocked(api.createStoryline)).not.toHaveBeenCalled();
    await user.click(await screen.findByRole("button", { name: /just the world/i }));

    expect(vi.mocked(api.createStoryline)).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Manual World" }),
    );
    expect(vi.mocked(api.populateWorldStream)).not.toHaveBeenCalled();
    await waitFor(() => expect(push).toHaveBeenCalledWith(expect.stringMatching(/^\/sl-test/)));
  });

  it("builds the cast and settings into the world it just created, then navigates", async () => {
    const { useRouter } = await import("next/navigation");
    const push = vi.mocked(useRouter().push);
    push.mockClear();
    const user = userEvent.setup();
    render(<StorylineCreatorView />);

    await user.type(screen.getByLabelText(/^title$/i), "Populated World");
    await user.click(screen.getByRole("button", { name: /create world/i }));
    await user.click(await screen.findByRole("button", { name: /create & build/i }));

    // Population targets the id that was just created — the world the author lands in.
    await waitFor(() => expect(vi.mocked(api.populateWorldStream)).toHaveBeenCalled());
    const createdId = (await vi.mocked(api.createStoryline).mock.results[0].value).id;
    expect(vi.mocked(api.populateWorldStream)).toHaveBeenCalledWith(
      createdId,
      expect.objectContaining({ withArtwork: false }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/${createdId}`));
  });

  it("saves an edit without asking about population", async () => {
    const user = userEvent.setup();
    render(<StorylineCreatorView editId="embergate" />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /edit storyline/i })).toBeInTheDocument(),
    );

    await user.click(screen.getByRole("button", { name: /save changes/i }));

    expect(screen.queryByRole("dialog", { name: /build the cast/i })).not.toBeInTheDocument();
    expect(vi.mocked(api.populateWorldStream)).not.toHaveBeenCalled();
    await waitFor(() => expect(vi.mocked(api.updateStoryline)).toHaveBeenCalled());
  });

  it("loads an existing storyline in edit mode", async () => {
    render(<StorylineCreatorView editId="embergate" />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /edit storyline/i })).toBeInTheDocument(),
    );
    expect(screen.getByLabelText(/^title$/i)).toHaveValue("Embergate");
  });
});
