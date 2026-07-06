import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { Composer } from "./Composer";

describe("Composer", () => {
  it("renders a textarea with aria-label 'Your message'", () => {
    render(<Composer value="" onChange={() => {}} onSend={() => {}} />);
    expect(screen.getByRole("textbox", { name: /your message/i })).toBeInTheDocument();
  });

  it("does not render a Config button (Config lives in the SceneHeader)", () => {
    render(<Composer value="" onChange={() => {}} onSend={() => {}} />);
    expect(screen.queryByRole("button", { name: /scene configuration/i })).not.toBeInTheDocument();
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
