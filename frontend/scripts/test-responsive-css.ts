import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const graphSource = readFileSync(new URL("../src/components/HcsTemplateGraph.tsx", import.meta.url), "utf8");

function mediaBlock(source: string, query: string) {
  const start = source.indexOf(`@media (${query})`);
  assert.notEqual(start, -1, `missing media query: ${query}`);
  const openingBrace = source.indexOf("{", start);
  assert.notEqual(openingBrace, -1, `missing opening brace for: ${query}`);

  let depth = 0;
  for (let index = openingBrace; index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    if (depth === 0) return source.slice(start, index + 1);
  }
  assert.fail(`unterminated media query: ${query}`);
}

const narrowShellBlock = mediaBlock(css, "max-width: 960px");
const narrowMobileBlock = mediaBlock(css, "max-width: 620px");

assert.match(narrowShellBlock, /\.sidebar\s*\{[\s\S]*position:\s*sticky/);
assert.match(narrowShellBlock, /nav\s*\{[\s\S]*display:\s*flex/);
assert.match(narrowShellBlock, /nav a\s*\{[\s\S]*flex:\s*0 0 40px/);
assert.match(narrowMobileBlock, /\.workspace\s*\{[\s\S]*padding:\s*10px/);
assert.match(narrowMobileBlock, /\.graph-canvas\s*\{[\s\S]*min-height:\s*360px/);
assert.match(narrowMobileBlock, /\.graph-canvas svg\s*\{[\s\S]*min-width:\s*720px/);
assert.match(css, /\.hcs-template-graph-viewport\s*\{[\s\S]*?overflow-x:\s*auto/);
assert.match(narrowMobileBlock, /\.hcs-node-detail\s*\{[\s\S]*?position:\s*static/);

const viewportStart = graphSource.indexOf('className="hcs-template-graph-viewport"');
const viewportEnd = graphSource.indexOf("</div>", viewportStart);
const detailStart = graphSource.indexOf("<aside", viewportEnd);
assert.notEqual(viewportStart, -1, "graph SVG needs a dedicated scrollable viewport");
assert.notEqual(viewportEnd, -1, "graph viewport must close after the SVG");
assert.ok(detailStart > viewportEnd, "node detail must render outside the SVG viewport overlay layer");

console.log("responsive css checks passed");
