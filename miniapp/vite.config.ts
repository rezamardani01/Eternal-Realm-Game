import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the page talks to the preview API (python scripts/miniapp_preview.py) through this proxy.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: { "/api": "http://127.0.0.1:8085" } },
  build: { target: "es2020", cssCodeSplit: true, chunkSizeWarningLimit: 400 },
});
