import { defineConfig } from "vite";
import path from "node:path";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:4000",
        changeOrigin: true,
      },
    },
  },
  optimizeDeps: {
    // @datacon/shared-types is a CommonJS workspace package (its dist is also
    // require()'d by the NestJS API at runtime, so it must stay CJS); force
    // esbuild to pre-bundle/convert it to ESM for the browser dev server,
    // since Vite doesn't auto-optimize symlinked monorepo packages.
    include: ["@datacon/shared-types"],
  },
});
