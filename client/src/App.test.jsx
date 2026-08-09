import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { clamp, renderMessageBody } from "./App.jsx";

describe("clamp", () => {
  it("bounds a value to [min, max]", () => {
    expect(clamp(5, 0, 10)).toBe(5);
    expect(clamp(-3, 0, 10)).toBe(0);
    expect(clamp(42, 0, 10)).toBe(10);
  });
});

describe("renderMessageBody", () => {
  it("renders bold and inline code", () => {
    render(<div>{renderMessageBody("Use **stop** and `drive`")}</div>);
    expect(screen.getByText("stop").tagName).toBe("STRONG");
    expect(screen.getByText("drive").tagName).toBe("CODE");
  });

  it("renders a bulleted list as <li> items", () => {
    render(<div>{renderMessageBody("- first\n- second")}</div>);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("first");
    expect(items[1]).toHaveTextContent("second");
  });

  it("renders a numbered list as an <ol>", () => {
    render(<div>{renderMessageBody("1. one\n2. two")}</div>);
    const list = screen.getByRole("list");
    expect(list.tagName).toBe("OL");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });
});
