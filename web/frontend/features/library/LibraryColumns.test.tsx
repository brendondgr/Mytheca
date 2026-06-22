import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { LibraryView } from "./LibraryView";

describe("LibraryView — storyline switcher", () => {
  it("opens the storyline menu with the active storyline and a create action", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await user.click(screen.getByRole("button", { name: "Embergate" }));

    const menu = screen.getByLabelText("Switch storyline");
    expect(within(menu).getByText("Embergate")).toBeInTheDocument();
    expect(
      within(menu).getByRole("button", { name: /new storyline/i }),
    ).toBeInTheDocument();
  });

  it("creates a new storyline and shows empty columns", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);
    await user.click(screen.getByRole("button", { name: "Embergate" }));
    await user.click(screen.getByRole("button", { name: /new storyline/i }));

    // Switcher now reads the new (empty) storyline; columns show empty notes.
    expect(screen.getByText("No characters yet.")).toBeInTheDocument();
    expect(screen.getByText("No settings yet.")).toBeInTheDocument();
    expect(screen.getByText("No scenarios yet.")).toBeInTheDocument();
  });
});

describe("LibraryView — cross-column highlight", () => {
  it("lights up the featured scenario's cast and active setting", async () => {
    const user = userEvent.setup();
    render(<LibraryView />);

    // Default feature = The Embergate Conspiracy: 4 cast + 1 setting = 5 cues.
    expect(screen.getAllByText(/in this scene/i)).toHaveLength(5);

    // Feature a different scenario (Salt & Secrets): 3 cast + 1 setting = 4.
    await user.click(
      screen.getByRole("button", { name: /feature scenario salt & secrets/i }),
    );
    expect(screen.getAllByText(/in this scene/i)).toHaveLength(4);
  });
});
