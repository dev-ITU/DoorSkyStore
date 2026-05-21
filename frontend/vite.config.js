import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    manifest: 'manifest.json',
    outDir: '../static/react',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: 'src/main.jsx',
      },
    },
  },
});
