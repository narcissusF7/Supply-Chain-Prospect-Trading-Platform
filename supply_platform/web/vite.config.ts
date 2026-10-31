import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite 配置：
// - React 插件
// - dev server 将 /api 代理到后端 http://127.0.0.1:8000，避免浏览器 CORS
//   前端统一使用相对路径 `/api/v1/...`，由本代理转发到后端。
//   显式用 127.0.0.1 而非 localhost，避免 Windows 下 localhost 先解析到 ::1 导致代理拒绝。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: "127.0.0.1",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
