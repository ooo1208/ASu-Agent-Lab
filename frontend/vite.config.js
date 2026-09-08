import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // 将 /api 请求代理到后端
      '/api': {
        target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8090',
        changeOrigin: true,
        // 不需要 rewrite，因为后端路由已经带 /api 前缀
      }
    }
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets'
  }
})
