import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// No dev proxy on purpose: the dashboard talks to absolute URLs configured in
// /ops/settings (platform-api on :18081, api-gateway on :18000 by default).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 700,
  },
});
