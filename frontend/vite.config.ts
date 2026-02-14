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
          if (id.includes("lightweight-charts")) return "vendor-lightweight-charts";
          if (id.includes("@tanstack/react-query")) return "vendor-react-query";
          if (id.includes("zustand")) return "vendor-zustand";
          return "vendor";
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
