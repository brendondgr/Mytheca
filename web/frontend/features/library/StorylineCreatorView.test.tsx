import { render, screen, waitFor, within } from "@testing-library/react";
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
  it("renders the New Storyline page with the Build hero and fields", () => {
    render(<StorylineCreatorView />);
    expect(screen.getByRole("heading", { name: /new storyline/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/describe the world/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^title$/i)).toBeInTheDocument();
    // Build is disabled until there's a seed or context.
    expect(screen.getByRole("button", { name: /build the whole world/i })).toBeDisabled();
  });

  it("builds a world and shows the reviewable proposal", async () => {
    const user = userEvent.setup();
    render(<StorylineCreatorView />);
    await user.type(screen.getByLabelText(/describe the world/i), "A drowned harbor town.");
    const buildBtn = screen.getByRole("button", { name: /build the whole world/i });
    expect(buildBtn).toBeEnabled();
    await user.click(buildBtn);

    expect(vi.mocked(api.buildWorldStream)).toHaveBeenCalled();
    // The proposal reflects the storyline core into the Title field…
    await waitFor(() => expect(screen.getByLabelText(/^title$/i)).toHaveValue("Built World"));
    // …and the right-column world panel lists the built cast/settings for review.
    const review = await screen.findByRole("region", { name: /proposed world/i });
    expect(within(review).getByDisplayValue("Built Hero")).toBeInTheDocument();
    expect(within(review).getByDisplayValue("Built Place")).toBeInTheDocument();
  });

  it("swaps the right column from Context files to the live world build", async () => {
    const user = userEvent.setup();
    render(<StorylineCreatorView />);
    // Before any build: the Context files column is shown.
    expect(screen.getByRole("complementary", { name: /context files/i })).toBeInTheDocument();

    await user.type(screen.getByLabelText(/describe the world/i), "A drowned harbor town.");
    await user.click(screen.getByRole("button", { name: /build the whole world/i }));

    // After building: the world panel replaces the Context files column.
    expect(await screen.findByRole("region", { name: /proposed world/i })).toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: /context files/i })).not.toBeInTheDocument();
  });

  it("triages dropped files into grouped buckets", async () => {
    const user = userEvent.setup();
    render(<StorylineCreatorView />);
    await user.upload(screen.getByLabelText(/browse files/i), md("hero.md", "A person."));
    expect(await screen.findByRole("button", { name: /remove hero\.md/i })).toBeInTheDocument();

    // One Uncategorized doc → the Triage action is scoped to it.
    await user.click(screen.getByRole("button", { name: /triage uncategorized \(1\)/i }));
    // The mock classifies the first doc as a character → the grouped "Character details".
    expect(await screen.findByText(/character details/i)).toBeInTheDocument();
  });

  it("drops files pre-categorized when an 'Add as' bucket is chosen (no triage)", async () => {
    const user = userEvent.setup();
    render(<StorylineCreatorView />);
    // Choose Character as the upload target, then add a file.
    await user.selectOptions(screen.getByRole("combobox", { name: /add as/i }), "character");
    await user.upload(screen.getByLabelText(/browse files/i), md("hero.md", "A person."));
    // It lands under Characters immediately — no Triage run.
    expect(await screen.findByText(/character details/i)).toBeInTheDocument();
    const row = screen.getByRole("combobox", { name: /category for hero\.md/i });
    expect(row).toHaveValue("character");
    expect(vi.mocked(api.triageDocumentsStream)).not.toHaveBeenCalled();
  });

  it("shows the context-budget meter", () => {
    render(<StorylineCreatorView />);
    expect(screen.getByText(/context budget/i)).toBeInTheDocument();
  });

  it("creates a storyline by hand and navigates to it", async () => {
    const { useRouter } = await import("next/navigation");
    const push = vi.mocked(useRouter().push);
    push.mockClear();
    const user = userEvent.setup();
    render(<StorylineCreatorView />);

    await user.type(screen.getByLabelText(/^title$/i), "Manual World");
    await user.click(screen.getByRole("button", { name: /create world/i }));

    expect(vi.mocked(api.createStoryline)).toHaveBeenCalledWith(
      expect.objectContaining({ title: "Manual World" }),
    );
    await waitFor(() => expect(push).toHaveBeenCalledWith(expect.stringMatching(/^\/sl-test/)));
  });

  it("loads an existing storyline in edit mode", async () => {
    render(<StorylineCreatorView editId="embergate" />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /edit storyline/i })).toBeInTheDocument(),
    );
    expect(screen.getByLabelText(/^title$/i)).toHaveValue("Embergate");
    // Build hero is create-only.
    expect(screen.queryByRole("button", { name: /build the whole world/i })).not.toBeInTheDocument();
  });
});
