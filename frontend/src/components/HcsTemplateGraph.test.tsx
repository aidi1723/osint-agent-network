// @vitest-environment jsdom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HcsTemplateGraph } from "./HcsTemplateGraph";

let root: Root;

async function renderGraph() {
  await act(async () => {
    root.render(
      <HcsTemplateGraph
        organizationLabel="Example Manufacturing Organization"
        decisionLabel="Decision Maker Full Name"
        productLabel="Industrial Packaging Materials"
        locationLabel="Rotterdam, Netherlands"
        contactLabel="operator@example.test"
      />,
    );
  });
}

function graphNodes() {
  return Array.from(document.querySelectorAll<SVGGElement>('svg [role="button"]'));
}

async function activate(node: SVGGElement, event: MouseEvent | KeyboardEvent) {
  await act(async () => {
    node.dispatchEvent(event);
    await Promise.resolve();
  });
}

describe("HcsTemplateGraph", () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="graph-root"></div>';
    root = createRoot(document.getElementById("graph-root")!);
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean })
      .IS_REACT_ACT_ENVIRONMENT = true;
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("uses a labelled graph container without hiding interactive descendants behind an image role", async () => {
    await renderGraph();

    expect(document.querySelector('svg[role="group"][aria-label="HCS 双核心标准拓扑"]')).not.toBeNull();
    expect(graphNodes()).toHaveLength(11);
  });

  it("toggles node selection with click, Enter, and Space while preserving full SVG titles", async () => {
    await renderGraph();
    const [organization, offshore, manufacturing] = graphNodes();
    expect(organization.getAttribute("aria-pressed")).toBe("false");
    expect(organization.querySelector("title")?.textContent).toBe("Example Manufacturing Organization");

    await activate(organization, new MouseEvent("click", { bubbles: true }));
    expect(organization.getAttribute("aria-pressed")).toBe("true");
    expect(document.querySelector(".hcs-node-detail")).not.toBeNull();
    await activate(organization, new MouseEvent("click", { bubbles: true }));
    expect(organization.getAttribute("aria-pressed")).toBe("false");
    expect(document.querySelector(".hcs-node-detail")).toBeNull();

    await activate(offshore, new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(offshore.getAttribute("aria-pressed")).toBe("true");
    await activate(manufacturing, new KeyboardEvent("keydown", { key: " ", bubbles: true }));
    expect(offshore.getAttribute("aria-pressed")).toBe("false");
    expect(manufacturing.getAttribute("aria-pressed")).toBe("true");
  });

  it("returns focus to the selected node after closing its detail", async () => {
    const animationFrames: FrameRequestCallback[] = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
      animationFrames.push(callback);
      return animationFrames.length;
    });
    await renderGraph();
    const node = graphNodes()[0];
    await activate(node, new MouseEvent("click", { bubbles: true }));
    const closeButton = document.querySelector<HTMLButtonElement>('button[aria-label="关闭节点详情"]');
    expect(closeButton).not.toBeNull();

    await act(async () => {
      closeButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await Promise.resolve();
    });
    expect(document.querySelector(".hcs-node-detail")).toBeNull();
    expect(document.activeElement).not.toBe(node);

    await act(async () => {
      animationFrames.splice(0).forEach((callback) => callback(0));
    });
    expect(document.activeElement).toBe(node);
  });
});
