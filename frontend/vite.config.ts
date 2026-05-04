import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:18080",
      "/auth": "http://127.0.0.1:18080",
      "/admin": "http://127.0.0.1:18080",
      "/v1": "http://127.0.0.1:18080",
      "/health": "http://127.0.0.1:18080"
    }
  }
});
