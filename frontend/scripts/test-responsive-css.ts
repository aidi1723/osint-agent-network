import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

const narrowShellBlock = css.match(/@media \(max-width: 960px\) \{[\s\S]*?\n\}/)?.[0] ?? "";
const narrowMobileBlock = css.match(/@media \(max-width: 620px\) \{[\s\S]*?\n\}/)?.[0] ?? "";

assert.match(narrowShellBlock, /\.sidebar\s*\{[\s\S]*position:\s*sticky/);
assert.match(narrowShellBlock, /nav\s*\{[\s\S]*display:\s*flex/);
assert.match(narrowShellBlock, /nav a\s*\{[\s\S]*flex:\s*0 0 40px/);
assert.match(narrowMobileBlock, /\.workspace\s*\{[\s\S]*padding:\s*10px/);
assert.match(narrowMobileBlock, /\.graph-canvas\s*\{[\s\S]*min-height:\s*360px/);
assert.match(narrowMobileBlock, /\.graph-canvas svg\s*\{[\s\S]*min-width:\s*720px/);

console.log("responsive css checks passed");
