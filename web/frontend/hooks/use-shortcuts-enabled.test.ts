import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { useShortcutsEnabled } from "./use-shortcuts-enabled";
import { writeShortcutsEnabled, SHORTCUTS_STORAGE_KEY } from "@/lib/shortcuts";

beforeEach(() => localStorage.clear());

describe("useShortcutsEnabled (WCAG 2.1.4)", () => {
  it("is on by default — the criterion asks for an escape, not an opt-in", () => {
    const { result } = renderHook(() => useShortcutsEnabled());
    expect(result.current).toBe(true);
  });

  it("reflects a stored preference", () => {
    localStorage.setItem(SHORTCUTS_STORAGE_KEY, "off");
    const { result } = renderHook(() => useShortcutsEnabled());
    expect(result.current).toBe(false);
  });

  it("reacts in this tab, without a reload", () => {
    // `storage` fires only in OTHER tabs, so a scene already on screen would otherwise keep
    // its old binding until the page was reloaded.
    const { result } = renderHook(() => useShortcutsEnabled());
    act(() => writeShortcutsEnabled(false));
    expect(result.current).toBe(false);
    act(() => writeShortcutsEnabled(true));
    expect(result.current).toBe(true);
  });

  it("reacts to another tab changing it", () => {
    const { result } = renderHook(() => useShortcutsEnabled());
    localStorage.setItem(SHORTCUTS_STORAGE_KEY, "off");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: SHORTCUTS_STORAGE_KEY }));
    });
    expect(result.current).toBe(false);
  });
});
