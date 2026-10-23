import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: http://localhost:5180 proxies /api to the FastAPI app on :8000.
// Build: writes straight into backend/static, which FastAPI serves, so graders
// only need Python (no Node) to run the app.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: {
    outDir: "../backend/static",
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
  },
});
