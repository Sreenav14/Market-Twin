import { defineConfig, loadEnv } from "vite";
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, fileURLToPath(new URL("../../", import.meta.url)), "CONTROL_API_");
  const controlApiPort = env.CONTROL_API_PORT || "8000";
  return {
    resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        "/api": {
          target: `http://127.0.0.1:${controlApiPort}`,
          changeOrigin: true,
        },
      },
    },
  };
});
