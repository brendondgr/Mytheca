import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSceneShortcuts, type SceneShortcuts } from "./use-scene-shortcuts";

function actions(over: Partial<SceneShortcuts> = {}): SceneShortcuts {
  return {
    focusComposer: vi.fn(),
    recallLast: vi.fn(),
    closeTopmost: vi.fn(() => false),
    toggleHelp: vi.fn(),
    ...over,
  };
}

function press(key: string, target: EventTarget = document.body, init: KeyboardEventInit = {}) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(event);
  return event;
}

function textarea(value = "") {
  const el = document.createElement("textarea");
  el.value = value;
  document.body.appendChild(el);
  return el;
}

describe("useSceneShortcuts", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("focuses the composer on /", () => {
    const a = actions();
    renderHook(() => useSceneShortcuts(a));
    press("/");
    expect(a.focusComposer).toHaveBeenCalledTimes(1);
  });

  it("opens the sheet on ?", () => {
    const a = actions();
    renderHook(() => useSceneShortcuts(a));
    press("?");
    expect(a.toggleHelp).toHaveBeenCalledTimes(1);
  });

  it("closes the topmost thing on Escape", () => {
    const a = actions({ closeTopmost: vi.fn(() => true) });
    renderHook(() => useSceneShortcuts(a));
    const event = press("Escape");
    expect(a.closeTopmost).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("leaves Escape alone when nothing was open", () => {
    // Swallowing a key nobody wanted is how a page stops feeling like a page.
    const a = actions({ closeTopmost: vi.fn(() => false) });
    renderHook(() => useSceneShortcuts(a));
    expect(press("Escape").defaultPrevented).toBe(false);
  });

  // ---- the bug this class of feature always ships with ----------------------

  it("does NOT steal / from a text field", () => {
    // Typing "/" into the composer must type "/". A shortcut that eats characters out of a
    // text field is worse than no shortcut, and it is the first thing a player will hit.
    const a = actions();
    renderHook(() => useSceneShortcuts(a));
    const event = press("/", textarea("half a sentence"));
    expect(a.focusComposer).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("does NOT steal ? from a text field", () => {
    const a = actions();
    renderHook(() => useSceneShortcuts(a));
    const event = press("?", textarea("is this a question"));
    expect(a.toggleHelp).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  it("does not steal from an input or a contenteditable either", () => {
    const a = actions();
    renderHook(() => useSceneShortcuts(a));
    const input = document.createElement("input");
    document.body.appendChild(input);
    press("/", input);

    const div = document.createElement("div");
    Object.defineProperty(div, "isContentEditable", { value: true });
    document.body.appendChild(div);
    press("/", div);

    expect(a.focusComposer).not.toHaveBeenCalled();
  });

  // ---- recall ---------------------------------------------------------------

  it("recalls the last message from an EMPTY composer", () => {
    const a = actions();
    renderHook(() => useSceneShortcuts(a));
    const event = press("ArrowUp", textarea(""));
    expect(a.recallLast).toHaveBeenCalledTimes(1);
    expect(event.defaultPrevented).toBe(true);
  });

  it("never recalls over something half-written", () => {
    // Recall that overwrites a draft is a data-loss bug wearing a convenience hat.
    const a = actions();
    renderHook(() => useSceneShortcuts(a));
    press("ArrowUp", textarea("a line I was in the middle of"));
    expect(a.recallLast).not.toHaveBeenCalled();
  });

  it("leaves ArrowUp alone outside a text field", () => {
    // It is the page's scroll key everywhere else.
    const a = actions();
    renderHook(() => useSceneShortcuts(a));
    const event = press("ArrowUp");
    expect(a.recallLast).not.toHaveBeenCalled();
    expect(event.defaultPrevented).toBe(false);
  });

  // ---- good citizenship -----------------------------------------------------

  it("never shadows a browser shortcut", () => {
    const a = actions();
    renderHook(() => useSceneShortcuts(a));
    press("/", document.body, { metaKey: true });
    press("/", document.body, { ctrlKey: true });
    press("?", document.body, { altKey: true });
    expect(a.focusComposer).not.toHaveBeenCalled();
    expect(a.toggleHelp).not.toHaveBeenCalled();
  });

  it("does nothing at all when disabled", () => {
    const a = actions();
    renderHook(() => useSceneShortcuts(a, false));
    press("/");
    press("?");
    expect(a.focusComposer).not.toHaveBeenCalled();
    expect(a.toggleHelp).not.toHaveBeenCalled();
  });

  it("stops listening once unmounted", () => {
    const a = actions();
    const { unmount } = renderHook(() => useSceneShortcuts(a));
    unmount();
    press("/");
    expect(a.focusComposer).not.toHaveBeenCalled();
  });
});
