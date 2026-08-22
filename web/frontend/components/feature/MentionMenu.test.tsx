import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MentionMenu } from "./MentionMenu";

const OPTS = [
  { id: "cd_m", name: "maerin.md", charCount: 812 },
  { id: "cd_h", name: "harbor.md", charCount: 40 },
];

function renderMenu(over: Partial<Parameters<typeof MentionMenu>[0]> = {}) {
  const onSelect = vi.fn();
  render(
    <MentionMenu
      id="mm"
      options={OPTS}
      activeIndex={0}
      optionId={(i) => `mm-opt-${i}`}
      onSelect={onSelect}
      {...over}
    />,
  );
  return onSelect;
}

describe("MentionMenu", () => {
  it("renders a listbox of the matching files", () => {
    renderMenu();
    expect(screen.getByRole("listbox", { name: /context files/i })).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(2);
    expect(screen.getByRole("option", { name: /maerin\.md/ })).toBeInTheDocument();
  });

  it("marks only the active row as selected", () => {
    renderMenu({ activeIndex: 1 });
    const [first, second] = screen.getAllByRole("option");
    expect(first).toHaveAttribute("aria-selected", "false");
    expect(second).toHaveAttribute("aria-selected", "true");
  });

  it("gives each row the id the textarea's aria-activedescendant points at", () => {
    renderMenu();
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("id", "mm-opt-0");
  });

  it("shows each file's size", () => {
    renderMenu();
    expect(screen.getByText("812 ch")).toBeInTheDocument();
  });

  it("reports the clicked option", () => {
    const onSelect = renderMenu();
    fireEvent.click(screen.getByRole("option", { name: /harbor\.md/ }));
    expect(onSelect).toHaveBeenCalledWith(OPTS[1]);
  });

  it("renders nothing when there are no matches", () => {
    const { container } = render(
      <MentionMenu
        id="mm"
        options={[]}
        activeIndex={0}
        optionId={(i) => `mm-opt-${i}`}
        onSelect={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

describe("MentionMenu cast + docs", () => {
  const MIXED = [
    { id: "ch_mei", name: "Mei", kind: "cast" as const, mono: "M", color: "#8E2B1C" },
    { id: "cd_m", name: "maerin.md", kind: "doc" as const, charCount: 120 },
  ];

  it("splits the rows into two labelled groups", () => {
    render(
      <MentionMenu
        id="m"
        options={MIXED}
        activeIndex={0}
        optionId={(i) => `m-${i}`}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByRole("group", { name: "Cast" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Context files" })).toBeInTheDocument();
  });

  it("says which kind each row is, so identical names are still distinguishable", () => {
    render(
      <MentionMenu
        id="m"
        options={MIXED}
        activeIndex={0}
        optionId={(i) => `m-${i}`}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByRole("option", { name: "Mei, character" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "maerin.md, context file" })).toBeInTheDocument();
  });

  it("keeps a FLAT index across both groups, so the roving highlight is unchanged", () => {
    // The composer's Arrow/Enter/Tab handling addresses one list; grouping must not
    // renumber the rows or the highlight and `aria-activedescendant` would disagree.
    render(
      <MentionMenu
        id="m"
        options={MIXED}
        activeIndex={1}
        optionId={(i) => `m-${i}`}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByRole("option", { name: "maerin.md, context file" })).toHaveAttribute(
      "id",
      "m-1",
    );
    expect(screen.getByRole("option", { name: "maerin.md, context file" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("option", { name: "Mei, character" })).toHaveAttribute(
      "aria-selected",
      "false",
    );
  });

  it("omits a group that has no rows", () => {
    render(
      <MentionMenu
        id="m"
        options={[MIXED[0]]}
        activeIndex={0}
        optionId={(i) => `m-${i}`}
        onSelect={() => {}}
      />,
    );
    expect(screen.queryByRole("group", { name: "Context files" })).not.toBeInTheDocument();
  });
});

