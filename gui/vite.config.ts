import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// GUI se servíruje z aplikace zakázky pod /gui (FastAPI StaticFiles); při vývoji proxy na lokální AG-UI server (app.py nebo fixture).
export default defineConfig({
  base: "/gui/",
  plugins: [react()],
  build: { outDir: "dist", sourcemap: false },
  server: { port: 5173, proxy: { "/agui": "http://127.0.0.1:8010", "/zakazky": "http://127.0.0.1:8010" } },
});
