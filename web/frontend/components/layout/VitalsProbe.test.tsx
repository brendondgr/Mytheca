import { render } from "@testing-library/react";
import { describe, it, expect, vi, afterEach } from "vitest";
import { VitalsProbe } from "./VitalsProbe";

const original = process.env.NEXT_PUBLIC_VITALS;
afterEach(() => {
  process.env.NEXT_PUBLIC_VITALS = original;
  delete (window as { __mythecaVitals?: unknown }).__mythecaVitals;
  vi.resetModules();
});

describe("VitalsProbe", () => {
  it("renders nothing", () => {
    const { container } = render(<VitalsProbe />);
    expect(container).toBeEmptyDOMElement();
  });

  it("subscribes to nothing and touches no globals when the flag is unset", async () => {
    // A measurement probe that ships in a normal build is a probe that changes the thing it
    // measures — and `web-vitals` is a devDependency, so a production bundle must not reach
    // for it at all.
    delete process.env.NEXT_PUBLIC_VITALS;
    render(<VitalsProbe />);
    await Promise.resolve();
    expect((window as { __mythecaVitals?: unknown }).__mythecaVitals).toBeUndefined();
  });

  it("subscribes to nothing when the flag is set to anything but 1", async () => {
    process.env.NEXT_PUBLIC_VITALS = "true";
    render(<VitalsProbe />);
    await Promise.resolve();
    expect((window as { __mythecaVitals?: unknown }).__mythecaVitals).toBeUndefined();
  });
});
