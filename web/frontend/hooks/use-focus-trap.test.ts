import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { useFocusTrap, FOCUSABLE } from "./use-focus-trap";

/** A container with three focusable children, attached to the document. */
function container() {
  const el = document.createElement("div");
  el.tabIndex = -1;
  el.innerHTML = `
    <button type="button" id="a">a</button>
    <button type="button" id="b">b</button>
    <button type="button" id="c">c</button>
  `;
  document.body.appendChild(el);
  return el;
}

function tab(shiftKey = false) {
  document.dispatchEvent(
    new KeyboardEvent("keydown", { key: "Tab", shiftKey, bubbles: true, cancelable: true }),
  );
}

afterEach(() => {
  document.body.innerHTML = "";
  document.body.style.overflow = "";
});

describe("useFocusTrap", () => {
  it("moves focus to the first focusable child on open", () => {
    const el = container();
    renderHook(() => useFocusTrap({ open: true, containerRef: { current: el }, onClose: vi.fn() }));
    expect(document.activeElement?.id).toBe("a");
  });

  it("falls back to the container when it holds nothing focusable", () => {
    const el = document.createElement("div");
    el.tabIndex = -1;
    document.body.appendChild(el);
    renderHook(() => useFocusTrap({ open: true, containerRef: { current: el }, onClose: vi.fn() }));
    expect(document.activeElement).toBe(el);
  });

  it("cycles Tab from the last child back to the first", () => {
    const el = container();
    renderHook(() => useFocusTrap({ open: true, containerRef: { current: el }, onClose: vi.fn() }));
    (el.querySelector("#c") as HTMLElement).focus();

    act(() => tab());
    expect(document.activeElement?.id).toBe("a");
  });

  it("cycles Shift+Tab from the first child back to the last", () => {
    const el = container();
    renderHook(() => useFocusTrap({ open: true, containerRef: { current: el }, onClose: vi.fn() }));

    act(() => tab(true));
    expect(document.activeElement?.id).toBe("c");
  });

  it("leaves a Tab in the middle of the list alone", () => {
    // The trap only intervenes at the edges — otherwise it would fight the browser's own
    // (correct) tab order on every keystroke.
    const el = container();
    renderHook(() => useFocusTrap({ open: true, containerRef: { current: el }, onClose: vi.fn() }));
    (el.querySelector("#b") as HTMLElement).focus();

    act(() => tab());
    expect(document.activeElement?.id).toBe("b"); // jsdom does not move it; the trap did not either
  });

  it("calls onClose on Escape", () => {
    const el = container();
    const onClose = vi.fn();
    renderHook(() => useFocusTrap({ open: true, containerRef: { current: el }, onClose }));

    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("locks the body scroll and restores the PREVIOUS value", () => {
    document.body.style.overflow = "clip";
    const el = container();
    const { rerender } = renderHook(
      ({ open }) => useFocusTrap({ open, containerRef: { current: el }, onClose: vi.fn() }),
      { initialProps: { open: true } },
    );
    expect(document.body.style.overflow).toBe("hidden");

    rerender({ open: false });
    expect(document.body.style.overflow).toBe("clip");
  });

  it("restores focus to whatever was focused before", () => {
    const outside = document.createElement("button");
    document.body.appendChild(outside);
    outside.focus();
    const el = container();

    const { rerender } = renderHook(
      ({ open }) => useFocusTrap({ open, containerRef: { current: el }, onClose: vi.fn() }),
      { initialProps: { open: true } },
    );
    expect(document.activeElement?.id).toBe("a");

    rerender({ open: false });
    expect(document.activeElement).toBe(outside);
  });

  it("does nothing at all while closed", () => {
    const outside = document.createElement("button");
    document.body.appendChild(outside);
    outside.focus();
    const el = container();

    renderHook(() => useFocusTrap({ open: false, containerRef: { current: el }, onClose: vi.fn() }));

    expect(document.activeElement).toBe(outside);
    expect(document.body.style.overflow).toBe("");
  });

  it("does not re-run and steal focus when onClose changes identity", () => {
    // The load-bearing indirection: without the ref, the effect re-runs every render and
    // `focus()` yanks the caret out of whatever controlled input is being typed in.
    const el = container();
    const { rerender } = renderHook(
      ({ onClose }) => useFocusTrap({ open: true, containerRef: { current: el }, onClose }),
      { initialProps: { onClose: vi.fn() } },
    );
    (el.querySelector("#c") as HTMLElement).focus();

    rerender({ onClose: vi.fn() }); // a fresh inline closure, as a real caller would pass
    expect(document.activeElement?.id).toBe("c");
  });

  it("routes Escape to the latest onClose, not the one it opened with", () => {
    const el = container();
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(
      ({ onClose }) => useFocusTrap({ open: true, containerRef: { current: el }, onClose }),
      { initialProps: { onClose: first } },
    );

    rerender({ onClose: second });
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });

    expect(second).toHaveBeenCalled();
    expect(first).not.toHaveBeenCalled();
  });

  it("exports one FOCUSABLE selector so Modal and Drawer cannot disagree", () => {
    for (const token of ["a[href]", "button:not([disabled])", '[tabindex]:not([tabindex="-1"])']) {
      expect(FOCUSABLE).toContain(token);
    }
  });
});
