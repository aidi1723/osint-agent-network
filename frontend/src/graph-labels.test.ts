import { describe, expect, it, vi } from "vitest";

import { compactGraphLabel, nextSelectedNode } from "./graph-labels";

describe("compactGraphLabel", () => {
  it("reserves the final code point for an ellipsis", () => {
    expect(compactGraphLabel("Example Manager", 12)).toBe("Example Man…");
  });

  it("keeps short Chinese labels unchanged", () => {
    expect(compactGraphLabel("短中文", 12)).toBe("短中文");
  });

  it("counts Unicode graphemes instead of UTF-16 code units", () => {
    expect(compactGraphLabel("A😀BC", 3)).toBe("A😀…");
  });

  it("does not split combining-character graphemes", () => {
    expect(compactGraphLabel("e\u0301xy", 2)).toBe("e\u0301…");
  });

  it("does not split zero-width-joiner emoji graphemes", () => {
    expect(compactGraphLabel("👨‍👩‍👧‍👦AB", 2)).toBe("👨‍👩‍👧‍👦…");
  });

  it("handles exact and minimum display limits", () => {
    expect(compactGraphLabel("Exact", 5)).toBe("Exact");
    expect(compactGraphLabel("Long", 1)).toBe("…");
  });

  it("rejects non-finite and fractional grapheme limits", () => {
    expect(() => compactGraphLabel("Label", Number.NaN)).toThrow(RangeError);
    expect(() => compactGraphLabel("Label", Number.POSITIVE_INFINITY)).toThrow(RangeError);
    expect(() => compactGraphLabel("Label", 2.5)).toThrow(RangeError);
  });

  it("loads and uses conservative truncation when Intl.Segmenter is unavailable", async () => {
    const descriptor = Object.getOwnPropertyDescriptor(Intl, "Segmenter");
    vi.resetModules();
    Object.defineProperty(Intl, "Segmenter", { configurable: true, value: undefined });
    try {
      const fallbackModule = await import("./graph-labels");
      expect(fallbackModule.compactGraphLabel("Example Manager", 12)).toBe("Example Man…");
      expect(fallbackModule.compactGraphLabel("短中文", 12)).toBe("短中文");
      expect(fallbackModule.compactGraphLabel("\r\nA", 2)).toBe("\r\nA");
      expect(fallbackModule.compactGraphLabel("e\u0301xy", 2)).toBe("…");
      expect(fallbackModule.compactGraphLabel("✈️AB", 2)).toBe("…");
      expect(fallbackModule.compactGraphLabel("👍🏽AB", 2)).toBe("…");
      expect(fallbackModule.compactGraphLabel("👨‍👩‍👧‍👦AB", 2)).toBe("…");
      expect(fallbackModule.compactGraphLabel("🇨🇳AB", 2)).toBe("…");
      expect(fallbackModule.compactGraphLabel("가A", 2)).toBe("…");
      expect(fallbackModule.compactGraphLabel("क्षाA", 2)).toBe("…");
      expect(fallbackModule.compactGraphLabel("🏴\u{e0067}\u{e0062}\u{e0065}\u{e006e}\u{e0067}\u{e007f}A", 2)).toBe("…");
    } finally {
      if (descriptor) Object.defineProperty(Intl, "Segmenter", descriptor);
      else Reflect.deleteProperty(Intl, "Segmenter");
      vi.resetModules();
    }
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
