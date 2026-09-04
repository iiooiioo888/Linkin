import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

const root = fileURLToPath(new URL('.', import.meta.url))
const posix = (value: string) => value.replace(/\\/g, '/')

// GitHub Pages 專案站必須用 /Evoloop/，本機與 Docker 維持 /
const base = process.env.VITE_BASE || '/'

// https://vite.dev/config/
export default defineConfig({
  base,
  plugins: [react(), tailwindcss()],
  optimizeDeps: {
    include: [
      'react-is',
      'recharts',
      'three',
      'three/examples/jsm/controls/OrbitControls.js',
    ],
  },
  resolve: {
    alias: [
      {
        find: /^three\/addons\/(.*)$/,
        replacement: posix(path.resolve(root, 'node_modules/three/examples/jsm')) + '/$1',
      },
      {
        find: /^three$/,
        replacement: posix(path.resolve(root, 'node_modules/three/build/three.module.js')),
      },
    ],
    dedupe: ['react', 'react-dom', 'react-is', 'three'],
  },
  server: {
    // 5173 在部分 Windows 環境會 EACCES；預設 3001 避開占用
    port: Number(process.env.VITE_DEV_PORT) || 3001,
    strictPort: true,
    host: '127.0.0.1',
    proxy: {
      // 開發時將 API 請求代理到 FastAPI 後端
      // 容器內執行時透過 VITE_PROXY_TARGET 指向服務名（如 http://backend:8000）
      // Hub 最長前綴必須先匹配，否則會被 /api 剝除前綴變成 /v1/...
      '/api/v1': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
      '/api': {
        target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
