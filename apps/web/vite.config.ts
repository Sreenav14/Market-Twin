import { defineConfig, loadEnv } from "vite";
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const root = fileURLToPath(new URL("../../", import.meta.url));
  const env = loadEnv(mode, root, "CONTROL_API_");
  const hitlEnv = loadEnv(mode, root, "VITE_");
  const controlApiPort = env.CONTROL_API_PORT || "8000";
  const hitlViewerTarget = hitlEnv.VITE_HITL_VIEWER_PROXY_TARGET || "http://127.0.0.1:8020";
  return {
    resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        "/api/v1/hitl-viewer": {
          target: hitlViewerTarget,
          changeOrigin: true,
          ws: true,
        },
        "/api": {
          target: `http://127.0.0.1:${controlApiPort}`,
          changeOrigin: true,
          timeout: 22 * 60 * 1000,
          proxyTimeout: 22 * 60 * 1000,
        },
      },
    },
  };
});
