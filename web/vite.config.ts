import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Behind Caddy (Compose) the API is same-origin. When running `npm run dev` directly on a
// developer machine, proxy API and admin calls to the Django dev server instead.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/admin": "http://localhost:8000",
      "/static": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  // Component and logic tests (npm test). Browser journeys are Playwright tests in e2e/.
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    unstubGlobals: true,
    coverage: {
      provider: "v8",
      // The client-side rules: API access, routing, sign-in, the frame and search (item 2.07), Home and
      // To do (items 2.07 to 2.09), the offline queue (item 4.02) and the course list. Add each screen here
      // as it gains tests; whole screens are also covered by the Playwright journeys.
      include: [
        "src/api/**",
        "src/app/**",
        "src/features/auth/**",
        "src/features/home/**",
        "src/features/todo/**",
        "src/features/courses/MyCoursesScreen.tsx",
        // Assignments, marking, rubrics, the gradebook, accommodations and notification settings (wave 3).
        "src/features/assignments/**",
        "src/features/marking/**",
        "src/features/rubrics/**",
        "src/features/gradebook/**",
        "src/features/accommodations/**",
        "src/features/notifications/**",
      ],
      exclude: ["src/**/*.test.*", "src/test/**"],
      reporter: ["text"],
      thresholds: { lines: 85, statements: 85, functions: 85, branches: 75 },
    },
  },
});
