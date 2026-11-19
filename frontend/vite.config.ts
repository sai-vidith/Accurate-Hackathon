import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Pre-bundle these at startup so Vite never re-optimizes mid-session (which can blank an open page).
  optimizeDeps: { include: ["react", "react-dom", "react-dom/client", "leaflet", "react-leaflet"] },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
