import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { InfoTip } from "./InfoTip";

const TEXT = "A director reads each moment and decides who speaks.";

describe("InfoTip", () => {
  it("keeps the description in the accessibility tree while the bubble is closed", () => {
    // The whole justification for moving this copy out of flow: nothing is taken away from a
    // screen reader, only from the layout. If this ever stops holding, the change is a
    // regression dressed as a tidy-up.
    render(
      <InfoTip id="tip" label="Turn planning">
        {TEXT}
      </InfoTip>,
    );
    render(
      <select aria-label="Turn planning" aria-describedby="tip">
        <option>On</option>
      </select>,
    );
    expect(screen.getByRole("combobox", { name: "Turn planning" })).toHaveAccessibleDescription(
      TEXT,
    );
  });

  it("shows the bubble on hover and hides it again on leave", async () => {
    const user = userEvent.setup();
    render(<InfoTip label="Turn planning">{TEXT}</InfoTip>);
    const btn = screen.getByRole("button", { name: /what turn planning does/i });
    expect(screen.queryAllByText(TEXT)).toHaveLength(1); // the sr-only copy only
    await user.hover(btn);
    expect(screen.queryAllByText(TEXT)).toHaveLength(2);
    await user.unhover(btn);
    expect(screen.queryAllByText(TEXT)).toHaveLength(1);
  });

  it("shows the bubble on keyboard focus — a pointer is not the only way in", async () => {
    const user = userEvent.setup();
    render(<InfoTip label="Turn planning">{TEXT}</InfoTip>);
    await user.tab();
    expect(screen.getByRole("button", { name: /what turn planning does/i })).toHaveFocus();
    expect(screen.queryAllByText(TEXT)).toHaveLength(2);
  });

  it("is dismissible with Escape without closing the surface around it", async () => {
    // WCAG 1.4.13. The `stopPropagation` matters as much as the close: this tip lives inside
    // popovers that close on a document-level Escape, and dismissing a tooltip must not also
    // throw away the panel the player is working in.
    const user = userEvent.setup();
    let outerEscapes = 0;
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") outerEscapes += 1;
    });
    render(<InfoTip label="Turn planning">{TEXT}</InfoTip>);
    await user.click(screen.getByRole("button", { name: /what turn planning does/i }));
    expect(screen.queryAllByText(TEXT)).toHaveLength(2);
    await user.keyboard("{Escape}");
    expect(screen.queryAllByText(TEXT)).toHaveLength(1);
    expect(outerEscapes).toBe(0);
  });

  it("opens on click, for a touch pointer that cannot hover", async () => {
    const user = userEvent.setup();
    render(<InfoTip label="Turn planning">{TEXT}</InfoTip>);
    const btn = screen.getByRole("button", { name: /what turn planning does/i });
    await user.click(btn);
    expect(screen.queryAllByText(TEXT)).toHaveLength(2);
  });
});
