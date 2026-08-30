/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Development only. The production build never learns a port: the SPA is
// served from the same origin as the API and every request is relative, so
// no backend port is ever compiled into the bundle (SI-37).
const DEV_API_PORT = Number(process.env.STATION_DEV_PORT ?? 8787);
const DEV_API_TARGET = `http://127.0.0.1:${DEV_API_PORT}`;

export default defineConfig({
  plugins: [react(), tailwindcss()],

  server: {
    // Loopback only. Never expose the dev server to the LAN.
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    // The browser only ever talks to the Vite origin; Vite forwards to the
    // backend server-side. changeOrigin rewrites Host to the backend
    // authority so the exact-Host guard still passes.
    proxy: {
      "/api": { target: DEV_API_TARGET, changeOrigin: true },
      "/session": { target: DEV_API_TARGET, changeOrigin: true },
    },
  },

  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },

  build: {
    target: "es2022",
    sourcemap: false,
    // The modulepreload polyfill is injected as an INLINE script, which the
    // strict `script-src 'self'` CSP would block. Native modulepreload is
    // available in every browser this Windows app targets (IMP-107).
    modulePreload: { polyfill: false },
  },

  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
