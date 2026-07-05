import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiProxyTarget = process.env.VITE_DEV_API_PROXY_TARGET ?? "http://127.0.0.1:8088";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 3008,
    allowedHosts: ["production-host.local"],
    proxy: {
      "/api": apiProxyTarget,
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 3008,
    allowedHosts: ["production-host.local"],
  },
});
