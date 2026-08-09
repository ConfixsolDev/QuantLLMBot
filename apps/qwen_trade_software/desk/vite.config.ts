import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "../website",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/snapshot": "http://127.0.0.1:48632",
      "/deal-sheet": "http://127.0.0.1:48632",
    },
  },
});
