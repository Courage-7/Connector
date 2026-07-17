import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
export default defineConfig({
    base: "/app/",
    plugins: [react()],
    build: {
        outDir: "../src/connector_service/web_dist",
        emptyOutDir: true,
        sourcemap: true,
    },
    resolve: {
        alias: {
            "@": fileURLToPath(new URL("./src", import.meta.url)),
        },
    },
    server: {
        port: 5173,
        proxy: {
            "/v1": "http://[::1]:8000",
        },
    },
    test: {
        environment: "jsdom",
        setupFiles: "./src/test/setup.ts",
        css: true,
    },
});
