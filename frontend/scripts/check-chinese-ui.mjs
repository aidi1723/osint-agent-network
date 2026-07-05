import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

const forbiddenPhrases = [
  "Agent console",
  "Dashboard",
  "Evidence Graph",
  "Reports",
  "Investigation Control",
  "New Investigation",
  "Tool Registry",
  "Queued jobs",
  "Enabled tools",
  "Seed type",
  "Seed value",
  "Strategy",
  "Budgets",
  "No investigations queued yet.",
];

const combined = `${source}\n${html}`;
const forbiddenPatterns = [
  { label: "Status", pattern: />Status<|\{["'`]Status["'`]\}/ },
];
const hits = [
  ...forbiddenPhrases.filter((phrase) => combined.includes(phrase)),
  ...forbiddenPatterns.filter((item) => item.pattern.test(combined)).map((item) => item.label),
];

if (hits.length) {
  console.error(`UI still contains English phrases: ${hits.join(", ")}`);
  process.exit(1);
}
