import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("renders the turn-limit and suggestion dropdowns to the left of the input", () => {
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        maxTurns={5}
        onMaxTurnsChange={() => {}}
        suggestionsCount={4}
        onSuggestionsCountChange={() => {}}
      />,
    );
    const maxTurns = screen.getByRole("combobox", { name: /max turns/i });
    const suggestions = screen.getByRole("combobox", { name: /suggestions/i });
    const input = screen.getByRole("textbox", { name: /your message/i });
    expect(maxTurns).toBeInTheDocument();
    expect(suggestions).toBeInTheDocument();
    // The controls precede the input in DOM order (they sit to its left).
    expect(maxTurns.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(suggestions.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("fires the change handlers when a dropdown value changes", async () => {
    const onMaxTurnsChange = vi.fn();
    const onSuggestionsCountChange = vi.fn();
    const user = userEvent.setup();
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        maxTurns={5}
        onMaxTurnsChange={onMaxTurnsChange}
        suggestionsCount={4}
        onSuggestionsCountChange={onSuggestionsCountChange}
      />,
    );
    await user.selectOptions(screen.getByRole("combobox", { name: /max turns/i }), "3");
    await user.selectOptions(screen.getByRole("combobox", { name: /suggestions/i }), "0");
    expect(onMaxTurnsChange).toHaveBeenCalledWith(3);
    expect(onSuggestionsCountChange).toHaveBeenCalledWith(0);
  });

  it("still sends the typed message", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Composer value="hello" onChange={() => {}} onSend={onSend} />);
    await user.click(screen.getByRole("button", { name: /send/i }));
    expect(onSend).toHaveBeenCalled();
  });
});
