import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import App from "./App.jsx";
import { EMPTY_AGENT_SETTINGS, buildOverrides, describeOverrides } from "./ResearchLab.jsx";

const CONFIG = {
  defaults: { model: "qwen3.8-27b", max_tokens: 160, trim_reply: true },
  models: ["qwen3.8-27b", "glm-5.3"],
  models_error: null,
  prompt_template: "You are an agent. Task: {task}",
  placeholders: { task: "The task." },
};

describe("buildOverrides", () => {
  it("sends nothing while every setting is at its production default", () => {
    expect(buildOverrides(EMPTY_AGENT_SETTINGS, CONFIG)).toBeNull();
    expect(
      buildOverrides(
        { ...EMPTY_AGENT_SETTINGS, model: "qwen3.8-27b", promptTemplate: CONFIG.prompt_template },
        CONFIG,
      ),
    ).toBeNull();
    expect(buildOverrides({ ...EMPTY_AGENT_SETTINGS, model: "glm-5.3" }, null)).toBeNull();
  });

  it("sends only the settings that differ", () => {
    const overrides = buildOverrides(
      {
        model: "glm-5.3",
        promptTemplate: "Be brief. {task}",
        temperature: 0.4,
        maxTokens: 300,
        trimReply: false,
      },
      CONFIG,
    );
    expect(overrides).toEqual({
      model: "glm-5.3",
      prompt_template: "Be brief. {task}",
      temperature: 0.4,
      max_tokens: 300,
      trim_reply: false,
    });
    expect(describeOverrides(overrides)).toBe(
      "glm-5.3, edited prompt, temperature 0.4, 300 max tokens, no trim",
    );
  });
});

describe("Agent tab", () => {
  let fetchMock;

  beforeEach(() => {
    window.localStorage.clear();
    window.localStorage.setItem("vex-agent:view", "research");
    window.HTMLElement.prototype.scrollIntoView = () => {};
    vi.stubGlobal(
      "EventSource",
      class {
        addEventListener() {}
        close() {}
      },
    );
    fetchMock = vi.fn((url, options = {}) => {
      const json = (body, status = 200) =>
        Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) });
      if (url.endsWith("/research/config")) {
        return options.headers?.["X-Research-Key"] === "right-key"
          ? json(CONFIG)
          : json({ detail: "Research key is missing or wrong." }, 403);
      }
      if (url.endsWith("/messages")) {
        return json({ message_id: "m1", session_id: "session-1" });
      }
      if (url.endsWith("/responses")) {
        return json({
          response_id: "r1",
          session_id: "session-1",
          response_text: "Try a longer drive.",
          llm_model: "glm-5.3",
          llm_prompt: "You are an agent. Task: Rescue the rover",
        });
      }
      return json({ session_id: "session-1" });
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("unlocks with the research key and sends the chosen model as an override", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Student ID"), "mars-042");
    await user.click(screen.getByRole("button", { name: "Start chat" }));

    await user.click(await screen.findByRole("tab", { name: "Agent" }));
    await user.type(screen.getByLabelText("Research key"), "wrong-key");
    await user.click(screen.getByRole("button", { name: "Unlock" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Research key is missing or wrong.");

    await user.clear(screen.getByLabelText("Research key"));
    await user.type(screen.getByLabelText("Research key"), "right-key");
    await user.click(screen.getByRole("button", { name: "Unlock" }));
    await user.selectOptions(await screen.findByLabelText("Model"), "glm-5.3");
    expect(screen.getByRole("status")).toHaveTextContent("Custom settings are on");

    await user.click(screen.getByRole("tab", { name: "Chat" }));
    expect(screen.getByText(/Custom agent: glm-5\.3/)).toBeInTheDocument();
    await user.type(screen.getByLabelText("Message"), "why does it stop?");
    await user.click(screen.getByRole("button", { name: /Send/ }));

    const [, options] = fetchMock.mock.calls.find(([url]) => url.endsWith("/responses"));
    expect(options.headers["X-Research-Key"]).toBe("right-key");
    expect(JSON.parse(options.body).overrides).toEqual({ model: "glm-5.3" });

    const conversation = screen.getByRole("region", { name: "Conversation" });
    expect(await within(conversation).findByText("Try a longer drive.")).toBeInTheDocument();
    expect(within(conversation).getByText("Prompt sent to the model")).toBeInTheDocument();
    expect(window.localStorage.getItem("vex-agent:research-key")).toBe(JSON.stringify("right-key"));
  });

  it("sends no overrides or key from the student view", async () => {
    window.localStorage.setItem("vex-agent:view", "student");
    window.localStorage.setItem("vex-agent:research-key", JSON.stringify("right-key"));
    window.localStorage.setItem("vex-agent:agent-settings", JSON.stringify({ model: "glm-5.3" }));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Student ID"), "mars-042");
    await user.click(screen.getByRole("button", { name: "Start chat" }));
    await user.type(await screen.findByLabelText("Message"), "hi");
    await user.click(screen.getByRole("button", { name: /Send/ }));

    expect(screen.queryByRole("tab", { name: "Agent" })).not.toBeInTheDocument();
    const [, options] = fetchMock.mock.calls.find(([url]) => url.endsWith("/responses"));
    expect(options.headers["X-Research-Key"]).toBeUndefined();
    expect(JSON.parse(options.body).overrides).toBeUndefined();
  });
});
