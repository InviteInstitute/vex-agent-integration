import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App.jsx";

// Student view hides why a proactive message fired; research view shows it.
let streamListeners;

beforeEach(() => {
  streamListeners = {};
  window.localStorage.clear();
  window.HTMLElement.prototype.scrollIntoView = () => {};
  vi.stubGlobal(
    "EventSource",
    class {
      addEventListener(type, listener) {
        streamListeners[type] = listener;
      }
      close() {}
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ session_id: "session-1" }),
      }),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function startChatWithCheckIn(user) {
  render(<App />);
  await user.type(screen.getByLabelText("Student ID"), "mars-042");
  await user.click(screen.getByRole("button", { name: "Start Chat" }));
  await screen.findByRole("region", { name: "Conversation" });
  act(() => {
    streamListeners.assistant_message({
      data: JSON.stringify({
        message_id: 7,
        message: "What do you expect the robot to do next time?",
        trigger_type: "wheel_spinning",
        trigger_why: "3 runs with no code change",
      }),
    });
  });
}

describe("student and research views", () => {
  it("shows students a plain check-in label without the trigger", async () => {
    const user = userEvent.setup();
    await startChatWithCheckIn(user);

    expect(screen.getByText("Checking in")).toBeInTheDocument();
    expect(screen.queryByText("wheel_spinning")).not.toBeInTheDocument();
    expect(screen.queryByText("session-1")).not.toBeInTheDocument();
  });

  it("shows researchers the trigger, its reason, and the session", async () => {
    const user = userEvent.setup();
    await startChatWithCheckIn(user);

    await user.click(screen.getByRole("button", { name: "Research" }));

    expect(screen.getByText("Proactive check-in")).toBeInTheDocument();
    expect(screen.getByText("wheel_spinning")).toBeInTheDocument();
    expect(screen.getByText("3 runs with no code change")).toBeInTheDocument();
    expect(screen.getByText("session-1")).toBeInTheDocument();
    expect(window.localStorage.getItem("vex-agent:view")).toBe("research");
  });

  it("counts replies that arrive while the chat is collapsed", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Student ID"), "mars-042");
    await user.click(screen.getByRole("button", { name: "Start Chat" }));
    await screen.findByRole("region", { name: "Conversation" });

    await user.click(screen.getByRole("button", { name: "Collapse chat" }));
    act(() => {
      streamListeners.assistant_message({
        data: JSON.stringify({ message_id: 9, message: "Still there?" }),
      });
    });

    expect(screen.getByRole("button", { name: /Open Chat\s*1 new/ })).toBeInTheDocument();
  });
});
