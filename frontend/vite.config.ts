import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiProxy = env.VITE_API_PROXY ?? "http://localhost:8000";

  return {
    plugins: [react(), tailwindcss()],
    server: {
      host: true,
      port: 5173,
      // Polling makes HMR work on Windows/WSL bind mounts inside Docker.
      watch: { usePolling: true },
      // Dev: forward backend routes so the SPA and API share an origin.
      proxy: {
        "/api": { target: apiProxy, changeOrigin: true },
        "/admin": { target: apiProxy, changeOrigin: true },
        "/static": { target: apiProxy, changeOrigin: true },
        "/media": { target: apiProxy, changeOrigin: true },
      },
    },
  };
});
