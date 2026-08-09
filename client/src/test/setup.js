import "@testing-library/jest-dom";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Unmount anything a test rendered so the DOM doesn't leak between tests.
afterEach(() => {
  cleanup();
});
