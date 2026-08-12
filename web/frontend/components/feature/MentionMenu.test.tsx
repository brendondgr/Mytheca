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
