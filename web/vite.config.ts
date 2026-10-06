import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

// --- packaged content (items 5.12, 5.13; ADR 0012) ---
// The package players run inside the sandboxed frame the API serves (api/packages/play.py), which loads them
// as plain files from /players/: scorm-again's cross-frame client and h5p-standalone, copied here from their
// npm packages at the exact versions in package.json, beside the LMS's own frame scripts in public/players/.
const PLAYERS: { from: string; to: string; only?: RegExp }[] = [
  { from: "node_modules/scorm-again/dist", to: "players/scorm-again", only: /^cross-frame-api\.min\.js$/ },
  { from: "node_modules/h5p-standalone/dist", to: "players/h5p", only: /\.(js|css|woff2?|gif|svg|txt)$/ },
];
const TYPES: Record<string, string> = {
  ".js": "text/javascript",
  ".css": "text/css",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".txt": "text/plain",
};

function playerFiles(): { fileName: string; path: string }[] {
  const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => (statSync(join(dir, name)).isDirectory() ? walk(join(dir, name)) : [join(dir, name)]));
  return PLAYERS.flatMap(({ from, to, only }) => {
    const root = join(import.meta.dirname, from);
    return walk(root)
      .map((path) => ({ path, name: relative(root, path).split(/[\\/]/).join("/") }))
      .filter(({ name }) => !only || only.test(name))
      .map(({ path, name }) => ({ path, fileName: `${to}/${name}` }));
  });
}

function players(): Plugin {
  return {
    name: "gsa-players",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const wanted = (req.url ?? "").split("?")[0].replace(/^\//, "");
        const hit = wanted.startsWith("players/") ? playerFiles().find((f) => f.fileName === wanted) : undefined;
        if (!hit) return next();
        res.setHeader("Content-Type", TYPES[extname(hit.path)] ?? "application/octet-stream");
        res.setHeader("Access-Control-Allow-Origin", "*");
        res.end(readFileSync(hit.path));
      });
    },
    generateBundle() {
      for (const file of playerFiles()) this.emitFile({ type: "asset", fileName: file.fileName, source: readFileSync(file.path) });
    },
  };
}
// --- end packaged content ---

// Behind Caddy (Compose) the API is same-origin. When running `npm run dev` directly on a
// developer machine, proxy API and admin calls to the Django dev server instead.
export default defineConfig({
  plugins: [react(), players()],
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
    // Fonts are always files: the Content-Security-Policy (font-src 'self') refuses fonts in data: addresses,
    // which Vite would otherwise make of KaTeX's smallest fonts.
    assetsInlineLimit: (file) => (/\.(woff2?|ttf)$/.test(file) ? false : undefined),
  },
  // Component and logic tests (npm test). Browser journeys are Playwright tests in e2e/.
  test: {
    environment: "jsdom",
    // Screens with long forms are typed key by key; on a busy machine or a small CI runner the 5-second
    // default is reached by load alone, not by a fault, so every test gets the same, longer limit.
    testTimeout: 15_000,
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
        // Teaching content, the page editor, course setup and course administration (items 2.12 to 2.20).
        "src/features/content/**",
        "src/features/course-admin/**",
        // Forums, messages, groups, classes and the calendar (items 4.08 to 4.15, 2.32).
        "src/features/forums/**",
        "src/features/messages/**",
        "src/features/groups/**",
        "src/features/attendance/**",
        "src/features/calendar/**",
        // --- accounts, staff development and the console ---
        "src/features/account/**",
        "src/features/learning/**",
        "src/features/admin/**",
        // Practicals, competency and the logbook (items 3.12 to 3.15, 5.15), with the photos kept offline.
        "src/features/practicals/**",
        // Quizzes (feature 10): the tab, attempts, banks and the question editor.
        "src/features/quizzes/**",
        // --- packaged content, the library and interchange (items 5.10, 5.12 to 5.14, 6.08) ---
        "src/features/packages/**",
      ],
      exclude: ["src/**/*.test.*", "src/test/**"],
      reporter: ["text"],
      thresholds: { lines: 85, statements: 85, functions: 85, branches: 75 },
    },
  },
});
