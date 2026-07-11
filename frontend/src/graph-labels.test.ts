import { describe, expect, it } from "vitest";

import { compactGraphLabel, nextSelectedNode } from "./graph-labels";

describe("compactGraphLabel", () => {
  it("reserves the final code point for an ellipsis", () => {
    expect(compactGraphLabel("Example Manager", 12)).toBe("Example Man…");
  });

  it("keeps short Chinese labels unchanged", () => {
    expect(compactGraphLabel("短中文", 12)).toBe("短中文");
  });

  it("counts Unicode code points instead of UTF-16 code units", () => {
    expect(compactGraphLabel("A😀BC", 3)).toBe("A😀…");
  });

  it("handles exact and minimum display limits", () => {
    expect(compactGraphLabel("Exact", 5)).toBe("Exact");
    expect(compactGraphLabel("Long", 1)).toBe("…");
  });
});

describe("nextSelectedNode", () => {
  it("selects an unselected node", () => {
    expect(nextSelectedNode(null, "x")).toBe("x");
  });

  it("clears the current node when it is selected again", () => {
    expect(nextSelectedNode("x", "x")).toBeNull();
  });

  it("moves selection to a different node", () => {
    expect(nextSelectedNode("x", "y")).toBe("y");
  });
});
