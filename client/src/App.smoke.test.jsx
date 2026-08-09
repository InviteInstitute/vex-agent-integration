import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render } from "@testing-library/react";

// App opens a Server-Sent Events connection and calls fetch on mount. jsdom has
// neither EventSource nor a real network, so stub both — then a successful mount
// exercises React 19's render + effects path end to end (not just pure helpers).
beforeEach(() => {
  vi.stubGlobal(
    "EventSource",
    class {
      constructor() {}
      addEventListener() {}
      close() {}
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

import App from "./App.jsx";

describe("App (smoke)", () => {
  it("mounts under React 19 without crashing", () => {
    const { container } = render(<App />);
    // If App threw during render/mount (a React 19 incompatibility), render()
    // would have thrown; a non-empty tree means it mounted cleanly.
    expect(container.firstChild).toBeTruthy();
  });
});
