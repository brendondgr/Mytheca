import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { CharacterColumn } from "./CharacterColumn";
import { SEED_CHARACTERS } from "@/lib/seed-data";

// The real seed cast rather than a hand-rolled literal, so this file cannot
// drift out of sync with the `Character` shape.
const CAST = SEED_CHARACTERS.slice(0, 1);

function renderColumn(props: Partial<React.ComponentProps<typeof CharacterColumn>> = {}) {
  return render(
    <CharacterColumn
      characters={CAST}
      castIds={[]}
      query=""
      onPreview={() => {}}
      onEdit={() => {}}
      {...props}
    />,
  );
}

describe("CharacterColumn", () => {
  it("shows placeholder tiles in the real grid while the cast loads", () => {
    const { container } = renderColumn({ characters: [], loading: true });

    // The placeholder must trace the layout it stands in for — same 2-up/3-up
    // grid, same gap — or the swap reflows the column and the user learns the
    // placeholder was a lie.
    const grid = container.querySelector(".grid");
    expect(grid).toHaveClass("grid-cols-2", "sm:grid-cols-3", "gap-[12px]");
    expect(container.querySelectorAll(".skeleton").length).toBeGreaterThan(0);
    expect(container.querySelector("[aria-busy='true']")).toBeInTheDocument();
  });

  it("hides the placeholder bars from assistive tech", () => {
    const { container } = renderColumn({ characters: [], loading: true });
    for (const bar of container.querySelectorAll(".skeleton")) {
      expect(bar.closest("[aria-hidden='true']")).not.toBeNull();
    }
  });

  it("makes an empty column an invitation with its action inline", async () => {
    const onAdd = vi.fn();
    const user = userEvent.setup();
    renderColumn({ characters: [], onAdd });

    // Not a blank panel and not a bare "No characters yet." — it says what a
    // character IS and offers the create action where a first-time author
    // will actually look for it.
    expect(screen.getByText(/No characters yet/)).toBeInTheDocument();
    expect(screen.getByText(/a voice, a manner, and a stake/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Forge Character" }));
    expect(onAdd).toHaveBeenCalledOnce();
  });

  it("offers to clear the search when a filter emptied the column", async () => {
    const onClearQuery = vi.fn();
    const user = userEvent.setup();
    renderColumn({ characters: [], query: "zzz", onClearQuery, onAdd: () => {} });

    // A filtered-empty column is a different problem from an empty one: the
    // content exists, the query is wrong. Offering "Forge Character" here
    // would answer a question nobody asked.
    expect(screen.getByText(/No characters match/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Forge Character" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Clear search" }));
    expect(onClearQuery).toHaveBeenCalledOnce();
  });

  it("renders the real cast once loaded", () => {
    renderColumn();
    expect(screen.getByText(CAST[0].name)).toBeInTheDocument();
  });
});
