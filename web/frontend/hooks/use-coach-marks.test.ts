import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useCoachMarks } from "./use-coach-marks";
import { COACH_MARK_STORAGE_KEY, type CoachMarkId } from "@/lib/coachMarks";

const ALL: CoachMarkId[] = ["composer", "pov", "cast-rail"];

describe("useCoachMarks", () => {
  beforeEach(() => localStorage.clear());

  it("offers one at a time, in order — never a queue on screen", () => {
    const { result } = renderHook(() => useCoachMarks(ALL));
    expect(result.current.mark).toBe("composer");
  });

  it("moves to the next once one is dismissed", () => {
    const { result } = renderHook(() => useCoachMarks(ALL));
    act(() => result.current.dismiss("composer"));
    expect(result.current.mark).toBe("pov");
    act(() => result.current.dismiss("pov"));
    expect(result.current.mark).toBe("cast-rail");
    act(() => result.current.dismiss("cast-rail"));
    expect(result.current.mark).toBeNull();
  });

  it("persists dismissal across a remount", () => {
    const first = renderHook(() => useCoachMarks(ALL));
    act(() => first.result.current.dismiss("composer"));
    first.unmount();

    const second = renderHook(() => useCoachMarks(ALL));
    expect(second.result.current.mark).toBe("pov");
  });

  it("stores ids, not a 'seen the tour' flag", () => {
    // The whole reason: a fourth mark can ship later without re-showing these three to
    // everyone who already dealt with them.
    const { result } = renderHook(() => useCoachMarks(ALL));
    act(() => result.current.dismiss("pov"));
    expect(JSON.parse(localStorage.getItem(COACH_MARK_STORAGE_KEY) ?? "[]")).toEqual(["pov"]);
    // And an unrelated mark is still offered.
    expect(result.current.mark).toBe("composer");
  });

  it("never offers a hint pointing at something that is not on screen", () => {
    // Below `lg` the cast rail does not exist; a hint pointing at nothing is worse than none.
    const { result } = renderHook(() => useCoachMarks(["composer", "pov"]));
    act(() => result.current.dismiss("composer"));
    act(() => result.current.dismiss("pov"));
    expect(result.current.mark).toBeNull();
  });

  it("dismissing twice is harmless", () => {
    const { result } = renderHook(() => useCoachMarks(ALL));
    act(() => result.current.dismiss("composer"));
    act(() => result.current.dismiss("composer"));
    expect(JSON.parse(localStorage.getItem(COACH_MARK_STORAGE_KEY) ?? "[]")).toEqual(["composer"]);
  });

  it("survives a mangled stored value rather than crashing the scene", () => {
    // A hint that cannot remember being dismissed is a small annoyance; a crash on load
    // is not.
    localStorage.setItem(COACH_MARK_STORAGE_KEY, "{not json");
    const { result } = renderHook(() => useCoachMarks(ALL));
    expect(result.current.mark).toBe("composer");
  });

  it("ignores unknown ids in storage", () => {
    localStorage.setItem(COACH_MARK_STORAGE_KEY, JSON.stringify(["composer", "nonsense"]));
    const { result } = renderHook(() => useCoachMarks(ALL));
    expect(result.current.mark).toBe("pov");
  });
});
