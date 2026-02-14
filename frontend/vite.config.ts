import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) return;
          const normalizedId = id.replace(/\\/g, "/");
          if (normalizedId.includes("lightweight-charts") || normalizedId.includes("fancy-canvas")) return "vendor-lightweight-charts";
          if (normalizedId.includes("react-router-dom") || normalizedId.includes("react-router")) return "vendor-react-router";
          if (normalizedId.includes("react-dom")) return "vendor-react-dom";
          if (normalizedId.includes("zustand")) return "vendor-zustand";
          if (normalizedId.includes("/node_modules/react/")) return "vendor-react";
          if (normalizedId.includes("@tanstack/react-query") || normalizedId.includes("@tanstack/query-core")) return "vendor-react-query";
          if (normalizedId.includes("use-resize-observer")) return "vendor-chart-utils";
          return "vendor-misc";
        }
      }
    }
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/binance-spot": {
        target: "https://api.binance.com",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/binance-spot/, "")
      },
      "/binance-fapi": {
        target: "https://fapi.binance.com",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/binance-fapi/, "")
      },
      "/oracle-api": {
        target: "http://127.0.0.1:8091",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/oracle-api/, "")
      }
    }
  }
});
