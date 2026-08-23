import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "path";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
  server: {
    port: 5173,
    // The Docker container runs this dev server directly in production
    // (see frontend/motm-voice-frontend/Dockerfile), behind the Caddy
    // reverse proxy at motmvoice.b2botix.ai. Vite blocks requests with an
    // unrecognized Host header by default (DNS-rebinding protection), so
    // the production domain must be explicitly allow-listed here.
    allowedHosts: ["motmvoice.b2botix.ai", "localhost"],
  },
});
