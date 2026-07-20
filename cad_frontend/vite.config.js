import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import { viteStaticCopy } from 'vite-plugin-static-copy'

const frontendDir = fileURLToPath(new URL('.', import.meta.url))

export default defineConfig({
  base: '/static/cad_viewer/',
  build: {
    outDir: resolve(frontendDir, '../static/cad_viewer'),
    emptyOutDir: true,
    modulePreload: false,
    rollupOptions: {
      input: resolve(frontendDir, 'src/main.js'),
      output: {
        entryFileNames: 'cad-viewer.js',
        chunkFileNames: 'cad-viewer-[name].js',
        assetFileNames: assetInfo => assetInfo.name?.endsWith('.css') ? 'cad-viewer.css' : '[name][extname]'
      }
    }
  },
  plugins: [
    viteStaticCopy({
      targets: [{
        src: 'node_modules/@mlightcad/cad-simple-viewer/dist/*-worker.js',
        dest: 'workers',
        rename: { stripBase: true }
      }, {
        src: 'vendor/fonts/*',
        dest: 'fonts',
        rename: { stripBase: true }
      }]
    })
  ]
})
