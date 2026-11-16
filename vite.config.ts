import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const enginePort = process.env.WFS_ENGINE_PORT ?? "8765";
// Cloud previews reach the dev server through a per-session hostname. Only the
// hosts named here are accepted; there is no wildcard fallback.
const allowedHosts = (process.env.WFS_ALLOWED_HOSTS ?? "")
  .split(",")
  .map((host) => host.trim())
  .filter(Boolean);

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  clearScreen: false,
  server: {
    host: true,
    port: 1420,
    strictPort: false,
    allowedHosts: allowedHosts.length > 0 ? allowedHosts : undefined,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${enginePort}`,
        changeOrigin: true,
      },
    },
  },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    outDir: "dist",
    target: "chrome105",
    sourcemap: false,
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ["echarts"],
          graph: ["cytoscape"],
          vendor: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
});
