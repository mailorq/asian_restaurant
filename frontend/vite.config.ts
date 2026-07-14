import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// dev proxy target; in the container it comes from the compose environment
const apiProxy = process.env.VITE_API_PROXY || "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true,
    port: 5173,
    // polling makes hmr work on windows/wsl bind mounts inside docker
    watch: { usePolling: true },
    proxy: {
      "/api": { target: apiProxy, changeOrigin: true },
      "/admin": { target: apiProxy, changeOrigin: true },
      "/static": { target: apiProxy, changeOrigin: true },
      "/media": { target: apiProxy, changeOrigin: true },
    },
  },
});
