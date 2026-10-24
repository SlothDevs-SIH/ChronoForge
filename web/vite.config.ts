import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api/engine/* -> Engine (8001), /api/agent/* -> Agent (8002)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/engine": { target: "http://localhost:8001", changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/engine/, "") },
      "/api/agent": { target: "http://localhost:8002", changeOrigin: true, rewrite: (p) => p.replace(/^\/api\/agent/, "") },
    },
  },
});
