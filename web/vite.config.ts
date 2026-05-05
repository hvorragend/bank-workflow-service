/// <reference types="vitest" />
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      // Im Dev-Modus laeuft Backend auf 8000, Frontend auf 5173. Wir proxien
      // alle API-Endpunkte transparent ans Backend, damit Cookies und Auth
      // unter derselben Origin laufen.
      "/auth":        { target: "http://localhost:8000", changeOrigin: true },
      "/instances":   { target: "http://localhost:8000", changeOrigin: true },
      "/definitions": { target: "http://localhost:8000", changeOrigin: true },
      "/health":      { target: "http://localhost:8000", changeOrigin: true },
      "/ready":       { target: "http://localhost:8000", changeOrigin: true },
      "/legacy":      { target: "http://localhost:8000", changeOrigin: true },
      "/docs":        { target: "http://localhost:8000", changeOrigin: true },
      "/openapi.json":{ target: "http://localhost:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
  },
});
