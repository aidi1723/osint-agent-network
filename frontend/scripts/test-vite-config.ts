import assert from "node:assert/strict";

process.env.VITE_DEV_API_PROXY_TARGET = "http://api:8088";

const configModule = await import("../vite.config.ts");
const config = typeof configModule.default === "function" ? configModule.default({ command: "serve", mode: "development" }) : configModule.default;

assert.equal(
  config.server?.proxy?.["/api"],
  "http://api:8088",
  "vite dev proxy should be configurable for Docker Compose service networking",
);

console.log("vite config checks passed");
