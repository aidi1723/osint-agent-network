import { readFileSync } from "node:fs";

const source = readFileSync(new URL("../src/main.tsx", import.meta.url), "utf8");
const loginSource = readFileSync(new URL("../src/components/AdminLogin.tsx", import.meta.url), "utf8");
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

const combined = `${source}\n${loginSource}\n${html}`;
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

const requiredLoginCopy = ["管理员登录", "访问凭据", "安全操作台", "退出登录"];
const missingLoginCopy = requiredLoginCopy.filter((phrase) => !combined.includes(phrase));
if (missingLoginCopy.length) {
  console.error(`管理员登录界面缺少中文文案: ${missingLoginCopy.join(", ")}`);
  process.exit(1);
}
