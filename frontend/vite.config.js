import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// "localhost" only reaches the backend when both run directly on the same
// machine (e.g. `npm run dev`). Inside docker-compose, frontend and backend
// are separate containers — "localhost" there means "this container", not
// the other one — so docker-compose.yml sets BACKEND_PROXY_TARGET to the
// compose service name (http://backend:8000) instead. Defaults to
// localhost so plain `npm run dev` keeps working unchanged.
const backendTarget = process.env.BACKEND_PROXY_TARGET || "http://localhost:8000";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: backendTarget,
        changeOrigin: true,
      },
      "/health": {
        target: backendTarget,
        changeOrigin: true,
      },
    },
  },
});
