import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { PromptOverridesModal } from "./PromptOverridesModal";

vi.mock("@/lib/api", async () => (await import("@/test/api-mock")).makeApiMock());

describe("PromptOverridesModal", () => {
  it("fetches the catalog and renders the editor sub-tabs", async () => {
    render(
      <PromptOverridesModal
        open
        onClose={vi.fn()}
        heading="Embergate — writing prompts"
        overrides={{}}
        onSave={vi.fn()}
      />,
    );
    expect(screen.getByText("Embergate — writing prompts")).toBeInTheDocument();
    // From the mocked catalog (narrator + planner).
    expect(await screen.findByRole("tab", { name: "Narrator" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Planner" })).toBeInTheDocument();
  });

  it("saves the edited override map and closes", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onClose = vi.fn();
    render(
      <PromptOverridesModal
        open
        onClose={onClose}
        heading="Embergate — writing prompts"
        overrides={{}}
        onSave={onSave}
      />,
    );
    const field = await screen.findByRole("textbox", { name: /narrator — transition beat prompt/i });
    await user.clear(field);
    await user.type(field, "STORY NARR");
    await user.click(screen.getByRole("button", { name: /save prompts/i }));

    await waitFor(() => expect(onSave).toHaveBeenCalledWith({ "narrator.system": "STORY NARR" }));
    expect(onClose).toHaveBeenCalled();
  });
});
