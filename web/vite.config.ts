import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api/engine/* -> Engine (8001), /api/agent/* -> Agent (8002)
//
// Targets use 127.0.0.1, NOT "localhost". Node resolves "localhost" to IPv6 ::1 first, but uvicorn listens on IPv4 only,
// so the proxy got "connection refused" and answered every API call with an empty HTTP 500 (curl hid this by falling back
// to IPv4). That was the "backend not responding" bug. Override with ENGINE_PROXY / AGENT_PROXY if the services run elsewhere.
const ENGINE = process.env.ENGINE_PROXY ?? "http://127.0.0.1:8001";
const AGENT = process.env.AGENT_PROXY ?? "http://127.0.0.1:8002";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/engine": { target: ENGINE, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/engine/, "") },
      "/api/agent": { target: AGENT, changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/agent/, "") },
    },
  },
});
