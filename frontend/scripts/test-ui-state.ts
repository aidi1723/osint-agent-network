import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

import {
  isActiveInvestigationStatus,
  isReviewableInvestigationStatus,
  sanitizeReportHtml,
  selectedTaskRowClassName,
} from "../src/ui-state.ts";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3008/" });
globalThis.DOMParser = dom.window.DOMParser;
globalThis.Node = dom.window.Node;
globalThis.window = dom.window as unknown as Window & typeof globalThis;

assert.equal(
  selectedTaskRowClassName("decision-maker-faiz-chaudhry", "decision-maker-faiz-chaudhry"),
  "selected-row",
  "the active investigation row should expose a selected-row class",
);

assert.equal(
  selectedTaskRowClassName("buyer-family-hospitality-faiz-chaudhry", "decision-maker-faiz-chaudhry"),
  "",
  "non-selected investigation rows should not be highlighted",
);

assert.equal(
  selectedTaskRowClassName("decision-maker-faiz-chaudhry", null),
  "",
  "rows should not be highlighted before a task is selected",
);

assert.equal(isActiveInvestigationStatus("OPEN"), true, "open tasks should be active");
assert.equal(isActiveInvestigationStatus("RUNNING"), true, "running tasks should be active");
assert.equal(isActiveInvestigationStatus("CLAIMED"), true, "claimed tasks should be active");
assert.equal(isActiveInvestigationStatus("NEEDS_REVIEW"), false, "review tasks should not keep auto-refresh active");
assert.equal(isActiveInvestigationStatus("COMPLETED"), false, "completed tasks should not be active");
assert.equal(isReviewableInvestigationStatus("NEEDS_REVIEW"), true, "review tasks should stay visible in results filters");
assert.equal(isReviewableInvestigationStatus("COMPLETED"), true, "completed tasks should stay visible in results filters");
assert.equal(isReviewableInvestigationStatus("PARTIAL_FAILED"), true, "partial failures should stay visible in results filters");
assert.equal(isReviewableInvestigationStatus("RUNNING"), false, "running tasks belong in the active filter");
assert.equal(
  sanitizeReportHtml('<p onclick="alert(1)">ok</p><script>alert(2)</script><a href="javascript:alert(3)">x</a>'),
  "<p>ok</p><a>x</a>",
  "report html should strip scriptable content before rendering",
);

assert.equal(
  sanitizeReportHtml('<a href=javascript:alert(1)>x</a><img src=x onerror=alert(2)><iframe src="https://example.com"></iframe>'),
  '<a>x</a><img src="x">',
  "report html should remove unquoted script URLs, event handlers, and unsafe tags",
);

console.log("ui state checks passed");
