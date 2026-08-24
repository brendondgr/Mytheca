import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  // Storage is shared across every test in a file, so a component that REMEMBERS a
  // preference silently changes the starting state of every test after it. The direction
  // verb bar is the first control to do this and it broke three unrelated tests by opening
  // itself; clearing here means no future one can.
  try {
    window.localStorage.clear();
    window.sessionStorage.clear();
  } catch {
    // A jsdom without storage is fine — there is nothing to leak.
  }
});

// Global App Router stub so components calling `useRouter()` (e.g. LibraryView,
// StorylineCreatorView) render under jsdom without an AppRouterContext. The router
// is stable per test file, so a test can assert against `useRouter().push`.
vi.mock("next/navigation", () => {
  const router = {
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  };
  return {
    useRouter: () => router,
    usePathname: () => "/",
    useSearchParams: () => new URLSearchParams(),
    redirect: vi.fn(),
    notFound: vi.fn(),
  };
});

// jsdom does not implement matchMedia; components read it for
// prefers-reduced-motion. Provide a permissive no-op (matches: false).
if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}
