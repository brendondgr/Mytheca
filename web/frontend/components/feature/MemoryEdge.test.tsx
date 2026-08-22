import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryEdge } from "./MemoryEdge";

describe("MemoryEdge", () => {
  it("renders nothing while everything still fits", () => {
    // The line must not appear on a short scene — a marker that is always there stops
    // meaning anything.
    const { container } = render(<MemoryEdge droppedBeats={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("says the cast no longer reads what is above it", () => {
    // Forgetting used to happen invisibly, so every consequence of it read as the model
    // being stupid. This is the signal that it is happening at all.
    render(<MemoryEdge droppedBeats={12} />);
    expect(screen.getByText(/no longer reads the 12 beats above/i)).toBeInTheDocument();
  });

  it("says the beats are kept when compaction is on", () => {
    render(<MemoryEdge droppedBeats={12} summarised />);
    expect(screen.getByText(/remembered as a summary/i)).toBeInTheDocument();
  });

  it("gets the singular right", () => {
    render(<MemoryEdge droppedBeats={1} />);
    expect(screen.getByText(/the 1 beat above/i)).toBeInTheDocument();
  });

  it("is a separator, not a beat", () => {
    // It is not part of the story, and must not be read as one.
    render(<MemoryEdge droppedBeats={3} />);
    expect(screen.getByRole("separator")).toBeInTheDocument();
  });
});
