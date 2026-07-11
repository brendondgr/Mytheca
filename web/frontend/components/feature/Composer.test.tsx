import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("renders a textarea with aria-label 'Your message'", () => {
    render(<Composer value="" onChange={() => {}} onSend={() => {}} />);
    expect(screen.getByRole("textbox", { name: /your message/i })).toBeInTheDocument();
  });

  it("omits the Config control when no config handlers are given", () => {
    render(<Composer value="" onChange={() => {}} onSend={() => {}} />);
    expect(screen.queryByRole("button", { name: /scene configuration/i })).not.toBeInTheDocument();
  });

  it("renders the Config control on the bottom row when config handlers are provided", () => {
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        maxTurns={5}
        onMaxTurnsChange={() => {}}
        suggestionsCount={4}
        onSuggestionsCountChange={() => {}}
        contextBeats={14}
        onContextBeatsChange={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: /scene configuration/i })).toBeInTheDocument();
  });

  it("renders the context dial as a labelled button when the model window size is known", () => {
    render(
      <Composer
        value=""
        onChange={() => {}}
        onSend={() => {}}
        usedTokens={5000}
        maxContextTokens={16384}
        usedTokensExact
      />,
    );
    const dial = screen.getByRole("button", { name: /context usage/i });
    expect(dial.getAttribute("aria-label")).toContain("exact");
  });

  it("omits the context dial when the window size is unknown", () => {
    render(<Composer value="" onChange={() => {}} onSend={() => {}} maxContextTokens={null} />);
    expect(screen.queryByRole("button", { name: /context usage/i })).not.toBeInTheDocument();
  });

  it("typing fires onChange", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<Composer value="" onChange={onChange} onSend={() => {}} />);
    const ta = screen.getByRole("textbox", { name: /your message/i });
    await user.type(ta, "hello");
    expect(onChange).toHaveBeenCalled();
  });

  it("Enter key fires onSend when value is non-empty", () => {
    const onSend = vi.fn();
    render(<Composer value="hello" onChange={() => {}} onSend={onSend} />);
    const ta = screen.getByRole("textbox", { name: /your message/i });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: false });
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("Enter key does NOT fire onSend when value is empty", () => {
    const onSend = vi.fn();
    render(<Composer value="" onChange={() => {}} onSend={onSend} />);
    const ta = screen.getByRole("textbox", { name: /your message/i });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: false });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("Shift+Enter does NOT fire onSend", () => {
    const onSend = vi.fn();
    render(<Composer value="hello" onChange={() => {}} onSend={onSend} />);
    const ta = screen.getByRole("textbox", { name: /your message/i });
    fireEvent.keyDown(ta, { key: "Enter", shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("Send button has aria-label 'Send' and fires onSend on click", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<Composer value="hello" onChange={() => {}} onSend={onSend} />);
    const btn = screen.getByRole("button", { name: /^send$/i });
    expect(btn).toBeInTheDocument();
    await user.click(btn);
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  describe("Player POV", () => {
    const POV_OPTS = [{ id: "mei", name: "Mei", mono: "M", color: "#8E2B1C", portrait: null }];

    it("renders the 'Speaking as' dropdown to the right of Config when a POV handler is given", () => {
      render(
        <Composer
          value=""
          onChange={() => {}}
          onSend={() => {}}
          onMaxTurnsChange={() => {}}
          onPovChange={() => {}}
          povOptions={POV_OPTS}
          pov={null}
        />,
      );
      const config = screen.getByRole("button", { name: /scene configuration/i });
      const pov = screen.getByRole("button", { name: /speaking as/i });
      expect(pov).toBeInTheDocument();
      // POV sits AFTER the Config button in document order (to its right).
      expect(config.compareDocumentPosition(pov) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it("omits the POV dropdown when no POV handler is given", () => {
      render(<Composer value="" onChange={() => {}} onSend={() => {}} />);
      expect(screen.queryByRole("button", { name: /speaking as/i })).not.toBeInTheDocument();
    });

    it("placeholder reflects the active POV character", () => {
      render(
        <Composer
          value=""
          onChange={() => {}}
          onSend={() => {}}
          onPovChange={() => {}}
          povOptions={POV_OPTS}
          pov="mei"
        />,
      );
      expect(screen.getByRole("textbox", { name: /your message/i })).toHaveAttribute(
        "placeholder",
        "Speaking as Mei…",
      );
    });

    it("keeps the default placeholder when POV is Narrator (null)", () => {
      render(
        <Composer
          value=""
          onChange={() => {}}
          onSend={() => {}}
          onPovChange={() => {}}
          povOptions={POV_OPTS}
          pov={null}
        />,
      );
      expect(screen.getByRole("textbox", { name: /your message/i })).toHaveAttribute(
        "placeholder",
        "Speak, or describe what you do…",
      );
    });
  });

  describe("while sendDisabled", () => {
    it("the textarea is NOT disabled — typing still fires onChange", async () => {
      const onChange = vi.fn();
      const user = userEvent.setup();
      render(<Composer value="" onChange={onChange} onSend={() => {}} sendDisabled />);
      const ta = screen.getByRole("textbox", { name: /your message/i });
      // textarea must NOT be disabled
      expect(ta).not.toBeDisabled();
      await user.type(ta, "a");
      expect(onChange).toHaveBeenCalled();
    });

    it("Enter does NOT call onSend", () => {
      const onSend = vi.fn();
      render(<Composer value="hello" onChange={() => {}} onSend={onSend} sendDisabled />);
      const ta = screen.getByRole("textbox", { name: /your message/i });
      fireEvent.keyDown(ta, { key: "Enter", shiftKey: false });
      expect(onSend).not.toHaveBeenCalled();
    });

    it("Send button has the disabled attribute", () => {
      render(<Composer value="hello" onChange={() => {}} onSend={() => {}} sendDisabled />);
      const btn = screen.getByRole("button", { name: /^send$/i });
      expect(btn).toBeDisabled();
    });

    it("shows the streaming placeholder", () => {
      render(<Composer value="" onChange={() => {}} onSend={() => {}} sendDisabled />);
      const ta = screen.getByRole("textbox", { name: /your message/i });
      expect(ta).toHaveAttribute("placeholder", "The scene responds…");
    });
  });
});
