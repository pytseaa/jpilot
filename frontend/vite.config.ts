import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser talks only to this dev server, which forwards /api to the backend.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
